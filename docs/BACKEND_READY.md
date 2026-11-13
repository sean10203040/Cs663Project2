# Android Gemini backend — ready November 11, 2026

November 13 update: the same service now supports the new **Analyze product
details** action using base Gemini image+OCR extraction. Revision is
`labellens-qa-00002-kcf`; the URL and app token are unchanged. The new extraction
route passed a live smoke check; see [product details](PRODUCT_DETAILS.md).
Historical QA deployment information below describes the initial revision.

The existing trained model is connected through a deployed HTTPS backend.
No training, tuning, or replacement of the existing model was performed.

Service URL: https://labellens-qa-1056598944825.us-central1.run.app

Open the repository root (the folder containing `settings.gradle`) directly in Android Studio, then:

1. Open **Connection settings** inside the **Ask Gemini** section.
2. Enter the service URL above and copy the application token from the local
   ignored file `.tools/APP_CONNECTION.txt` (or `.tools/app-token.txt`).
3. Select **Fine-tuned Gemini**, then **Save**.
4. Read a label with the local reader above, then enter a question and tap **Ask Gemini**.
5. Use **Read full photo** when the requested information is outside the product-name crop.

The latest Android source saves the connection on this device. Enter the token
once and tap Save; it is encrypted using an Android Keystore AES-GCM key and
reloaded when the app opens. Forget token removes it. Uninstalling or clearing
app data removes the saved connection. Google credentials stay in Google Cloud
and are not embedded in the Android app.

## Verified through the public HTTPS service

- Health endpoint: configured prompt and tuned QA endpoint.
- Question request without an application token: HTTP 401.
- Question request with the application token: HTTP 200.
- Selected model: `projects/1056598944825/locations/us/endpoints/1423735616574586880`.
- Validation image question: `what flavor is this?`.
- Actual tuned-model answer: `salmon with basil`, answerable true.
- Observed full HTTPS question-request time: 5.43 seconds, including backend/model processing.
- Android UI interaction itself has not been exercised against this service yet.

Raw verification is stored locally in `qa_gateway_results/live_20261111.json`.
The legacy extraction flags in `/health` are separate from the QA flags; the app
uses `/v1/answer`, for which `qa_prompt_configured` and `qa_tuned_configured` are true.

## Deployment

- Project: `spatial-thinker-512218-b0`.
- Cloud Run service: `labellens-qa`, region `us-central1`.
- Revision: `labellens-qa-00001-5zn`.
- Dedicated runtime identity: `labellens-backend@spatial-thinker-512218-b0.iam.gserviceaccount.com`.
- Runtime roles: Agent Platform Endpoint User and Service Usage Consumer.
- Maximum instances: 1; minimum instances: 0; concurrency: 4; request timeout: 60 seconds.
- Cloud Run accepts requests from the phone; FastAPI authenticates prediction calls with the app token.
- Source upload contains only the backend, verified prompt, Dockerfile, and ignore files.
- Token deployment settings are in ignored `.tools/cloudrun-env.yaml`; they are
  supplied as runtime environment settings and are not included in the container source.

To verify again (one real model inference):

```powershell
.\.venv\Scripts\python.exe -m model_dev.smoke_gateway --url https://labellens-qa-1056598944825.us-central1.run.app --token-file .tools/app-token.txt --image .tools/backend-test-label.jpg --question "what flavor is this?" --output qa_gateway_results/recheck.json
```
