"""Extract the exact question prompt from the existing model's downloaded SFT data."""
import argparse
import hashlib
import json
from pathlib import Path

from backend.qa import PROMPT_VERSION, parse_answer, prompt_digest


def load_sft(path: Path) -> list[dict]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        raw = json.loads(line)
        contents = raw.get("contents", [])
        if len(contents) != 2 or [c.get("role") for c in contents] != ["user", "model"]:
            raise ValueError(f"{path.name}:{number}: expected exactly user input and model reference")
        if set(raw) - {"contents"}:
            raise ValueError(f"{path.name}:{number}: extra top-level fields need review before replay")
        parts = contents[0].get("parts", [])
        if len(parts) != 2 or "fileData" not in parts[0] or "text" not in parts[1]:
            raise ValueError(f"{path.name}:{number}: expected image followed by question prompt")
        image = parts[0]["fileData"]
        if set(parts[0]) != {"fileData"} or set(parts[1]) != {"text"}:
            raise ValueError("Additional input fields need review")
        if not image.get("fileUri", "").startswith("gs://") or image.get("mimeType") not in ("image/jpeg", "image/png"):
            raise ValueError("Expected a GCS JPEG/PNG image")
        answer_parts = contents[1].get("parts", [])
        if len(answer_parts) != 1 or set(answer_parts[0]) != {"text"}:
            raise ValueError("Expected one JSON reference answer")
        target = parse_answer(answer_parts[0]["text"]).model_dump()
        rows.append({"line": number, "user": contents[0], "image_uri": image["fileUri"],
                     "text": parts[1]["text"], "target": target})
    if not rows:
        raise ValueError(f"Empty dataset: {path}")
    return rows


def extract_template(rows: list[dict], marker: str = "Question:") -> dict:
    prefixes = set()
    for row in rows:
        text = row["text"]
        if text.count(marker) != 1:
            raise ValueError("Each training prompt must contain the question marker exactly once. "
                             "Inspect train.jsonl and pass --question-marker with its exact marker.")
        head, question = text.split(marker)
        whitespace = question[:len(question)-len(question.lstrip())]
        if not question.strip():
            raise ValueError("Empty training question")
        prefixes.add(head + marker + whitespace)
    if len(prefixes) != 1:
        raise ValueError("Training instructions differ across examples; review before extracting a template")
    prefix = prefixes.pop()
    # Existing SFT format must end with the question. If instructions follow it,
    # review the data and supply a manually verified prefix/suffix instead.
    suffix = ""
    return {"prompt_version": PROMPT_VERSION, "prefix": prefix, "suffix": suffix,
            "prompt_sha256": prompt_digest(prefix, suffix), "training_examples": len(rows),
            "review_note": "Extracted common prefix; inspect that training prompts end with the question."}


def assert_held_out(train: list[dict], validation: list[dict], test: list[dict]):
    splits = {"train": train, "validation": validation, "test": test}
    owners = {}
    for split, rows in splits.items():
        for row in rows:
            uri = row["image_uri"]
            if uri in owners and owners[uri] != split:
                raise ValueError(f"Image URI occurs in both {owners[uri]} and {split}: {uri}")
            owners[uri] = split
    # This catches URI overlap, not near duplicates, renamed images or shared products.


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--train", type=Path, required=True)
    p.add_argument("--validation", type=Path, required=True)
    p.add_argument("--test", type=Path, required=True)
    p.add_argument("--question-marker", default="Question:")
    p.add_argument("--output", type=Path, default=Path("backend/qa_prompt.json"))
    a = p.parse_args()
    train, validation, test = [load_sft(path) for path in (a.train, a.validation, a.test)]
    assert_held_out(train, validation, test)
    template = extract_template(train, a.question_marker)
    for row in validation + test:
        if not row["text"].startswith(template["prefix"]):
            raise ValueError("Held-out instructions differ from the training prompt")
    template["training_jsonl_sha256"] = hashlib.sha256(a.train.read_bytes()).hexdigest()
    template["split_counts"] = {"train": len(train), "validation": len(validation), "test": len(test)}
    template["split_check"] = "No shared image URIs; product independence and image content not audited"
    if a.output.exists():
        raise ValueError("Output exists; choose a new path to avoid replacing a reviewed template")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(template, ensure_ascii=False, indent=2))
    print("Review prefix and question placement before using this template. No model calls or training were run.")


if __name__ == "__main__":
    main()
