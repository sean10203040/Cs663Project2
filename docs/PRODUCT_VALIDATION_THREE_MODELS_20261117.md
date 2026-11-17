# Product extraction: three-model validation — November 17, 2026

Both two-epoch training jobs succeeded. All three models were evaluated on the same 155 validation crops from 18 recorded product families using the evidence-v4 candidate prompt, the same original OCR and generation settings. Model inputs, references and prompt hashes were verified to match. No final-test data was invoked and no app/backend deployment was performed.

**These are strict matches against frozen references, not independently adjudicated semantic accuracy.** The existing reference-policy and visibility flags remain unresolved. The earlier evidence-v3 results are a separate experiment and must not be used as a before/after comparison for these numbers.

## Results after bounded service retries

| Metric | Base Gemini | 287 examples, 2 epochs | 399 examples, 2 epochs |
| --- | ---: | ---: | ---: |
| Valid complete JSON/evidence response | 96.1% | 69.7% | 89.0% |
| All four fields exact | 16.8% | 21.9% | 27.1% |
| product_name exact | 38.1% | 40.0% | 47.1% |
| brand exact | 65.2% | 49.7% | 63.9% |
| size exact | 65.8% | 57.4% | 76.8% |
| best_by exact | 76.1% | 57.4% | 72.9% |
| Values returned on absent reference fields | 13.5% | 8.5% | 4.2% |
| Median duration of successful responses | 3.67 s | 2.39 s | 1.81 s |

All 155 examples remain in each accuracy denominator, including invalid outputs and any unresolved service failures. Exact matching normalizes only case and whitespace. Equivalent typography, alternate wording, additional qualifiers, quantity formatting and date headings can fail exact matching. A value returned against a null reference is not a proven hallucination without image/reference adjudication.

## Paired all-field comparisons

- tuned287_vs_base: 13 wins, 5 losses, 137 ties; net +5.2 percentage points. Descriptive 95% product-family bootstrap interval: -1.1 to +10.6 points.
- tuned399_vs_base: 23 wins, 7 losses, 125 ties; net +10.3 percentage points. Descriptive 95% product-family bootstrap interval: -2.2 to +21.2 points.
- tuned399_vs_tuned287: 16 wins, 8 losses, 131 ties; net +5.2 percentage points. Descriptive 95% product-family bootstrap interval: -3.5 to +13.8 points.

These descriptive intervals resample the 18 recorded product families. They do not resolve reference-label problems or establish generalization to unseen users/packaging.

## Service failures versus model failures

First attempts remain untouched. Only temporary capacity/transport failures received up to two additional attempts, sequentially with two-second spacing, using identical inputs and settings. Wrong answers and contract/evidence rejections were never retried for a better answer. The bounded retry policy and every additional attempt are recorded separately.

| Variant | First-attempt valid response | Temporary service failures initially | Additional calls | Service failures remaining | Final contract/other failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| base | 89.0% | 12 | 12 | 0 | 6 |
| tuned287 | 69.7% | 0 | 0 | 0 | 47 |
| tuned399 | 89.0% | 0 | 0 | 0 | 17 |

Latency is the successful API-call duration, excluding earlier failed attempts, phone capture, OCR, backend transport and speech. Base uses the global serving route; the tuned models use their US endpoints. This measures these deployments, not training alone.

## Next decision

Use this report as a diagnostic comparison. Resolve the previously flagged validation-reference cases under the v4 field policy and rescore all saved predictions identically before making a strong accuracy claim or selecting a winner on exact-match scores alone. Evidence-contract validity is separately measurable without treating the frozen label as semantic ground truth. Keep the final-test split untouched until model selection is complete.

The app still uses its existing backend configuration. A selected v4 model must be served with its evaluated v4 prompt; training completion alone does not update the app.

Detailed metrics, first attempts, effective predictions, errors, retry ledger, frozen plan and cloud job snapshots are retained in `runs/gemini_product_v4_comparison_20261117/`.
