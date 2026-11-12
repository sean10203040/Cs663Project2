# Live Gemini comparison — November 11, 2026

Actual Google Cloud inference using the existing models. No training or deployment was performed.

Split: **validation**. Scope: **full split**.

Both models received the same original image URI and question prompt. Reference answers were used only for scoring.

| Metric | Base Gemini | Fine-tuned Gemini |
|---|---:|---:|
| Examples | 20 | 20 |
| Valid JSON responses | 20 | 20 |
| API / invalid-output errors | 0 | 0 |
| Normalized exact-match accuracy | 65.0% | 65.0% |
| Token F1 on answerable examples | 80.2% | 77.0% |
| Answerability accuracy | 95.0% | 95.0% |
| False answers on unanswerable examples | 0 | 0 |
| Median cloud response time | 3.20 s | 5.64 s |

## Interpretation limits

- Exact match ignores capitalization and repeated whitespace, but still penalizes additional words and equivalent wording. Token F1 measures word overlap, not semantic correctness.
- API failures and invalid outputs remain in accuracy denominators. An unanswerable response is not automatically correct.
- This small validation comparison does not establish a reliable improvement from fine-tuning. Inspect the individual answers and source images.
- Training, validation, and test contain 100, 20, and 30 examples. No shared image URIs were found; product overlap and renamed or near-duplicate images remain unaudited.
- The 30 final-test examples were not invoked in this validation run.
- Timings cover cloud inference and response parsing, excluding phone capture, detection, OCR, backend transport, and speech.
- This tests the Gemini image-question task, not the complete Android pipeline or a deployed Cloud Run backend.

## Individual answers

| Example | Reference | Base answer | Tuned answer |
|---|---|---|---|
| 1 | salmon basil | salmon with basil | salmon with basil |
| 2 | chocolate | Chocolate | Chocolate |
| 3 | mango | mango | mango |
| 4 | pork beans | Van Camp's Pork and Beans | Van Camp's Pork and Beans |
| 5 | toffee cheesecake | Toffee Cheesecake | Toffee Cheesecake |
| 6 | blueberry | Blueberry | Blueberry |
| 7 | unanswerable | unanswerable | unanswerable |
| 8 | unanswerable | unanswerable | unanswerable |
| 9 | vanilla | vanilla | vanilla |
| 10 | almond | almond | almond |
| 11 | gevalia | Gevalia Swiss Hazelnut | yes |
| 12 | honey nut cheerios | Honey Nut Cheerios | Honey Nut Cheerios |
| 13 | nutmeg | ground nutmeg | ground nutmeg |
| 14 | unanswerable | unanswerable | unanswerable |
| 15 | chicken broccoli cheese potato | Chicken Broccoli Cheese with Potato | Chicken Broccoli Cheese with Potato |
| 16 | dunkin donuts | unanswerable | unanswerable |
| 17 | unanswerable | unanswerable | unanswerable |
| 18 | ballatore | Ballatore | Ballatore |
| 19 | creamy chicken | Creamy Chicken | Creamy Chicken |
| 20 | classico | Classico Tomato & Basil | Classico Tomato & Basil |

## Resources

Base: `gemini-3.5-flash` (global).

Tuned: `projects/1056598944825/locations/us/endpoints/1423735616574586880` (us).

Raw responses, per-example timing, source hashes, and metric definitions are in the accompanying prediction JSONL files and comparison.json.
