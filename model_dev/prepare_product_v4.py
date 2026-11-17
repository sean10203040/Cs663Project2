"""Build an audited train-only candidate without cloud calls or changes to frozen data."""
import argparse
import copy
from collections import Counter
import hashlib
import json
import mimetypes
from pathlib import Path
import shutil

from backend.contracts import parse_reading
from model_dev.product_policy_v4 import INSTRUCTION, PROMPT_VERSION, make_prompt

FIELDS = ("product_name", "brand", "size", "best_by")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical_sha(value):
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def field_values(target):
    return {k: target[k] if k in ("product_name", "brand") else target["key_attributes"][k] for k in FIELDS}


def prepare(source_path, audit_path, output, gcs_prefix):
    """Validate all inputs before creating output. Never promote validation into training."""
    if not gcs_prefix.startswith("gs://") or len(gcs_prefix.split("/")) < 4:
        raise ValueError("Use a dedicated Cloud Storage bucket/prefix")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output must be empty; preserve previous runs")
    source_bytes = source_path.read_bytes()
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["source_examples_sha256"] != sha(source_bytes):
        raise ValueError("Source examples changed since review")
    if audit["policy_version"] != PROMPT_VERSION or audit["instruction_sha256"] != sha(INSTRUCTION.encode()):
        raise ValueError("Review is bound to a different candidate policy")
    records = read_rows(source_path)
    if any(r["split"] not in ("train", "validation") for r in records):
        raise ValueError("Source must contain only frozen train/validation data")
    train = {r["example_id"]: r for r in records if r["split"] == "train"}
    if len(train) != sum(r["split"] == "train" for r in records):
        raise ValueError("Duplicate training IDs")
    decisions = audit["decisions"]
    if len(decisions) != len(train) or {d["example_id"] for d in decisions} != set(train):
        raise ValueError("Review must cover each training ID exactly once; no held-out IDs")
    root = source_path.parent.resolve()
    groups, hashes, photos = {}, {}, {}
    blobs = {}
    for row in records:
        group, split = row["product_group"], row["split"]
        if not group or group in groups and groups[group] != split:
            raise ValueError("Product family leaks between splits")
        groups[group] = split
        photo = row.get("source_photo_sha256")
        if photo:
            if photo in photos and photos[photo] != split:
                raise ValueError("Source photo leaks between splits")
            photos[photo] = split
        if row.get("context") is not None:
            raise ValueError("This review covers one exact crop per example")
        path = (root / row["crop"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Invalid crop path")
        blob = path.read_bytes()
        digest = sha(blob)
        if digest != path.stem:
            raise ValueError("Crop hash mismatch")
        if digest in hashes and hashes[digest] != split:
            raise ValueError("Identical crop leaks between splits")
        hashes[digest] = split
        blobs[row["crop"]] = blob
    selected, changes, held = [], [], []
    for decision in decisions:
        row = copy.deepcopy(train[decision["example_id"]])
        if decision["source_row_sha256"] != canonical_sha(row):
            raise ValueError("Reviewed row changed")
        if decision["image_sha256"] != sha(blobs[row["crop"]]):
            raise ValueError("Review refers to a different image")
        status = decision["status"]
        if status not in ("retain", "revise", "hold"):
            raise ValueError("Every example needs a resolved review disposition")
        if not decision.get("notes"):
            raise ValueError("Review needs notes")
        if status == "hold":
            held.append(decision)
            continue
        patches = decision["fields"]
        if status == "retain" and patches or status == "revise" and not patches:
            raise ValueError("Review status disagrees with patches")
        before = copy.deepcopy(row["target"])
        for key, patch in patches.items():
            if key not in FIELDS or not patch.get("reason"):
                raise ValueError("Invalid field correction")
            if patch["before"] != field_values(before)[key] or patch["before_evidence"] != before["evidence"].get(key):
                raise ValueError("Correction does not match original target")
            if key in ("product_name", "brand"):
                row["target"][key] = patch["value"]
            else:
                row["target"]["key_attributes"][key] = patch["value"]
            if patch["value"] is None:
                row["target"]["evidence"].pop(key, None)
            else:
                row["target"]["evidence"][key] = {"source": patch["source"], "quote": patch["quote"]}
        row["target"] = parse_reading(json.dumps(row["target"], ensure_ascii=False), row["ocr_text"]).model_dump()
        row["candidate_review"] = {"policy": PROMPT_VERSION, "reviewer": "assistant",
            "independently_human_verified": False, "status": status, "original_row_sha256": decision["source_row_sha256"]}
        selected.append(row)
        if row["target"] != before:
            changes.append({"example_id": row["example_id"], "image_sha256": decision["image_sha256"],
                "before": before, "after": row["target"], "fields": patches})
    if not selected:
        raise ValueError("No candidate training rows")
    requests = []
    for row in selected:
        mime = mimetypes.guess_type(row["crop"])[0]
        if mime not in ("image/jpeg", "image/png"):
            raise ValueError("Unsupported image MIME type")
        requests.append({"contents": [{"role": "user", "parts": [
            {"fileData": {"mimeType": mime, "fileUri": gcs_prefix.rstrip("/") + "/" + row["crop"]}},
            {"text": make_prompt(row["ocr_text"])}]},
            {"role": "model", "parts": [{"text": json.dumps(row["target"], ensure_ascii=False)}]}],
            "generationConfig": {"mediaResolution": "MEDIA_RESOLUTION_HIGH"}})
    manifest = {"policy_version": PROMPT_VERSION, "instruction_sha256": sha(INSTRUCTION.encode()),
        "source_examples_sha256": sha(source_bytes), "review_sha256": sha(audit_path.read_bytes()),
        "counts": {"original_train": len(train), "candidate_train": len(selected), "held_for_review": len(held)},
        "families": {"original_train": len({r["product_group"] for r in train.values()}),
            "candidate_train": len({r["product_group"] for r in selected})},
        "dispositions": dict(Counter(d["status"] for d in decisions)),
        "changed_examples": len(changes), "changed_fields": dict(Counter(k for c in changes for k in c["fields"])),
        "gcs_prefix_planned_only": gcs_prefix, "cloud_calls_made": False,
        "review_limit": "Assistant first-pass visual review, not independent human ground truth. Held rows excluded; no completeness guarantee.",
        "evaluation_policy": "Frozen validation inputs/labels checked for leakage but not exported or edited. Final-test data never opened. Old v3 scores unchanged.",
        "release_status": "local candidate; validation-policy adjudication and paid-run approval remain before training"}
    (output / "images").mkdir(parents=True, exist_ok=True)
    for row in selected:
        shutil.copyfile(root / row["crop"], output / row["crop"])
    for name, rows in (("examples.jsonl", selected), ("train.jsonl", requests)):
        (output / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    manifest["files"] = {name: sha((output / name).read_bytes()) for name in ("examples.jsonl", "train.jsonl")}
    for name, value in (("changes.json", changes), ("held_for_review.json", held), ("manifest.json", manifest)):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "instruction.txt").write_text(INSTRUCTION, encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gcs-prefix", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.audit, args.output, args.gcs_prefix), indent=2))
