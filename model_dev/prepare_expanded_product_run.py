"""Build a local training candidate from the frozen 287 and reviewed held rows.

This module makes no network calls. It never edits a previous run or uploads data.
"""
import argparse
import copy
import json
import mimetypes
from pathlib import Path
import shutil

from backend.contracts import parse_reading
from model_dev.prepare_product_v4 import canonical_sha, field_values, read_rows, sha
from model_dev.product_policy_v4 import INSTRUCTION, PROMPT_VERSION, make_prompt


def prepare(source, previous, audit_path, output, prefix):
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if output.exists():
        raise ValueError("Use a new output directory; existing revisions are immutable")
    if not prefix.startswith("gs://") or prefix.rstrip("/") == audit["previous_gcs_prefix"].rstrip("/"):
        raise ValueError("A distinct planned Cloud Storage prefix is required")
    for path, key in ((source, "source_examples_sha256"), (previous, "previous_examples_sha256")):
        if sha(path.read_bytes()) != audit[key]:
            raise ValueError("Frozen input changed: " + str(path))
    if audit["policy_version"] != PROMPT_VERSION or audit["instruction_sha256"] != sha(INSTRUCTION.encode()):
        raise ValueError("Review policy changed")
    original = read_rows(source)
    train = {r["example_id"]: r for r in original if r["split"] == "train"}
    old_rows = read_rows(previous)
    retained = {r["example_id"]: r for r in old_rows}
    entries = audit["entries"]
    ids = [e["example_id"] for e in entries]
    held = set(train) - set(retained)
    if len(ids) != len(set(ids)) or set(ids) != held:
        raise ValueError("Review must cover every held training row exactly once")
    if len(train) != 400 or len(old_rows) != 287 or len(held) != 113:
        raise ValueError("Unexpected frozen dataset membership")
    root = source.parent.resolve()
    groups, photos, hashes, blobs = {}, {}, {}, {}
    for row in original:
        if row["split"] not in ("train", "validation") or row.get("context") is not None:
            raise ValueError("Unexpected source split or context")
        path = (root / row["crop"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Crop escapes dataset")
        blob = path.read_bytes()
        digest = sha(blob)
        if digest != path.stem:
            raise ValueError("Image content hash mismatch")
        for mapping, key in ((groups, row["product_group"]), (photos, row.get("source_photo_sha256")), (hashes, digest)):
            if key:
                if key in mapping and mapping[key] != row["split"]:
                    raise ValueError("Training/validation leakage")
                mapping[key] = row["split"]
        blobs[row["crop"]] = blob
    for row in old_rows:
        original_row = train.get(row["example_id"])
        if original_row is None or row["split"] != "train":
            raise ValueError("Previous candidate includes a non-training row")
        for key in ("ocr_text", "crop", "product_group", "source_photo_sha256"):
            if row.get(key) != original_row.get(key):
                raise ValueError("Previous candidate changed input evidence")
    accepted, excluded, changes = {}, [], []
    for entry in entries:
        row = train[entry["example_id"]]
        if entry["source_row_sha256"] != canonical_sha(row) or entry["image_sha256"] != sha(blobs[row["crop"]]):
            raise ValueError("Review does not match original row/image")
        if not entry.get("note") or entry["disposition"] not in ("include", "exclude"):
            raise ValueError("Unresolved review")
        if entry["disposition"] == "exclude":
            excluded.append(entry)
            continue
        candidate = copy.deepcopy(row)
        candidate["target"] = parse_reading(json.dumps(entry["target"], ensure_ascii=False), row["ocr_text"]).model_dump()
        candidate["candidate_review"] = {
            "policy": PROMPT_VERSION, "reviewer": "assistant",
            "independently_human_verified": False,
            "status": "held_row_rechecked", "original_row_sha256": entry["source_row_sha256"],
            "review_audit_sha256": sha(audit_path.read_bytes()),
        }
        accepted[row["example_id"]] = candidate
        changes.append({"example_id": row["example_id"], "number": entry["number"],
                        "before": row["target"], "after": candidate["target"], "note": entry["note"]})
    selected = [retained.get(r["example_id"], accepted.get(r["example_id"]))
                for r in original if r["split"] == "train"]
    selected = [r for r in selected if r is not None]
    requests = []
    for row in selected:
        parse_reading(json.dumps(row["target"], ensure_ascii=False), row["ocr_text"])
        mime = mimetypes.guess_type(row["crop"])[0]
        if mime not in ("image/jpeg", "image/png"):
            raise ValueError("Unsupported image type")
        requests.append({"contents": [
            {"role": "user", "parts": [
                {"fileData": {"mimeType": mime, "fileUri": prefix.rstrip("/") + "/" + row["crop"]}},
                {"text": make_prompt(row["ocr_text"])}]},
            {"role": "model", "parts": [{"text": json.dumps(row["target"], ensure_ascii=False)}]}],
            "generationConfig": {"mediaResolution": "MEDIA_RESOLUTION_HIGH"}})
    partial = sum(any(v is None for v in field_values(r["target"]).values()) and
                  any(v is not None for v in field_values(r["target"]).values()) for r in accepted.values())
    unknown = sum(all(v is None for v in field_values(r["target"]).values()) for r in accepted.values())
    manifest = {
        "policy_version": PROMPT_VERSION, "instruction_sha256": sha(INSTRUCTION.encode()),
        "source_examples_sha256": audit["source_examples_sha256"],
        "previous_examples_sha256": audit["previous_examples_sha256"],
        "review_sha256": sha(audit_path.read_bytes()),
        "counts": {"previous_train": len(retained), "held_reviewed": len(entries),
                   "recovered": len(accepted), "recovered_partial": partial,
                   "recovered_all_unknown": unknown, "excluded": len(excluded), "candidate_train": len(selected)},
        "candidate_product_families": len({r["product_group"] for r in selected}),
        "gcs_prefix_planned_only": prefix, "cloud_calls_made": False,
        "release_status": "Local candidate only; no upload, paid job, or deployment performed.",
        "review_limit": "Assistant visual review under user delegation; not independent human ground truth or an accuracy measurement.",
        "evaluation_policy": "Existing 287 rows preserved exactly. Validation inputs/labels checked for leakage but neither exported nor edited. Final-test data not opened.",
    }
    (output / "images").mkdir(parents=True)
    for row in selected:
        shutil.copyfile(root / row["crop"], output / row["crop"])
    for name, rows in (("examples.jsonl", selected), ("train.jsonl", requests)):
        (output / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    manifest["files"] = {n: sha((output / n).read_bytes()) for n in ("examples.jsonl", "train.jsonl")}
    for name, value in (("changes.json", changes), ("excluded.json", excluded), ("manifest.json", manifest)):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "instruction.txt").write_text(INSTRUCTION, encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "previous", "audit", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--gcs-prefix", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.previous, args.audit, args.output, args.gcs_prefix), indent=2))
