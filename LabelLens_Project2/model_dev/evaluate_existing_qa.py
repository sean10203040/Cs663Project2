"""Replay held-out SFT user inputs identically against base and existing tuned Gemini."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import time

from backend import qa
from model_dev.prepare_existing_qa import assert_held_out, load_sft


def normalize(value):
    return " ".join(value.casefold().split())


def token_f1(expected, predicted):
    e, p = Counter(normalize(expected).split()), Counter(normalize(predicted).split())
    common = sum((e & p).values())
    return 2*common/(sum(e.values())+sum(p.values())) if e and p else float(e == p)


def summarize(rows):
    valid = correct = answerability_correct = false_answers = refused_answerable = 0
    unknown = known = 0
    f1 = []
    for row in rows:
        target, prediction = row["target"], row.get("prediction")
        known += target["answerable"]
        unknown += not target["answerable"]
        if prediction:
            valid += 1
            same_flag = target["answerable"] == prediction["answerable"]
            answerability_correct += same_flag
            correct += same_flag and normalize(target["answer"]) == normalize(prediction["answer"])
            false_answers += not target["answerable"] and prediction["answerable"]
            refused_answerable += target["answerable"] and not prediction["answerable"]
        if target["answerable"]:
            f1.append(token_f1(target["answer"], prediction["answer"]) if prediction and prediction["answerable"] else 0.0)
    n = len(rows)
    latency = [r["elapsed_ms"] for r in rows]
    return {"examples": n, "valid_responses": valid, "errors": n-valid,
            "valid_response_rate": valid/n if n else None,
            "normalized_exact_accuracy": correct/n if n else None,
            "answerability_accuracy": answerability_correct/n if n else None,
            "answerable_examples": known, "unanswerable_examples": unknown,
            "token_f1_on_answerable": statistics.mean(f1) if f1 else None,
            "false_answers_when_unanswerable": false_answers,
            "false_answer_rate_when_unanswerable": false_answers/unknown if unknown else None,
            "refusals_when_answerable": refused_answerable,
            "median_latency_ms": statistics.median(latency) if latency else None,
            "within_five_seconds_rate": sum(t <= 5000 and bool(r.get("prediction")) for t, r in zip(latency, rows))/n if n else None,
            "latency_scope": "cloud request and response validation; not Android capture-to-speech",
            "error_policy": "Invalid outputs and API errors count as incorrect, never as valid abstentions"}


def user_contents(row):
    from google.genai import types
    # Deliberately never pass the role=model reference answer to Gemini.
    return [types.Content.model_validate(row["user"])]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--train", type=Path, required=True)
    p.add_argument("--validation", type=Path, required=True)
    p.add_argument("--test", type=Path, required=True)
    p.add_argument("--split", choices=["validation", "test"], default="test")
    p.add_argument("--limit", type=int, help="Run only the first N examples for a live smoke check")
    p.add_argument("--project", default=qa.PROJECT)
    p.add_argument("--base-model", default=qa.BASE_MODEL)
    p.add_argument("--base-location", default="global")
    p.add_argument("--tuned-model", default=qa.TUNED_MODEL)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    train, validation, test = [load_sft(path) for path in (a.train, a.validation, a.test)]
    assert_held_out(train, validation, test)
    records = test if a.split == "test" else validation
    total_examples = len(records)
    if a.limit is not None:
        if a.limit < 1:
            p.error("--limit must be positive")
        records = records[:a.limit]
    if a.output.exists() and any(a.output.iterdir()):
        raise ValueError("Choose a new empty output folder")
    a.output.mkdir(parents=True, exist_ok=True)
    variants = [("base", a.base_model, a.base_location),
                ("tuned", a.tuned_model, qa.serving_location(a.tuned_model))]
    rows = {"base": [], "tuned": []}
    # Alternate first caller to reduce a fixed ordering bias in timing.
    for index, record in enumerate(records):
        ordered = variants if index % 2 == 0 else list(reversed(variants))
        for variant, model, location in ordered:
            started = time.perf_counter()
            row = {"line": record["line"], "image_uri": record["image_uri"],
                   "target": record["target"], "model": model, "location": location}
            try:
                text = qa.generate_answer(a.project, model, location, user_contents(record))
                row["raw_response"] = text
                row["prediction"] = qa.parse_answer(text).model_dump()
            except Exception as error:
                row["prediction"] = None
                status, detail = qa.failure_status(error)
                if isinstance(error, (ValueError, TypeError)):
                    status, detail = 502, "Invalid answer JSON or contract"
                row["error"] = {"type": type(error).__name__, "status": status, "detail": detail}
            row["elapsed_ms"] = round((time.perf_counter()-started)*1000, 2)
            rows[variant].append(row)
            with (a.output/(variant+"_predictions.jsonl")).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False)+"\n")
            print(f"{index+1}/{len(records)} {variant}: {'valid' if row['prediction'] else 'error'}", flush=True)
    report = {"split": a.split, "project": a.project,
              "available_examples": total_examples,
              "evaluation_scope": "first-N smoke check" if len(records) < total_examples else "full split",
              "input_policy": "Exactly the user image and prompt from held-out SFT JSONL; references excluded",
              "split_check": "No shared image URIs. Product identity, renamed/near-duplicate images not audited",
              "sources_sha256": {key: hashlib.sha256(path.read_bytes()).hexdigest()
                                  for key, path in [("train", a.train), ("validation", a.validation), ("test", a.test)]}}
    for variant, model, location in variants:
        report[variant] = {"model": model, "location": location, **summarize(rows[variant])}
    report["tuned_minus_base_exact_accuracy"] = (report["tuned"]["normalized_exact_accuracy"]-
                                                report["base"]["normalized_exact_accuracy"])
    (a.output/"comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
