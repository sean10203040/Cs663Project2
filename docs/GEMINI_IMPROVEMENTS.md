# Evidence, review and model comparison

Open the repository root in Android Studio. Local detection/OCR was not changed.
After reading a label, use the separate Gemini section:

1. **Analyze product details** shows product name, brand, size and best-by date.
   Each populated field now shows an **OCR quote** or **Model-read image text**.
   OCR quotes are checked against the supplied OCR. An image quote is Gemini's
   transcription, so it still needs human inspection. Missing fields have no
   evidence and remain **Not visible**.
2. Rescan instructions address the missing field: front label for name/brand,
   net-weight/volume area with units for size, and cap/base/seam/back plus the
   printed heading for a date. These are suggestions about where to look, not
   claims that a date exists there. A lot code is not treated as a best-by date.
3. **Review or correct details** opens the supplied images and raw OCR beside
   editable values, quotes and evidence sources. Leave invisible fields blank.
   Give all photos of one product the same group ID. A confirmation checkbox is
   required before saving. The original prediction is preserved under
   `product_details`; the checked target is stored under `product_review`, with
   the selected input views, actual OCR, group, split and timestamp.
4. **Export reviewed scan** writes the image/JSON ZIP using Android's save dialog.
   Extract ZIPs into `exported_scans`, then run:

```powershell
.\.venv\Scripts\python.exe -m model_dev.prepare_examples --scans exported_scans --output gemini_examples
```

This creates examples, not a training job. Unreviewed drafts stay unreviewed.
The preparation script prioritizes checked targets and retains the original
prediction. It preserves context being omitted and the actual OCR supplied to
Gemini, including OCR mistakes. A checked reference in the development split
must be assigned a training, validation or test split before SFT export.

## Base versus fine-tuned comparison

**Compare base and fine-tuned details** calls authenticated `/v1/compare`.
Both model requests receive the same encoded image bytes, OCR, extraction
prompt and generation settings. Responses include model IDs, prompt version,
timing and a shared input hash. Per-model failures remain visible. The app
shows fields side by side, followed by each model's evidence and guidance.

Matching values are **agreement**, including shared missing values; they are
not an accuracy score. Correctness requires independently checked references.
The existing fine-tuned model was trained for image-question answering and is
kept on `/v1/answer`. It must not be presented as a product-extraction model.
Until a separate `LABELLENS_TUNED_MODEL` endpoint exists, comparison returns an
explicit explanation and performs zero model inference requests.

## Improving fine-tuning after the new data arrives

First choose the task. Improve the existing QA model with image/question/checked
answer examples matching its training prompt. For this product card, prepare a
separate extraction fine-tune using crop, optional whole photo, actual noisy OCR,
and the checked structured output with field evidence. YOLO bounding boxes alone
do not supply those Gemini target answers.

Use real failures: missing letters, stylized fonts, reflections, curved labels,
small sizes and date codes. Include ordinary clear labels and cases with genuinely
missing/unreadable fields, so the model learns when to return null. Review every
target rather than accepting base-model drafts as truth. These choices follow
[Google's data preparation guidance](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tuning/supervised-tuning/prepare-data).

Split by product before training. All views, video frames and near duplicates
of one package belong in one split. Keep the final test set untouched while
selecting prompts, training settings and checkpoints on validation. The exporter
rejects cross-split group IDs and byte-identical images, but people still need
to check grouping and near duplicates.

Compare the tuned endpoint against its **own parent base model/version** using
the same prompt, images, OCR and generation settings. The current base-model
setting may need to change to that parent; comparison with a different newer
model is a separate product benchmark and does not isolate the effect of tuning.
Start with a baseline on validation, tune only after reviewing error patterns,
and change training settings based on validation results rather than final tests.

The existing `model_dev.evaluate_gemini` tool scores reviewed held-out examples:
field accuracy and precision/recall, all-fields accuracy, invalid-response rate,
unsupported values on absent fields, median latency and condition breakdowns.
Errors remain in the accuracy denominator. Inspect image quotes manually as
well: valid JSON and a supporting quote do not prove the field is correct.
Use the final frozen test set once the experiment is selected. Report actual
results, including regressions; a benefit from tuning cannot be guaranteed.

No fine-tuning was started for this update. The Android debug app and device-test
APK compile, lint has zero errors, and backend/export unit tests cover input
pairing, missing-field guidance, absent configuration, human-reference export,
unreviewed drafts and split leakage. Device interaction remains to be checked.
