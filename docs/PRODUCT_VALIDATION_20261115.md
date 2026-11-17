# Product extraction: base versus tuned validation

One approved training epoch on 400 examples. Validation contains 155 examples from 18 recorded product families. Final-test cases were not invoked.

Both models received the same crop bytes, actual OCR, evidence-v3 prompt and generation settings. Reference answers were used only for scoring. Input hashes and references were verified to match.

| Metric | Base Gemini | Product-extraction fine-tune |
|---|---:|---:|
| Valid complete response | 91.0% | 97.4% |
| All four fields exact | 16.1% | 18.1% |
| product_name exact | 41.9% | 50.3% |
| brand exact | 56.1% | 60.0% |
| size exact | 59.4% | 61.3% |
| best_by exact | 78.1% | 81.9% |
| Values returned on absent reference fields | 20.8% | 23.5% |
| Median cloud response | 1.76 s | 2.06 s |

Paired all-field outcomes: tuned-only correct on 5 cases; base-only correct on 2; tied on 148.

Format/evidence compliance: 10 base failures became valid tuned responses; 0 valid base responses became tuned failures. Among cases valid for both models, tuned-only exact on all four fields: 3; base-only exact: 2.

All-field exact-match difference: +1.9 percentage points. Descriptive 95% group-bootstrap interval: -0.9 to +5.0 points, resampling recorded product families.

## Interpretation limits

- Exact matching normalizes case/whitespace only. Extra bilingual text, equivalent units and alternate wording can be correct to a person while failing this metric.
- Complete-response failures remain in every accuracy denominator. Improvements in JSON/evidence compliance are useful but do not by themselves prove better visual recognition.
- A value disagreeing with a null reference is not a proven hallucination until the image/reference has been independently checked. Some archived reference policies need adjudication.
- This is validation, not an untouched final-test result or phone accessibility study. Multiple views share product families; the descriptive interval is not a guarantee of real-world performance.
- Cloud timings exclude phone capture, OCR, backend transport and speech. Reported confidence is subjective, not calibrated accuracy.
- Base serving uses the global route; the tuned endpoint's serving location is taken from its resource name. Latency compares these deployments and does not isolate the effect of training from network/region differences.
- The existing question-answer fine-tune is a separate model and was not replaced by this experiment.

Raw predictions/errors, exact input fingerprints, provenance, per-field precision/recall and paired outcomes are retained locally in the run's validation folder.

A subsequent [visual error review](PRODUCT_ERROR_REVIEW_20261115.md) categorizes
the disagreements without changing these frozen references, predictions or scores.
