# Held training review — November 17, 2026

All 113 previously held training crops were visually rechecked at their original resolution under the user's instruction to review and fix them autonomously.

| Result | Examples |
| --- | ---: |
| Previously accepted training examples, preserved exactly | 287 |
| Held examples rechecked | 113 |
| Recovered for the future candidate | 112 |
| Recovered with some fields still unknown | 104 |
| Recovered as all-unknown / rescan examples | 6 |
| Recovered with all four fields readable | 2 |
| Still excluded | 1 |
| **Future training candidate** | **399** |

The 399 examples cover 165 product families. They remain in the original training split. A recovered example does not imply that every field became readable: unknown fields are deliberately retained. The six all-unknown examples provide abstention/rescan targets for unusable views. Case 308 remains excluded because its visible Arabic branding could not be transcribed confidently; it is not mislabeled as an all-unknown image.

The recovered targets change 126 field values: 49 product names, 51 brands, 17 sizes, and 9 best-by dates. This includes removing 35 unsupported values. Other adjustments correct evidence, confidence, and rescan guidance.

Examples of corrections:

- Retail dates marked “packed on” are not labeled as best-by dates.
- Halo Top's 300-calorie claim and protein-gram claims are not package weights.
- Recipe ingredients, advertised neighboring products, and distributor addresses do not establish the selected product's identity.
- Cropped brand endings and illegible small print remain unknown; text is not completed from another photograph.
- Explicit “Best if used by” dates on Mission packages are retained, including the year.

## Files

- Final decisions and exact image/source bindings: `model_dev/held_training_fixes_20261117.json`.
- Before-and-after gallery: `runs/gemini_product_v4_expanded_review_20261117/review.html`. Open locally; search by product, case number, or note. Each image opens at its original resolution.
- Local training candidate: `runs/gemini_product_v4_expanded_review_20261117/dataset/`, containing `examples.jsonl`, `train.jsonl`, images, changes, exclusion, instruction, and a manifest with hashes.
- Reproducible local exporter: `model_dev/prepare_expanded_product_run.py`.

The earlier `model_dev/held_training_review_20261117.json` is the initial five-case proposal snapshot. The final decisions are in `held_training_fixes_20261117.json` and supersede those proposals under the user's later delegation. They are assistant-reviewed, not independently human-verified ground truth.

## Verification and limits

All candidate targets pass the application's reading contract. The exporter checks source/image hashes, complete review coverage, and product-family, original-photo, and exact-image leakage between training and validation. The previous 287 records are preserved exactly; raw OCR and image bytes are unchanged. The original audit and frozen training-request file hashes remain unchanged.

Validation labels and the final-test set were not edited or added to training. Existing accuracy scores are unchanged; dataset review alone does not establish a model improvement. The validation reference-policy issues documented in the prior review still need resolution for a fair future comparison.

This work creates a local candidate only. It makes no cloud calls, uploads nothing, starts no additional paid training, and does not change the previously submitted 287-example, two-epoch job or app backend. Cloud Storage URIs in the candidate are planned locations for a future separately authorized run.
