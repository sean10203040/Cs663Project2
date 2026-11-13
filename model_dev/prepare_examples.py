"""Convert exported Android scans into REVIEW REQUIRED multimodal example records."""
import argparse
import json
from pathlib import Path
from PIL import Image
from backend.contracts import parse_reading


def jpeg(source, destination):
    with Image.open(source) as image:
        image = image.convert("RGB")
        image.thumbnail((2048, 2048))
        image.save(destination, "JPEG", quality=95)


def prepare(scans, output):
    target = output/"examples.jsonl"
    if target.exists():
        raise ValueError("examples.jsonl already exists; choose a new output to preserve reviewed edits")
    output.mkdir(parents=True, exist_ok=True)
    (output/"images").mkdir(exist_ok=True)
    rows = []
    for path in sorted(scans.rglob("scan.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        review = record.get("product_review") or {}
        reviewed = review.get("reviewed") is True
        stage = record["paths"].get(record["primary_path"], {})
        inputs = review if reviewed else {}
        crop_name = inputs.get("crop", record.get("product_details_crop", stage.get("image", "source.png")))
        if Path(crop_name).name != crop_name:
            raise ValueError("Unexpected scan image path")
        identifier = record["scan_id"]
        if not identifier.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Unexpected scan ID")
        crop, context = f"images/{identifier}_crop.jpg", f"images/{identifier}_context.jpg"
        jpeg(path.parent/crop_name, output/crop)
        context_name = inputs.get("context", record.get("product_details_context", "source.png"))
        if context_name is not None:
            if Path(context_name).name != context_name:
                raise ValueError("Unexpected context image path")
            jpeg(path.parent/context_name, output/context)
        else:
            context = None
        ocr = record.get("product_details_ocr_text", record.get("primary_ocr_text", stage.get("text", "")))
        if reviewed:
            ocr = review.get("ocr_text",ocr)
        draft = inputs.get("prediction", record.get("product_details", {}).get("reading"))
        checked = parse_reading(json.dumps(review["target"]), ocr).model_dump() if reviewed else draft
        rows.append({"example_id": identifier, "product_group": review.get("product_group", record.get("product_group")),
            "split": review.get("split", record.get("split", "development")), "condition": record.get("condition"),
            "crop": crop, "context": context, "ocr_text": ocr,
            "ocr_engine": "MLKit-Latin-16.0.1", "reviewed": reviewed,
            "target": checked, "prediction": draft, "reviewed_epoch_ms": review.get("reviewed_epoch_ms"),
            "target_origin": "human-checked reference" if reviewed else "unreviewed model draft" if draft else "not annotated",
            "review_notes": "Check each field against this exact image; unreadable/absent fields must be null."})
    target.write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in rows), encoding="utf-8")
    print(f"Prepared {len(rows)} examples ({sum(r['reviewed'] for r in rows)} checked) at {target}. No training was started.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scans", type=Path, required=True, help="Folder containing extracted Android scan ZIPs")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(); prepare(a.scans, a.output)
