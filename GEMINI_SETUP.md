# LabelLens: use the existing tuned Gemini model first

**Backend is now ready:** use [the app connection guide](docs/BACKEND_READY.md).
The HTTPS gateway has been tested with the existing tuned model, and the local
ignored `.tools/APP_CONNECTION.txt` contains the URL and application token.

**Live check completed November 11:** the exact prompt has been recovered in
`backend/qa_prompt.json`, and both models completed the 20-example validation
comparison without API or JSON errors. See
[results and limits](docs/LIVE_GEMINI_RESULTS_20261111.md). No Cloud Run deployment
or Android-to-cloud test was performed. Earlier inspection-status statements
below describe the uploaded package before this check.

The Android app now asks one question about one selected label image. The backend
uses the existing FineTunedModel endpoint and validates its `answer`/`answerable`
JSON. It preserves local OCR when Gemini fails, gives rescan guidance for an
unanswerable image, and records which model actually answered. No YOLO or Gemini
retraining is needed. Start with steps 1–3 below on your laptop.

The richer product-name/brand/size/evidence workflow is a future alternative in
docs/PRODUCT_EXTRACTION_FUTURE.md. Its /v1/parse route and training scripts remain
separate. The current Android code uses /v1/answer; do not configure the old route
with this question-answer model.

## Existing resources

| Setting | Value |
|---|---|
| Project | spatial-thinker-512218-b0 |
| Base model for comparison | gemini-3.5-flash |
| Base serving location | global (configurable) |
| Tuned endpoint | projects/1056598944825/locations/us/endpoints/1423735616574586880 |
| Tuned serving location | us, inferred from the endpoint |
| Tuning job | projects/1056598944825/locations/us-central1/tuningJobs/5156565025799798784 |
| Training/validation/test files | gs://labellens-spatial-thinker-512218-b0/datasets/ |

The console showed a succeeded one-epoch job and 100 training examples. This does
not establish accuracy or fulfill the proposal's approximately 400-example goal.
The tuning region and serving region differ. No additional Gemini deployment is
needed just to try the existing active endpoint.

## 1. Install dependencies and sign in

Open PowerShell in the repository root (the folder containing `settings.gradle` and `backend`). Use
Python 3.12 and install the official Google Cloud CLI if `gcloud` is unavailable.
These login steps are for your own account; no Google keys go in Android.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
gcloud auth login
gcloud config set project spatial-thinker-512218-b0
gcloud auth application-default login
gcloud auth application-default set-quota-project spatial-thinker-512218-b0
```

CLI login downloads the existing data; Application Default Credentials are used
by the Python SDK. Use the account that can access your Cloud project.

## 2. Download the original data and extract the exact prompt

The console preview truncates the instruction. Browser downloads did not complete
in this session, so the full prompt is deliberately not guessed or bundled.

```powershell
New-Item -ItemType Directory -Force existing_qa_data
gcloud storage cp gs://labellens-spatial-thinker-512218-b0/datasets/train.jsonl existing_qa_data/train.jsonl
gcloud storage cp gs://labellens-spatial-thinker-512218-b0/datasets/validation.jsonl existing_qa_data/validation.jsonl
gcloud storage cp gs://labellens-spatial-thinker-512218-b0/datasets/test.jsonl existing_qa_data/test.jsonl
.\.venv\Scripts\python.exe -m model_dev.prepare_existing_qa --train existing_qa_data/train.jsonl --validation existing_qa_data/validation.jsonl --test existing_qa_data/test.jsonl --output backend/qa_prompt.json
```

This writes backend/qa_prompt.json, prints the common instruction prefix, and
reports actual split counts. Inspect the first training lines and confirm the
question is at the end of each prompt. The extractor expects the literal marker
`Question:`; if different, pass its exact text with `--question-marker`. Inconsistent
instructions, unexpected input formats, or shared image URIs across splits stop
preparation for review. If instructions follow the question, manually adjust the
prefix/suffix template; do not treat those instructions as part of the question.
The template includes a checksum; recompute it with backend.qa.prompt_digest if
making a reviewed manual edit.

URI checks do not detect renamed duplicates, shared products, near duplicates, or
incorrect references. Review those separately. Reusing training/validation images
does not establish independent final test accuracy.

## 3. Try one real request before connecting Android

Use a real label photo and a question whose answer could be visible:

```powershell
.\.venv\Scripts\python.exe -m model_dev.ask_existing_qa --image "C:\path\label.jpg" --question "What is the name of this product?" --variant tuned
.\.venv\Scripts\python.exe -m model_dev.ask_existing_qa --image "C:\path\label.jpg" --question "What is the name of this product?" --variant base
```

These make billable inference requests using your project/credits; they do not
train. A valid result contains `qa.answer` and `qa.answerable`, plus rescan guidance
when unanswerable. Answers are predictions, not verified facts. No confidence
probability is invented.

For a 403, check the account's Vertex AI prediction permissions and access to the
image objects used in evaluation. For a 404, check endpoint and serving region;
this tuned endpoint is in `us`. Base location is configurable with --base-location.

## 4. Compare base and tuned on the existing held-out split

Run validation to check the workflow, freeze settings, then run test:

```powershell
.\.venv\Scripts\python.exe -m model_dev.evaluate_existing_qa --train existing_qa_data/train.jsonl --validation existing_qa_data/validation.jsonl --test existing_qa_data/test.jsonl --split validation --output qa_validation_results
.\.venv\Scripts\python.exe -m model_dev.evaluate_existing_qa --train existing_qa_data/train.jsonl --validation existing_qa_data/validation.jsonl --test existing_qa_data/test.jsonl --split test --output qa_test_results
```

N examples produce 2N inference requests. Both models receive exactly the same
role=user image URI and prompt. The role=model reference is used only for scoring.
No test data is submitted for training. Calls alternate which model goes first.

Outputs: base_predictions.jsonl, tuned_predictions.jsonl, comparison.json. Scores:
normalized exact accuracy, token F1 on answerable cases, answerability accuracy,
false answers when unanswerable, invalid/API responses, and cloud latency. Failures
remain in accuracy denominators. Single-reference scoring can penalize equivalent
answers; this is not an official multi-annotator VizWiz score. Review equivalences
manually. Cloud time is not phone capture-to-speech time. These scores assess the
original SFT task, not the new YOLO/OpenCV/OCR pipeline by itself.

## 5. Run the backend and connect Android

Copy backend/.env.existing-qa.example to `.env`. Generate a random application token,
put it in LABELLENS_APP_TOKEN, and keep `.env` private. Do not use a Google password,
access token, or service-account key as this app token.

```powershell
Copy-Item backend/.env.existing-qa.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8080 --env-file .env
```

GET http://127.0.0.1:8080/health checks configuration presence, not live access.
For phone access, host the backend at an HTTPS URL. The root Dockerfile and
.gcloudignore support Cloud Run source deployment. Ensure backend/qa_prompt.json
exists first. Its service identity needs Vertex AI prediction permissions. Do not
upload a service-account credential file. Backend deployment is separate from the
already-active Gemini endpoint.

Optional Cloud Run commands to run yourself after reviewing billing and permissions:

```powershell
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
gcloud run deploy labellens-qa --source . --region us-central1 --no-allow-unauthenticated --max-instances 1 --concurrency 4 --timeout 60 --set-env-vars "GOOGLE_CLOUD_PROJECT=spatial-thinker-512218-b0,LABELLENS_QA_BASE_MODEL=gemini-3.5-flash,LABELLENS_QA_BASE_LOCATION=global,LABELLENS_QA_TUNED_MODEL=projects/1056598944825/locations/us/endpoints/1423735616574586880,LABELLENS_QA_PROMPT_FILE=backend/qa_prompt.json"
```

Set LABELLENS_APP_TOKEN in the Cloud Run revision's environment or Secret Manager
before testing. The first deploy above keeps the service private. Android's simple
demo gateway sends the app token, not a Google Cloud IAM identity token. For direct
phone access, the Cloud Run frontend must accept unauthenticated requests while
FastAPI continues to enforce LABELLENS_APP_TOKEN. If using this class-demo arrangement,
change Cloud Run's authentication setting yourself after configuring the app token.
Until then, a 403 from Cloud Run is expected. Use authenticated user identity if
distributing beyond your demo. Build/hosting/inference can incur charges; max instances
is not a spending cap. No deployment or cloud permissions were changed here.

Open the repository root directly in Android Studio, build/run on API 28+, tap
**Connection settings** in the **Ask Gemini** section, enter the HTTPS backend base
URL and app token, select Fine-tuned Gemini, and save. Read locally first, then
enter a question and tap **Ask Gemini**. Connection settings saves the token encrypted
on the device and restores it when the app is reopened.

The app sends one selected image (JPEG, max side 2048) and a question. OCR stays
available locally but is not appended to the image-only training contract. P1
sends the full image; P2/P3 use their selected region/correction. If detection fails,
the full source image is used for the question and recorded. Use the full-photo
button if the answer lies outside the crop. Inspect inputs before scoring results.

## Failures and remaining work

- Missing prompt or endpoint: setup error, never silent base fallback.
- Offline, timeout, quota, invalid JSON: retain local OCR with spoken failure guidance.
- Unanswerable: rescan guidance rather than a product guess.
- Records preserve question, actual model, region, prompt hash and timing.
- Cancellation suppresses stale results; it cannot recall a sent cloud request.
- There are no automatic retries that create hidden requests.

Eight offline Python checks passed for QA validation, auth, failures, reference
exclusion, region selection and SDK settings. Android XML/source consistency is
checked separately. Android was not built/run here; no live Gemini request or
base/tuned comparison was executed. Test these on your laptop and phone.

The proposal still requires dataset expansion/review, real camera and failure
examples, P1/P2/P3 OCR measurements, full-system latency, report and demo. The old
400-example goal remains an expansion target; this model is the first experiment.

References:
- https://googleapis.github.io/python-genai/
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tuning/supervised-tuning/use
