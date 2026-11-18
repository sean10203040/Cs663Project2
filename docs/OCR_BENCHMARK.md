# Run the proposal's P1/P2/P3 OCR benchmark

The app already runs all three local OCR paths and exports their images, text,
word polygons, geometry, timings and detector hash. The scoring tool is
`model_dev/benchmark_ocr.py`. It makes no cloud calls and does not retrain models.
No real benchmark results can be produced until phone comparison scans and
checked manual transcriptions are available.

## First pilot on the phone

1. Take or import a label photo. Start with a new development/validation product;
   reserve the existing final-test products until the protocol is frozen.
2. Scroll to the evaluation controls near the bottom. Enter a stable **Product
   group ID** (reuse that ID for all views of the same product). Choose **Capture
   condition** and **Validation** as the dataset split.
3. Enter **Manually transcribed reference text**, independently reading the photo.
   Include the complete target label text, in reading order. Do not use a Gemini
   product-details summary or copy unchecked OCR as the reference. Check **I
   checked this reference against the photo**. Set these fields before scanning.
4. Choose the surface correction that matches the package. Keep contrast and
   crop-padding settings fixed across this benchmark. Tap **Compare full, cropped
   and corrected reading**. This runs P1/P2/P3 from the same source photo.
5. Tap **Export scan record** and save the ZIP to the computer under
   `data/incoming/ocr_benchmark_exports/`. Export the OCR scan, rather than only
   the reviewed Gemini product details. Preserve failed detections too.

Start with one export to verify the workflow. Then collect several distinct
products under all six proposed conditions: clean, curved, crumpled, damaged,
partially occluded, and glare/shadows. The assignment does not specify a fixed
number of benchmark photos; report actual coverage and missing categories.

## Score the exports

From the root project folder in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m model_dev.benchmark_ocr --input data/incoming/ocr_benchmark_exports --split validation --output runs/ocr_benchmark_20261118/validation_01
```

Use a new output directory for each report. The tool writes:

- `report.html`: readable summary and searchable P1/P2/P3 text comparisons.
- `report.md`: aggregate and per-condition results, paired improvements/regressions
  and explicit interpretation limits.
- `report.json`: machine-readable scores, coverage, provenance and unscored cases.
- `per_scan.jsonl`: reference, predictions, edit counts, geometry and image hashes.

Unchecked references, missing group/condition metadata and incomplete comparisons
are listed as unscored. Missing detection is a pipeline failure, remains in every
paired denominator, and is scored as an empty reading. Empty input folders and
cohorts with no eligible records do not produce invented zero-error reports.
Mixed detector, OCR, crop, contrast or processing settings are rejected; score
each configuration separately. Exact duplicate exports are deduplicated, while
conflicting records/images with the same scan ID are rejected.

## Scoring policy

Default **selected-label** scope measures end-to-end target-label reading. The
same full manual transcript is used for every path. Extra background text counts
as insertions and cropped-away label text as deletions. This measures localization
and recognition together, rather than pure OCR quality.

Normalization applies Unicode NFC, casefolding and whitespace collapsing. Digits,
accents and punctuation are retained. CER = character edit distance / reference
characters. WER = word edit distance / reference words. Word accuracy is explicitly
defined here as 1 − WER, including insertion penalties; it can be negative. CER
can exceed 100%. Dataset scores pool edit counts/reference lengths. Reviewed empty
references have no per-image denominator; unexpected text is counted separately
and contributes insertions to pooled errors.

OCR time excludes detection, geometry, camera handling and speech. Comparison runs
execute all three paths, so their combined time must not be presented as the
standalone latency of an individual path. Actual capture-to-speech and accessibility
testing remain separate full-system experiments.

## Optional controlled common-region comparison

For pure same-region comparisons, create independent, human-defined reference
rectangles in `source.png` pixel coordinates. Do not copy the detector-generated
`evaluation_region_xyxy`, which would condition the reference region on detector
success. Prepare a hash-bound manual annotation file:

```powershell
.\.venv\Scripts\python.exe -m model_dev.benchmark_ocr --input data/incoming/ocr_benchmark_exports --prepare-annotations --output runs/ocr_benchmark_20261118/manual_labels
```

For each JSONL row, enter `reference_text`, set `reference_reviewed` to true only
after checking the image, and enter `reference_region_xyxy` as `[left,top,right,bottom]`.
The generated fields start blank and unchecked, never copied from model outputs.
Retain the image/record hashes. Then score with `--scope manual-roi --annotations
runs/ocr_benchmark_20261118/manual_labels/annotations.jsonl` and a new output folder.
The tool maps word polygons through the saved homography/cylindrical mapping and
crop origin before selecting word centroids in the same manual rectangle.

Final-test runs require `--split test --confirm-final-test`. Split checks cover
the supplied exports; users must keep product IDs consistent with the original
dataset and ensure test products were never used for training. These tools do
not certify independent human ground truth or repair uncertain transcriptions.
