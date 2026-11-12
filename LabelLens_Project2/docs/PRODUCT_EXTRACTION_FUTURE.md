# LabelLens: Gemini examples, tuning, comparison and Android integration

This package contains Android source, a Python Gemini backend, and model-development
scripts. No YOLO retraining is needed to use these changes. No Google Cloud resources
were created, no Gemini job was run, and no credentials are included. The new Android
changes and live cloud requests have not been runtime-tested; test them on your laptop.

## 1. Open the Android code

Open android/LabelLensProject2 in Android Studio, use a JDK 17+ compatible with
Gradle 9.3, sync dependencies, and run on API 28+. The bundled YOLO model is retained.
The project adds org.opencv:opencv:4.12.0. Internet is enabled only for the optional
backend flow; the existing detector/OCR can still operate without Gemini.

The app can now record P1/P2/P3 under one 4096-pixel master-image policy, preserve
OCR words/polygons, export scan images and metadata, call the backend, and speak
both results and failure guidance. Name-based context crops remain an explicit ROI
policy, not a newly trained whole-label detector. Choose Flat label for planar
correction. Bottle/can correction is an experimental 120-degree orthographic arc
assumption; it is not automatic 3-D recovery. Unspecified/folded surfaces retain the
original crop. Inspect geometric outputs and do not assume they improve OCR.

## 2. Collect actual Gemini examples

On the phone, enter a product group and condition in Study annotations. Assign all
views of one product to one split. Capture/read a label and use Save scan and
evaluation record. Extract exported scan ZIPs into a folder on your laptop.

Create a Python 3.12 environment in the root of this package:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe -m model_dev.prepare_examples --scans exported_scans --output gemini_examples
```

Edit gemini_examples/examples.jsonl against the exact crop/context images. Each
record starts reviewed=false. For each target, enter product_name, brand, size,
best_by, certainty and guidance, with evidence for every non-null field. Use null
for absent/unreadable fields. For OCR evidence the quote must occur in raw OCR;
image evidence must be transcribed from visible text. Do not infer a date/quantity
from knowing the product. A base-model response is only an unreviewed draft.

See model_dev/reviewed_example_format.json for the shape, not training content.
Set reviewed=true only after reviewing that actual example. Assign train,
validation or test and a real product_group. The proposal targets about 400 tuning
examples, plus separate validation/test data and 600-800 captures across 60-100
products. This code does not manufacture missing examples or review decisions.

## 3. Set up Google Cloud

In your own Cloud account, create/select the project, attach the class billing/
credits, enable the Vertex AI API and Cloud Storage, and choose an image-tuning
model and supported region. This starter defaults to Gemini 2.5 Flash and
us-central1; verify current model/region availability and quota in your project.
Install the Google Cloud CLI and authenticate on your laptop:

```powershell
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default login
gcloud services enable aiplatform.googleapis.com storage.googleapis.com
```

Create a bucket in the Cloud console. Prepare reviewed JSONL and images:

```powershell
.\.venv\Scripts\python.exe -m model_dev.export_sft --records gemini_examples/examples.jsonl --output gemini_ready --gcs-prefix gs://YOUR_BUCKET/labellens
gcloud storage cp -r gemini_ready/images gs://YOUR_BUCKET/labellens/
gcloud storage cp gemini_ready/train.jsonl gs://YOUR_BUCKET/labellens/train.jsonl
gcloud storage cp gemini_ready/validation.jsonl gs://YOUR_BUCKET/labellens/validation.jsonl
```

The exporter excludes unreviewed entries and rejects cross-split product groups
and byte-identical image leakage. It does not prove that manually assigned groups
or near-duplicate captures are independent. Never submit test.jsonl for tuning.

## 4. Fine-tune Gemini

This command submits a real billable cloud tuning job when you run it. Check the
dataset counts, credits/quota and current supported tuning model before submission.

```powershell
.\.venv\Scripts\python.exe -m model_dev.tune_gemini --project YOUR_PROJECT_ID --location us-central1 --base-model gemini-2.5-flash --train-uri gs://YOUR_BUCKET/labellens/train.jsonl --validation-uri gs://YOUR_BUCKET/labellens/validation.jsonl
```

Save the job name. Inspect it later without submitting another job:

```powershell
.\.venv\Scripts\python.exe -m model_dev.tune_gemini --project YOUR_PROJECT_ID --location us-central1 --job projects/PROJECT/locations/REGION/tuningJobs/JOB_ID
```

Use the successful job's tuned_model.endpoint, not its tuning-job ID or an invented
model name. The Android setting never silently substitutes base Gemini when the
tuned endpoint is absent. Confirm the serving region matches the tuned endpoint.

## 5. Compare base and tuned on identical held-out examples

```powershell
.\.venv\Scripts\python.exe -m model_dev.evaluate_gemini --records gemini_examples/examples.jsonl --project YOUR_PROJECT_ID --location us-central1 --base-model gemini-2.5-flash --tuned-model YOUR_TUNED_ENDPOINT --split validation --output gemini_validation_comparison
```

This writes per-example outputs/errors and comparison.json with field accuracy,
precision/recall, JSON validity, false identification when the product is unknown,
and condition-level breakdowns. API/invalid-response failures stay in the denominator.
Use validation to choose settings; freeze them before a final --split test run.
No performance numbers are claimed until actual reviewed examples have been run.

The validation run also writes categorical confidence-bucket measurements. The
backend exposes these only when the report matches the exact model/prompt and the
bucket contains at least 30 reviewed examples. This is empirical validation support,
not proof that an individual result is correct. No calibrated rate is invented.

## 6. Run/deploy the backend

Copy backend/.env.example to .env and fill project, location and tuned endpoint.
Generate a long random LABELLENS_APP_TOKEN with Python's secrets.token_urlsafe(32).
Do not use your Google password or a Google service-account key as this app token.
Keep .env outside Git. For local development:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8080 --env-file .env
```

GET /health reports configuration presence, not successful model access. Android
expects an HTTPS backend. Deploy backend/Dockerfile using the package root as the
Docker context to Cloud Run or another HTTPS host. Give its service identity the
needed Vertex AI permissions and set the environment variables there. The server
uses Application Default Credentials; no Google credential is embedded in the app.
The per-demo bearer token is application authentication, not a complete multi-user
identity system. Replace it with user identity authentication if distributing widely.

In Android, tap Connect product-details service, enter the HTTPS base URL and the
application token, select Base Gemini or Fine-tuned Gemini, and enable product
details. The token is kept only for the app session. The backend validates JSON,
requires evidence for non-null fields, and rejects quotes absent from supplied OCR.
Image-evidence claims still need evaluation; a model can be wrong about an image.

## Useful failure behavior included

- Offline/local OCR remains available with product details turned off.
- Missing backend settings prompt configuration instead of issuing a fake result.
- A missing tuned endpoint returns an explicit service error, not a base-model answer.
- HTTP failure/timeout retains raw OCR and announces product-details unavailability.
- No detection/text produces spoken guidance and haptic feedback.
- Invalid/unsupported Gemini output is rejected by the backend.
- Unreadable fields remain null; all-unknown results require low reported certainty
  and actionable guidance. Confidence is never presented as a verified probability.
- Cancellation suppresses stale results and stops further stages at progress boundaries.

## Still required to claim project completion

Reviewed application-specific data and product-group splits; the actual successful
Gemini tuning job; measured base/tuned and full-system results; device/camera tests;
P1/P2/P3 OCR evaluation with manual ground truth; latency to first speech; failure
examples; the narrated mobile demo, GitHub development records and final report.
Code for a workflow alone is not evidence that these requirements have been met.

Primary documentation used for this implementation:
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tuning/image
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tuning/supervised-tuning/use
- https://googleapis.github.io/python-genai/
- https://docs.opencv.org/5.0/tutorials/introduction/android_binary_package/dev_with_OCV_on_Android.html
