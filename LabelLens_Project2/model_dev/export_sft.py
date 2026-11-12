"""Export only reviewed, group-separated examples to Gemini multimodal JSONL."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
from backend.contracts import PROMPT_VERSION, make_prompt, parse_reading


def load_reviewed(path):
    root = path.parent.resolve()
    records = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]
    selected, groups, image_splits = [], {}, {}
    for row in records:
        if row.get("reviewed") is not True:
            continue
        group, split = row.get("product_group"), row.get("split")
        if not group or split not in {"train", "validation", "test"}:
            raise ValueError("Reviewed examples require a product group and train/validation/test split")
        if group in groups and groups[group] != split:
            raise ValueError(f"Product group occurs in multiple splits: {group}")
        groups[group] = split
        row["target"] = parse_reading(json.dumps(row["target"]), row["ocr_text"]).model_dump()
        for key in ["crop", "context"]:
            image = (root/row[key]).resolve()
            if not image.is_relative_to(root) or not image.is_file():
                raise ValueError("Images must exist inside the examples folder")
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            if digest in image_splits and image_splits[digest] != split:
                raise ValueError("Identical image content appears across splits")
            image_splits[digest] = split
        selected.append(row)
    if not selected:
        raise ValueError("No reviewed examples; unreviewed or generated drafts cannot be used as ground truth")
    return selected


def export(records_path, output, gcs_prefix):
    if not gcs_prefix.startswith("gs://") or len(gcs_prefix.split("/")) < 3:
        raise ValueError("Use a Cloud Storage prefix such as gs://bucket/labellens")
    records = load_reviewed(records_path)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output must be new so reviewed datasets are not overwritten")
    (output/"images").mkdir(parents=True, exist_ok=True)
    splits = {s: [] for s in ["train", "validation", "test"]}
    for row in records:
        parts = []
        for key in ["crop", "context"]:
            source = records_path.parent/row[key]
            name = hashlib.sha256(source.read_bytes()).hexdigest()+".jpg"
            shutil.copyfile(source, output/"images"/name)
            parts.append({"fileData": {"mimeType": "image/jpeg", "fileUri": gcs_prefix.rstrip("/")+"/images/"+name}})
        parts.append({"text": make_prompt(row["ocr_text"])})
        splits[row["split"]].append({"contents": [{"role": "user", "parts": parts},
            {"role": "model", "parts": [{"text": json.dumps(row["target"], ensure_ascii=False)}]}]})
    for split, examples in splits.items():
        (output/(split+".jsonl")).write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in examples), encoding="utf-8")
    manifest = {"prompt_version": PROMPT_VERSION, "counts": {s: len(r) for s, r in splits.items()},
        "product_groups": dict(Counter(r["split"] for r in {x["product_group"]: x for x in records}.values())),
        "source_examples_sha256": hashlib.sha256(records_path.read_bytes()).hexdigest(),
        "gcs_prefix": gcs_prefix, "proposal_training_target": 400,
        "note": "test.jsonl is held out and must not be passed to the tuning job"}
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--records",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True);p.add_argument("--gcs-prefix",required=True)
    a=p.parse_args();export(a.records,a.output,a.gcs_prefix)
