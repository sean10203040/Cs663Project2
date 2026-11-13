# Google Cloud inspection: November 11, 2026

Observed in the signed-in Google Cloud console; this inspection did not create,
deploy, tune, or invoke a model, modify billing, or change permissions.

## Existing resources

- Project display name: Fine-Tuning-Gemini
- Project ID: spatial-thinker-512218-b0
- Project number: 1056598944825
- Free trial was active at inspection.
- Tuning job: projects/1056598944825/locations/us-central1/tuningJobs/5156565025799798784
- Display name: FineTunedModel
- Status: Succeeded
- Base model: gemini-3.5-flash
- Created October 30, 2026, 4:54:19 PM; ended 7:33:31 PM as displayed by console.
- One supervised tuning epoch; learning-rate multiplier 1; adapter size 4.
- Training URI: gs://labellens-spatial-thinker-512218-b0/datasets/train.jsonl
- Validation URI: gs://labellens-spatial-thinker-512218-b0/datasets/validation.jsonl
- Dataset tab reported 100 messages/examples, each containing two messages,
  and 123,871 total tokens. This is not a verified count of distinct products or images.
- Registered model: projects/1056598944825/locations/us/models/4818710863798075392@1
- Serving endpoint listed as Active:
  projects/1056598944825/locations/us/endpoints/1423735616574586880

The tuning-job region is us-central1, but this existing model's serving endpoint
is in us. Do not assume the tuning and serving regions match.

## Observed training contract

The first three previews instruct LabelLens to answer a question using only the
supplied image and return exactly:

```json
{"answer": "short answer or unanswerable", "answerable": true}
```

For an unanswerable image, the instruction requires answer="unanswerable" and
answerable=false. The preview included two unanswerable responses and one
"deer park" response. Three previews do not establish dataset quality, class
balance, independent validation/test splits, or model accuracy. Full prompts,
questions, source images, and targets have not been audited.

## Integration decision

The user selected Option A: use the existing model first. The source now contains
a separate /v1/answer route, Android question input, and held-out QA evaluator.
See GEMINI_SETUP.md. The exact full training prompt still needs extraction from
the original JSONL; the console preview was truncated and browser downloads did
not complete. No cloud request or deployment has been made by this code update.

The older backend/contracts.py and extraction evaluation scripts expect
product_name, brand, key_attributes, confidence, guidance, and evidence, with
image plus OCR inputs. The existing tuned model was trained on a different
image-question/answer contract. Merely setting LABELLENS_TUNED_MODEL to its endpoint
will not make these formats compatible. The new QA route uses separate
LABELLENS_QA_* settings and strict answer/answerable validation instead.

Option A: add a separate question-answer mode with the exact training prompt,
compare base gemini-3.5-flash and this endpoint on identical held-out questions,
then connect the corresponding Android question/answer interface.

Option B: keep the richer product extraction interface and prepare reviewed
examples matching that contract for a new tuning job. Preserve the existing
model as a previous experiment. No new job is necessary just to inspect or reuse
the existing one.

Neither model inference, endpoint authentication, nor the proposed Android/backend
integration was tested during this inspection.

Console pages:
- https://console.cloud.google.com/agent-platform/tuning/locations/us-central1/tuningJob/5156565025799798784/detail?project=spatial-thinker-512218-b0
- https://console.cloud.google.com/agent-platform/models/locations/us/models/4818710863798075392/versions/1/deploy?project=spatial-thinker-512218-b0
