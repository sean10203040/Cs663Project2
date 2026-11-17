# Product extraction tuning run — November 13, 2026

The user approved uploading 400 training and 155 validation examples to the
specified private Cloud Storage prefix and submitting one paid training epoch.
No additional tuning run has been authorized. The existing QA model is retained.

## Submitted experiment

- Project: `spatial-thinker-512218-b0`.
- Base model: `gemini-3.5-flash`.
- Job: `projects/1056598944825/locations/us/tuningJobs/9081316234057744384`.
- Display name: `LabelLens-product-v3-compact400-20261113-r1`.
- Training location: `us` multi-region, using the documented `.rep.googleapis.com` endpoint.
- Epochs: 1; adapter size: 4; learning-rate multiplier: 1.0.
- Export the last checkpoint only. This is one pilot run, not a checkpoint search.
- Submitted at 23:24 UTC; running at 23:25 UTC on November 13.
- Task: one selected crop plus original ML Kit OCR to structured product fields,
  evidence sources/quotes, subjective certainty, and optional rescan guidance.

The job succeeded on November 14 at 15:57:36 UTC (7:57 AM Pacific), about
16 hours 32 minutes after training started. Its serving endpoint is
`projects/1056598944825/locations/us/endpoints/6152796700290318336`;
the model is `projects/1056598944825/locations/us/models/8105423798104227840@1`.
No second training job was submitted.

Paired validation completed November 15. Complete valid responses increased
from 91.0% to 97.4%, and product-name exact matching increased from 41.9% to
50.3%. All-four-field matching increased only from 16.1% to 18.1%; its descriptive
group-bootstrap interval includes zero improvement. The tuned model was slower
and returned more values against blank references. See the
[full paired report](PRODUCT_VALIDATION_20261115.md) before making quality claims.

The validated endpoint was connected November 15 on existing Cloud Run service
`labellens-qa`, revision `labellens-qa-00004-nmx`. Live checks passed for base and
tuned extraction, paired comparison and the separate original QA model. The
app URL and token are unchanged. This deployment did not submit further training.

## Dataset lineage

Source release: **LabelLens Dataset — November 13, 2026**. The original ZIP and
its annotations were preserved. Only the compact training and validation images
were staged; the held-out and OCR stress sets were not uploaded or invoked.

| Split | Examples | Recorded product families |
|---|---:|---:|
| Compact training | 400 | 165 |
| Validation | 155 | 18 |

All selected image hashes and remote JSONL checksums were verified. Recorded
family IDs are disjoint across splits. This does not independently prove the
absence of aliases or near duplicates assigned to different families.

The 14 pre-existing visual holds in the full training pool are outside this
compact selection. An additional assistant visual review of 25 flagged crops
corrected 26 evidence sources from OCR to image; field values and raw OCR were
unchanged. For example, **Silk** was visible on the carton, while the supplied OCR
only matched that string inside **SILKY**. Decisions are preserved in
`model_dev/evidence_review_20261113.json`. They are assistant visual checks, not
an independent human reannotation of the complete dataset.

## Reproducibility

- Prompt: `labellens-evidence-v3`, copied byte-for-byte from the dataset prompt.
- Instruction SHA-256: `26fe52aadff5bacdec159e52bef97a2447b77266284c118288af4b88128d51a8`.
- Prepared train JSONL SHA-256: `200e8ea0d7be7f4d6c594d5a4712786b80117024e03ea7164dc56d74be0067f0`.
- Prepared validation JSONL SHA-256: `b6798dc8ba191d4b9892a1c6d143074d39819b016fa24fa04eef5f225c90ab16`.
- Cloud prefix: `gs://labellens-spatial-thinker-512218-b0/product-extraction/20261113-v3-compact400-r1/`.
- Local run state, prepared data and evaluation output: `runs/gemini_product_v3_compact400_20261113/` (Git ignored).
- The original extracted subset is in `data/incoming/labellens_20261113/` (Git ignored).

Prepare the derivative locally using `model_dev.prepare_product_run`. The
preparation step validates prompt/target correspondence, image hashes, split
separation and review patches before producing the training files. It never
opens the final-test manifests. The tuning CLI refuses to submit if its job
record already exists, and API submissions have automatic retries disabled.
After an ambiguous network failure, list jobs before attempting another submission.

For a new checkout, the optional `--archive` argument stages only selected
train/validation inputs from the nested release ZIP into a new `--source` folder.
Use a new `--output` folder and the same review-patch file, then compare the
resulting data hashes with the frozen run manifest. Preparation is local; upload
and paid training remain separate commands.

## Evaluation protocol

Base and tuned models are compared on all 155 validation examples with identical
image bytes, actual OCR, prompt and generation settings. Input hashes accompany
each prediction. Reference answers are used only for scoring, not sent to either
model. API/format/evidence failures stay in accuracy denominators.

The fixed extraction inference policy is temperature 0, maximum output 1,600
tokens, HIGH image resolution and MINIMAL thinking. Neither side uses controlled
JSON/schema generation: JSON is taught by the training prompt and targets. OCR
evidence uses word boundaries to prevent a brand being accepted merely because
it appears inside another word. The same policy is shared by evaluation and the
backend extraction route. QA is a different task with a separate prompt/config.

Validation measures field accuracy/precision/recall, all-field accuracy, response
validity, unsupported values on absent fields, median latency, and condition
breakdowns where condition labels exist. Leave the final phone test and OCR stress cases
for the frozen final evaluation; detector misses must remain in full-system
failure counts even though they cannot be sent as crop-only Gemini requests.

### Completed base validation

The base model was invoked once on all 155 validation examples. With fixed strict
case/whitespace-normalized matching, 141 responses (90.97%) passed the complete
format/evidence contract, and 25 (16.13%) matched all four reference fields.
Median cloud response time was 1.76 seconds, excluding phone/backend transport.

These are strict reference agreement rates, not human-judged semantic accuracy.
For example, returning English and French product/brand wording can fail exact
matching against an English-only reference even when both languages are printed.
Some archived null references may also warrant independent visual adjudication.
Reference data and scoring are frozen for this paired run; no prompts, training
settings or labels were changed in response to this baseline. Treat metrics
about values on absent reference fields as reference disagreements until
visual review establishes whether the prediction or reference is wrong.

These validation manifests do not supply the proposal's six physical packaging
condition labels; the current condition breakdown is therefore `unspecified`.
Condition-specific claims about curvature, damage, glare and occlusion require
additional annotations or the original source workspace. This pilot cannot
establish that every proposed degradation category improved.

## Budget

The user approved one epoch with an approximate training estimate of $7–$9 before
credits, plus validation/inference. This is an estimate, not an invoice or spending
cap enforced by Google. Google lists Gemini 3.5 Flash tuning at $0.01 per 1,000
training tokens; token count and epochs determine the actual training charge.
The user reported approximately $295 in educational credits. The remaining
balance and eligibility of those credits for tuning have not been independently
verified. Credit availability does not authorize additional runs.

Google's job statistics subsequently reported 400 examples and 699,130 billable
training tokens. At the published rate this implies approximately **$6.99 in
training charges before credits**, excluding validation/inference. This is a
rate-based calculation from job statistics, not a verified billing statement.

Sources: [Google tuning limits and settings](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tuning/supervised-tuning),
[image tuning format](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tuning/image),
[pricing](https://cloud.google.com/model-garden/pricing).
