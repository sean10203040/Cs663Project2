# Product v4 training preparation — November 15, 2026

The first visual review of all 400 compact training crops produced a **local
candidate of 287 examples from 135 product families**. It is a separate derivative,
not a replacement for the completed v3 experiment. No cloud upload, inference,
training or deployment was performed for this preparation.

## Review outcome

| Disposition | Examples | Meaning |
|---|---:|---|
| Retain | 194 | Existing target retained after first-pass visual screening |
| Revise | 93 | Proposed target/evidence changes recorded against the original |
| Hold | 113 | Excluded pending closer transcription or field-role adjudication |
| Candidate total | 287 | Retained plus revised, all originally in training |

The revisions cover 108 field patches: 45 product-name, 18 brand, 25 package-size
and 20 date patches. An evidence-only change also counts as a field patch.
Original images and noisy OCR are preserved byte-for-byte. Each review decision
is bound to its original record and crop by SHA-256 hashes.

Review was performed by the assistant using eight-image contact sheets, with
selected original-resolution rechecks. **These are provisional review decisions,
not independently verified human ground truth.** Retaining an example does not
guarantee that every printed field was exhaustively transcribed. Small-print,
partial-view and language ambiguities are reasons to hold a row rather than
invent an answer. The 113 held rows are not 113 proven annotation errors.

## What changed

The [candidate field policy](PRODUCT_FIELD_POLICY_V4.md) defines consumer brand,
printed identity/variant, explicit package quantity/count, date roles, and
evidence. Its matching candidate prompt lives in `model_dev/product_policy_v4.py`.

Examples of proposed corrections, identified by review number:

- #3: retain the visible medicine strength in **Ibuprofen Tablets 200 mg**.
- #11: retain both printed quantities, **100 g (3.2 oz)**, even though the
  package's own conversion is unusual. Never silently repair printed numbers.
- #79 and #80: date transcription changes from MA to visibly printed MR;
  preserve the best-before heading and original month-code ambiguity.
- #207: add the readable **100 Tablets** package count instead of null.
- #212–215: preserve the explicitly printed **3 x 625 count (1875 swabs)**.
- #385–386: retain the visible **Salt-Free** seasoning variant.

Holds include #263, where a prominent **300 CALORIES** claim appears to have
become a 300 g size target; #324, whose visible logo conflicts with the existing
brand answer; and rear/covered labels whose identity or quantity needs closer
confirmation. Proposed descriptor expansions for #369–374 were excluded after
original-resolution checks could not establish the small wording reliably.

## Local artifacts

- `model_dev/training_review_20261115.json`: all 400 decisions, original record
  hashes, proposed field values, evidence and explanations. This is versionable;
  it contains no photos, raw OCR transcripts or credentials.
- `runs/gemini_product_v4_reviewed_20261115/dataset/`: ignored local export with
  `examples.jsonl`, multimodal `train.jsonl`, unchanged crop images,
  `instruction.txt`, `changes.json`, `held_for_review.json`, and `manifest.json`.
- `.tools/training_review_20261115/review.html`: local before/after photo gallery,
  filterable by disposition, ID, family or explanation; includes held rows.

The `gs://` paths in the export are **planned destinations only**. Nothing has
been uploaded there. The manifest records that this is a candidate and that
independent validation-policy review remains before a paid run.

## Safeguards and verification

`model_dev/prepare_product_v4.py` refuses changed source records/images/policy,
incomplete or duplicate decisions, validation IDs in training, false OCR quotes,
cross-split family/photo/crop overlap, and nonempty output folders. It validates
the entire candidate before writing the export. Validation images are read only
to check separation; no validation labels are changed or exported into training.
Final-test files are not read. The production v3 prompt and saved predictions
remain unchanged.

All 39 Python tests pass, including seven candidate-preparation tests covering
source integrity, split separation, held examples, evidence validation and policy
selection. The evaluator now accepts explicit `--policy v4`; its default stays
v3, and resume checks reject a changed prompt. No Android rebuild is required
for this offline preparation.

## Before another training run

1. Have a teammate check the proposed corrections and the flagged validation
   references against the field policy. Resolve held rows only from their own
   selected inputs. They may remain excluded if uncertain; do not fill them from
   another view or promote validation families into training.
2. Freeze an independently checked evaluation reference version. The existing
   v3 strict results stay published. If v4 changes reference wording or scoring,
   apply that version identically to both models and report the measurement
   change separately from model improvement.
3. Choose the next experiment after checking coverage. The candidate drops from
   400 to 287 examples and from 165 to 135 families. Cleaner labels are a
   hypothesis for improvement, and reduced coverage may hurt performance.
4. Estimate the concrete run and authorize its upload/training cost. The earlier
   approval covered the already completed one-epoch run. There is no new job.
5. Compare base and newly tuned models with identical frozen v4 instructions,
   inputs and generation settings. Keep final-test data untouched until model
   selection ends. Deploy only after that comparison supports the change.

This work improves experiment preparation. It does not increase the existing
50.3% product-name exact-match score or establish an accuracy gain by itself.

## User approval and next-run estimate

The user explicitly approved all 93 proposed training corrections in chat.
`model_dev/training_review_20261115_approval.json` binds that approval to the
review audit and candidate file hashes. The 113 held examples remain excluded.
This records approval of the proposed labels, not a claim of independent
reannotation or authorization for another paid cloud job.

A one-epoch planning estimate is approximately $6–$9 for training before credits,
excluding validation/inference and storage. The central estimate is about
614,000 tokens ($6.14 at $0.01 per 1,000 training tokens). It is calibrated to the
previous run's actual 699,130 billable tokens, with a rough four-characters-per-
text-token approximation and previous per-image residual overhead. This is not
an exact tokenizer result or spending cap. The longer v4 instructions mean cost
does not fall in direct proportion to the smaller example count.

The price was checked against [Google Cloud model-tuning pricing](https://cloud.google.com/model-garden/pricing).
The local estimate and assumptions are saved in the ignored run's
`cost_estimate.json`. No new training job or upload has started.
