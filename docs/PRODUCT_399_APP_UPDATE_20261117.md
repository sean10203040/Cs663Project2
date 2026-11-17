# 399-image model connected to Android — November 17, 2026

Cloud Run revision `labellens-qa-00005-lqd` is serving the existing app URL:
`https://labellens-qa-1056598944825.us-central1.run.app`.

The fine-tuned **product extraction** action and comparison now use
`projects/1056598944825/locations/us/endpoints/2142341232116891648`, trained on
399 images for two epochs. Both extraction variants use the exact evaluated v4
instruction (SHA-256 `cc071334fdb0ed6fb98e6229d2f8dd6f3db9963f3892333cf154652e36643793`).
The base-first layout and separate question-answer model retain their roles.

## Evidence recovery

The 17 rejected fine-tuned validation responses all claimed at least one OCR
quote absent from the actual transcript. The backend now performs at most one
targeted image recheck for those fields, with the original images and OCR. The
model must explicitly reread the image or supply a genuine OCR quote. The server
does not silently switch evidence sources. Fields outside the repair list retain
their original values and evidence.

If rechecking fails or still returns unsupported evidence, the affected fields
become unknown, their evidence is removed, and the response supplies specific
rescan guidance. Other supported details remain available. Completely unknown
results require low reported confidence. Malformed schemas still fail validation.
Valid first responses need no additional model request. Recovery can add one
inference call, latency and inference cost to an affected scan.

The response records processing version `targeted-evidence-recheck-v1`, attempted
fields, removed fields and actual inference-call count. Calibration from an older
processing policy is not reused. No model weights or dataset labels changed.

## Verification

- 53 automated tests passed, including unchanged first responses, targeted repair,
  unsuccessful repair, complete abstention, prompt checksum, same-image routing
  and accurate comparison request counts.
- The 138 previously valid 399-model responses replayed unchanged without an
  additional call.
- All 17 saved evidence failures passed a targeted live recheck, with no fields
  needing removal. Extracted field values remained unchanged in those repairs.
  This is a recovery diagnostic, not independently verified semantic accuracy.
- The Android debug build passed. Product requests allow 65 seconds; comparisons
  allow 125 seconds, accommodating up to one recheck per variant. Cloud Run's
  request timeout is 120 seconds. Normal successful calls still return promptly.
- Authenticated HTTPS comparison succeeded for both base and the exact 399-image
  endpoint. Both sides exercised evidence recovery; four model calls took about
  9.45 seconds combined in this smoke test. This is not a phone latency benchmark.
- Requests without an app token returned HTTP 401. The original question-answer
  endpoint passed a live request. Existing environment settings, app token and URL
  were verified preserved.
- The uploaded source bundle contained only 12 explicitly allowed backend/build
  files; datasets, tokens, local settings and Android files were excluded.

Diagnostic and deployed smoke records are in
`runs/gemini_product_v4_evidence_recheck_20261117/`. The earlier three-model
comparison remains unchanged; its scores do not include this new processing
policy. Final-test data remains untouched, and unresolved validation-reference
flags still require adjudication before strong accuracy claims.

## Use in Android

Rebuild/run the root project in Android Studio for the updated timeout settings.
Read a label, then use **Analyze with fine-tuned model** in the product-details
section, or compare product extraction models. The base product-details action
still provides the base-model result. Saved connection settings continue to work.
The older installed app already reaches the new backend but retains its shorter
timeouts until rebuilt. No APK was installed on a phone in this update.

## Rollback

The previous revision `labellens-qa-00004-nmx` remains available. If rollback is
needed, route traffic to it; this also restores its previous model/prompt settings:

```powershell
gcloud run services update-traffic labellens-qa --project spatial-thinker-512218-b0 --region us-central1 --to-revisions labellens-qa-00004-nmx=100
```
