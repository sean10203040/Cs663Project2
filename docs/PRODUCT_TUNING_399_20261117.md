# Corrected 399-example Gemini run — November 17, 2026

Submitted successfully to Google Cloud and independently retrieved by job name immediately after submission.

- Display name: `LabelLens-product-v4-reviewed399-e2-20261117-r1`
- Job: `projects/1056598944825/locations/us/tuningJobs/4968016846268661760`
- Created: `2026-11-17T21:22:26.026978Z`
- Submission-time status: `JOB_STATE_PENDING` (queued, not a completion claim).
- Base model: `gemini-3.5-flash`; two epochs, adapter size four, learning-rate multiplier 1.0; intermediate checkpoint export enabled.
- Training: 399 corrected examples, including 112 recovered held examples. Case 308 remains excluded.
- Validation: existing 155-example validation set reused separately; no final-test data included.
- Uploaded: 400 objects (399 images and training JSONL), 113,488,893 bytes, all verified against local hashes and remote MD5 metadata.
- Authorization: user's explicit request to start another 399-image, two-epoch training run; no additional confirmation required.

The previous 287-example job `2465141353357508608` was checked before this submission: `JOB_STATE_SUCCEEDED`, ending `2026-11-17T20:45:55.154551Z`. The new run starts from the same foundation model; it does not resume or overwrite that previous job. No app/backend deployment was performed.

Local records: `runs/gemini_product_v4_reviewed399_e2_20261117/` contains the hash-bound plan, upload manifest and receipts, submission guard, and saved cloud job response. Candidate data remains in `runs/gemini_product_v4_expanded_review_20261117/dataset/`.

Existing validation reference-policy concerns remain as documented in the review. Compare the completed models on the same independently adjudicated references before claiming a measured improvement. Cloud accepted the job without a billing/credit error; remaining credits were not verified.

Console: https://console.cloud.google.com/agent-platform/generative/language/tuning?project=spatial-thinker-512218-b0

To inspect the job without resubmitting:

```powershell
.\.venv\Scripts\python.exe -m model_dev.tune_gemini --project spatial-thinker-512218-b0 --location us --job projects/1056598944825/locations/us/tuningJobs/4968016846268661760 --output runs/gemini_product_v4_reviewed399_e2_20261117/tuning_job.json
```
