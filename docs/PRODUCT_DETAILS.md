# Product details baseline

## November 13 verification

- Android debug app and instrumentation APK compile; lint reports zero errors.
- Twenty-three offline Python backend/export tests pass, including existing QA.
- Deployed to the existing `labellens-qa` Cloud Run service, revision
  `labellens-qa-00003-z8f`, at the same HTTPS URL with the same app token.
- The live `/v1/parse` smoke check returned HTTP 200 with base `gemini-3.5-flash`
  and prompt `labellens-evidence-v2`. It returned separate name, brand, and size,
  with `best_by: null`; the missing date displays as Not visible in the app.
- That smoke check used one existing validation image and an empty OCR string;
  it verifies live image extraction, not image+OCR accuracy or the phone UI.
  Offline SDK tests separately verify both images and supplied OCR are forwarded.
- Unauthenticated extraction requests return HTTP 401. Calibration is null;
  model-reported certainty is not presented as calibrated accuracy.
- No new tuning job was created. Device testing of the new card is still needed.

Live raw results are retained locally in
`qa_product_details_results/live_evidence_comparison_20261113.json` (ignored by Git).
The updated live smoke check also verified missing-date guidance and comparison
unavailability with zero inference requests. See
[evidence, review and comparison](GEMINI_IMPROVEMENTS.md) for the new workflow.

## Feature

After a local scan, the optional Gemini section now offers **Analyze product
details**. The action uses the saved connection and the **base** Gemini model,
independently of the model selected for the existing question-answer feature.
The QA endpoint and its existing fine-tuned model remain unchanged. This update
does not start a tuning job or claim an improvement from fine-tuning.

The product card shows product name, brand, size/net weight, best-by date,
rescan guidance, and model-reported certainty. Missing fields stay null in JSON
and display as **Not visible**. A printed date is transcribed as visible; no
expiration, freshness, or product-safety judgment is made. Reported certainty
is explicitly **not calibrated**.

## Flow

1. Take or import a photo and run local Read label, Read full photo, or correction.
2. In the Gemini section, select whether to include the whole photo for context.
   The OCR input is always sent; the optional second image is the source photo.
3. Tap Analyze product details. The app posts the crop, the exact raw OCR from
   that scan, and optional context to `/v1/parse` with `model_variant: base`.
4. Inspect the structured fields. Read details aloud is a separate user action.
   The original OCR remains visible above. A failure does not replace it.
5. Export scan record to retain the request's OCR, image references, complete
   structured response including evidence/model identity/prompt version, and timing.
   These exported predictions are not ground truth until manually reviewed.

The product-name detector can exclude dates or weight. Context helps supply
those areas, but a photo containing multiple products remains ambiguous. Keep
one package in frame; the backend prompt forbids borrowing other products'
attributes. Image evidence is model-reported supporting text, not independent
verification that a value is true.

## Backend

Product extraction defaults to `gemini-3.5-flash` in `global`, configurable via
`LABELLENS_BASE_MODEL` and `GOOGLE_CLOUD_LOCATION`. The existing QA model settings
are separate. Tuned product extraction fails explicitly until its own
`LABELLENS_TUNED_MODEL` is configured; it never substitutes the QA model.

`labellens-evidence-v2` versions the extraction prompt. Each populated field
requires an evidence quote; quotes attributed to OCR must occur in the supplied
OCR. Invalid types, unsupported evidence, missing fields, and malformed JSON
produce a failure rather than partially trusted UI output. Image-only evidence
must still be reviewed against the source photo during evaluation.

The existing application token is reused. Do not put it in source code or a
committed configuration file. No automatic retry or fallback adds hidden model
requests. Each Analyze action performs one extraction inference.

## Checks and next work

Backend contract tests cover partial and unreadable labels, unsupported fields,
authentication, task separation, and SDK request wiring. Android includes
instrumentation checks for partial-value presentation and response validation.
Build and lint checks compile those tests; running on a device remains a
separate step.

Next: review real-photo extraction errors, assemble independently reviewed
crop/OCR/target examples, then compare base and a future product-extraction
fine-tune using the same inputs, scoring, and held-out product groups. Keep the
existing QA model as a separate experiment. A fine-tuning benefit must be
measured, not assumed or created by changing the test set.
