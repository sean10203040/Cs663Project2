# LabelLens - Project 2 working baseline

**Android Gemini backend is now deployed:** see [connection steps and verification](docs/BACKEND_READY.md).
The app token is in the local Git-ignored `.tools/APP_CONNECTION.txt` file.

**November 11 live verification:** both the base and existing fine-tuned Gemini
models were invoked on all 20 validation examples. See
[live results](docs/LIVE_GEMINI_RESULTS_20261111.md). The exact training prompt is
now recovered in `backend/qa_prompt.json`. The updated Android debug APK builds
and lint passes after correcting JSON exception handling in `ScanPipeline`.
The 30 final-test examples and Android UI-to-cloud flow remain unverified. The
HTTPS backend was subsequently deployed and tested; see the connection guide above.
The notes below include historical milestones.

Current Gemini integration: read [GEMINI_SETUP.md](GEMINI_SETUP.md). The user chose
to reuse the existing successful Gemini 3.5 Flash image-question model. Updated
Android source is in android/LabelLensProject2; the backend exposes /v1/answer.
Eight offline backend checks passed. Mobile/cloud inference and the comparison
still need to be run. The baseline notes below describe an earlier milestone.

For detector training, start with notebooks/LabelLens_Project2_Training.ipynb in
Google Colab. It is self-contained: upload the dataset and train, without the
starter ZIP. Select START_FROM="project1" to fine-tune a supplied checkpoint or
leave "pretrained" to train YOLOv8n from general pretrained weights.
The final cells export best.tflite at 320 pixels for the current Android model
dimensions, create labels.txt, and compare raw exported outputs against PyTorch
on six validation photos. Read model_contract.json before deployment: normalized
coordinates require a decoder update even when tensor dimensions match. Training
at 640 does not establish unchanged accuracy when exporting/inferencing at 320.
The notebook separately measures the PyTorch model at 320 and includes those scores.

For the image-processing/OCR experiment, use notebooks/LabelLens_Project2_Baseline.ipynb
with the starter ZIP, or use the local commands below. The original dataset and
Android ZIPs remain unchanged.

## What is prepared

- data/baseline: 431 checked image/label pairs, preserving train/valid/test splits.
- reports/baseline/dataset_audit.json: archive hash, decoding/label checks, orphan
  labels, and exact pixel duplicate checks. All 431 images decode, labels are valid,
  and no exact pixel duplicates were found. Near-duplicates/group leakage remain unaudited.
- data/baseline/real_data.yaml: 383 non-drawing inputs (268/62/53). The 48 reviewed
  drawings remain in the full baseline; they are excluded only from this view.
- annotations/baseline_annotations.jsonl: unreviewed OCR/attribute/group templates.
- labellens/experiment.py: P1 full-frame OCR, P2 predicted-crop OCR, P3 optional
  planar contour correction. Saves inputs, crops, tokens, transforms, and run settings.
- android/LabelLens: restored original app source/build inputs with normalized names.
- docs/ANDROID_REVIEW.md: actual app flow and changes needed for Project 2.
  reports/android/model_contract.json records the bundled model's static interface.
- docs/DATA_COLLECTION.md: how to expand by new product groups without changing
  the baseline or inventing transcription/attribute ground truth.

This milestone prepares data and an experiment. No new detector has been trained,
no Gemini model has been fine-tuned, and no Project 2 Android behavior is deployed.

## Local setup

Use Python 3.12. The existing .venv in this workspace has the tested preprocessing
dependencies. For a new checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-preprocess.txt
```

Recreate the baseline in a NEW empty directory (existing prepared data is protected):

```powershell
.\.venv\Scripts\python.exe -m labellens.audit --archive "D:\School CSUEB\CS663 Computer Vision\Project 2\dataset-20261105T195440Z-1-001.zip" --reports reports/baseline --prepare data/baseline
.\.venv\Scripts\python.exe -m labellens.prepare
```

The supplied ZIP has 443 labels but 431 images. The 12 orphan validation labels are
reported and omitted from the matched-pair copy. No missing images are synthesized.

## Inspect geometry before training

```powershell
.\.venv\Scripts\python.exe -m labellens.experiment --geometry-only --oracle-boxes --split valid --limit 12 --output runs/new_geometry_review
```

Oracle mode uses human boxes ONLY as a diagnostic and cannot emit OCR accuracy.
The first actual 12-image diagnostic retained all 15 crops unchanged because no
eligible four-corner contour was found. This is expected for tight name crops and
curved surfaces; it is not evidence of an OCR improvement.

## Run predicted-crop OCR in Colab

Upload dist/LabelLens_Project2_Starter.zip, the source dataset ZIP, and the chosen
Project 1 checkpoint when the notebook requests them. The app archive contains
several different checkpoints; choose and record the intended baseline rather
than treating every best.pt as equivalent. The later selected 640 checkpoint from
the website has not yet been matched to these files.

Notebook stages install the model/OCR dependencies, recreate audited data, load
your checkpoint, and run a validation pilot. An optional training cell trains
YOLOv8n on the real-only split with text flips/mosaic disabled; it never runs
automatically. Model selection and processing settings belong on validation data.

OCR metrics appear only for manually reviewed visible_text targets. Scoring uses
the same original-image target regions across all paths to avoid penalizing P1 for
background text outside the target. Those regions are not used to crop predictions.
Missing detections count as empty hypotheses, not dropped cases. CER/WER are
micro-averaged edit counts; they can exceed 1 with insertion errors. Text uses
NFKC, case folding, and whitespace normalization; punctuation/numbers remain.

The contour method is a planar candidate generator. Visually inspect every warp.
It cannot unwrap cylinders or folds. Raw originals and fallback statuses are saved.

## Checks and next development

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The checks cover archive pairing/duplicates, corner permutations/inverse mapping,
crop clipping, geometry fallback, OCR scoring/missing predictions, and export
coordinate convention/score mismatches.
Real-image geometry smoke checks were run on 12 validation images. Full detector
and OCR execution requires the checkpoint/dependencies in Colab; no OCR score is
claimed from the geometry-only run. The Colab workflow is prepared but unexecuted.

Next: review the actual app flow, select a checkpoint, annotate 20-50 validation
photos, collect the broader-label pilot, and evaluate P1/P2/P3. Then implement the
chosen processing policy in Android and add/evaluate fine-tuned multimodal Gemini.

References: https://docs.ultralytics.com/modes/train/ and
https://github.com/JaidedAI/EasyOCR and
https://docs.opencv.org/4.x/da/d6e/tutorial_py_geometric_transformations.html
