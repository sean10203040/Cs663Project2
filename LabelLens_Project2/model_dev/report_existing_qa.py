"""Write a readable report from saved predictions without making model calls."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads((args.results / "comparison.json").read_text(encoding="utf-8"))
    records = {
        variant: [json.loads(line) for line in (args.results / (variant + "_predictions.jsonl")).read_text(encoding="utf-8").splitlines() if line]
        for variant in ("base", "tuned")
    }
    text = ["# Live Gemini comparison — November 11, 2026", "",
            "Actual Google Cloud inference using the existing models. No training or deployment was performed.", "",
            f"Split: **{report['split']}**. Scope: **{report.get('evaluation_scope', 'full split')}**.", "",
            "Both models received the same original image URI and question prompt. Reference answers were used only for scoring.", "",
            "| Metric | Base Gemini | Fine-tuned Gemini |", "|---|---:|---:|"]
    for title, key, style in [
        ("Examples", "examples", "count"),
        ("Valid JSON responses", "valid_responses", "count"),
        ("API / invalid-output errors", "errors", "count"),
        ("Normalized exact-match accuracy", "normalized_exact_accuracy", "percent"),
        ("Token F1 on answerable examples", "token_f1_on_answerable", "percent"),
        ("Answerability accuracy", "answerability_accuracy", "percent"),
        ("False answers on unanswerable examples", "false_answers_when_unanswerable", "count"),
        ("Median cloud response time", "median_latency_ms", "time"),
    ]:
        values = []
        for variant in ("base", "tuned"):
            value = report[variant][key]
            values.append("N/A" if value is None else f"{value:.1%}" if style == "percent" else f"{value / 1000:.2f} s" if style == "time" else str(value))
        text.append(f"| {title} | {' | '.join(values)} |")
    text += ["", "## Interpretation limits", "",
             "- Exact match ignores capitalization and repeated whitespace, but still penalizes additional words and equivalent wording. Token F1 measures word overlap, not semantic correctness.",
             "- API failures and invalid outputs remain in accuracy denominators. An unanswerable response is not automatically correct.",
             "- This small validation comparison does not establish a reliable improvement from fine-tuning. Inspect the individual answers and source images.",
             "- Training, validation, and test contain 100, 20, and 30 examples. No shared image URIs were found; product overlap and renamed or near-duplicate images remain unaudited.",
             "- The 30 final-test examples were not invoked in this validation run.",
             "- Timings cover cloud inference and response parsing, excluding phone capture, detection, OCR, backend transport, and speech.",
             "- This tests the Gemini image-question task, not the complete Android pipeline or a deployed Cloud Run backend.",
             "", "## Individual answers", "",
             "| Example | Reference | Base answer | Tuned answer |", "|---|---|---|---|"]
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    base = {row["line"]: row for row in records["base"]}
    tuned = {row["line"]: row for row in records["tuned"]}
    for line, row in base.items():
        other = tuned[line]
        if row["image_uri"] != other["image_uri"] or row["target"] != other["target"]:
            raise ValueError("Mismatched comparison examples")
        answers = [cell(item["prediction"]["answer"] if item.get("prediction") else "ERROR") for item in (row, other)]
        text.append(f"| {line} | {cell(row['target']['answer'])} | {' | '.join(answers)} |")
    text += ["", "## Resources", "", f"Base: `{report['base']['model']}` ({report['base']['location']}).", "",
             f"Tuned: `{report['tuned']['model']}` ({report['tuned']['location']}).", "",
             "Raw responses, per-example timing, source hashes, and metric definitions are in the accompanying prediction JSONL files and comparison.json.", ""]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(text), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
