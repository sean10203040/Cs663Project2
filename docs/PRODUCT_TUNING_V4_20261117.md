# Gemini v4 two-epoch training — November 17, 2026

Google accepted and independently returned this new job:

- Job: `projects/1056598944825/locations/us/tuningJobs/2465141353357508608`
- Display name: `LabelLens-product-v4-reviewed287-e2-20261117-r1`
- Confirmed submission state: `JOB_STATE_PENDING` (queued; this is a submission snapshot, not live status).
- Created: `2026-11-17T20:20:22.727808Z`.
- Base: Gemini 3.5 Flash; **two epochs**, adapter size 4, learning-rate multiplier 1.0.
- Intermediate checkpoint export enabled (`export_last_checkpoint_only=False` in the submitted SDK configuration; false is omitted in Google's returned protobuf JSON).
- Training: 287 approved candidate examples, including 93 user-approved corrections; 113 uncertain training examples excluded.
- Validation: 155 separate examples, unchanged images/OCR/reference targets, with the same v4 prompt as training.
- Final-test data was not staged, uploaded or used.

The user approved this paid run after an estimated $12–$18 training charge before credits, excluding validation/inference/storage. All 444 uploaded objects (141.7 MB) were verified using returned content hashes. Cloud Billing API is disabled, so remaining promotional credits were not verified. Application credentials worked despite expired CLI credentials. Google accepted job creation without a credit/billing error; this does not prove a remaining credit balance or guarantee job completion.

The exact job response, plan, upload hashes/receipts, and guarded submission record are under the ignored `runs/gemini_product_v4_reviewed287_e2_20261117/` folder. `model_dev/tune_gemini.py` now supports explicit `--export-intermediate-checkpoints`; existing callers retain their prior default. All 40 Python tests passed, including a mocked two-epoch submission that verifies checkpoint export and job-ID persistence.

## Monitoring

From the project root:

```powershell
.\.venv\Scripts\python.exe -m model_dev.watch_product_run --job-file runs/gemini_product_v4_reviewed287_e2_20261117/tuning_job.json --project spatial-thinker-512218-b0
```

The monitor only reads status and refreshes the local job record. Closing it or the computer does not stop the cloud job. The original one-epoch job is `9081316234057744384`; it must not be confused with this new job.

## After completion

Inspect all returned checkpoints and compare them with base Gemini on identical v4 validation inputs/settings. Original v3 strict scores remain a separate experiment. Frozen validation references still contain the previously flagged scope/legibility cases; report that limitation and do not present reference-policy changes as model accuracy gains. Keep the current app/backend connection until checkpoint evaluation justifies a change. No production app or backend deployment was performed during submission.
