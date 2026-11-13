# LabelLens — CS663 Project 2

**Open this folder directly in Android Studio:**

```text
C:\Users\seanf\OneDrive\Documents\ChatGPT\Project  2 Cs663
```

The Android project is at the repository root. There is no separate nested
Android project to open.

```text
Project  2 Cs663/
  app/                 Android app, detector model, OCR and Gemini interface
  gradle/              Gradle wrapper
  build.gradle
  settings.gradle
  gradlew.bat
  backend/             Authenticated Google Cloud Gemini gateway
  model_dev/           Data preparation, tuning and evaluation scripts
  tests/               Offline backend tests
  docs/                Results, setup and implementation notes
```

## Run the app

1. Open this folder in Android Studio, sync Gradle, and run `app` on Android 9+.
2. Take or choose a photo, then tap **Read label** for local YOLO + ML Kit OCR.
3. Use **Read aloud** for speech. Scan options include contrast and geometric correction.
4. The separate Gemini section is ordered as **Base Gemini · Product details**,
   **Ask a question · Base Gemini**, then **Fine-tuned Gemini**. The two question
   buttons share the question/image choice and keep separate answers and speech.
5. Missing product details display as **Not visible**. Gemini needs internet;
   local OCR works offline. Connection settings remembers the token encrypted
   on the phone.
6. Each product field shows its supporting OCR quote or model-read image text.
   **Review or correct details** saves a checked reference separately from the
   original prediction; **Export reviewed scan** exports both with the images.
7. Future extraction comparison in **Evaluation tools** uses identical inputs. Until a matching
   product-extraction model is configured, it explains what is missing and makes
   no inference calls. The existing tuned QA model is a separate task.

The deployed backend URL and application token are in the local ignored file
`.tools/APP_CONNECTION.txt`. The token is not in the source code or APK.

## Backend and checks

Run commands from this same project folder:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\gradlew.bat assembleDebug lintDebug
```

For a new checkout, create a Python 3.12 virtual environment and install
`backend/requirements.txt`. Backend deployment uses the root Dockerfile and
uploads only backend source and the verified prompt; datasets, tokens, Android
files, and local tools are excluded.

## Project status

- Local detection, OCR, speech and optional geometric correction are implemented.
- Existing fine-tuned Gemini QA is connected through the Cloud Run gateway.
- Product extraction has separate product, brand, size, date and guidance fields;
  it currently uses base Gemini. No new product-extraction tuning was performed.
- Evidence, missing-field rescan instructions, checked-reference export, and
  paired model comparison are implemented. Device verification is still needed.
- Base and existing tuned QA models were compared on 20 validation examples.
- Full-system evaluation and a measured fine-tuning benefit remain future work.

See [Gemini setup](GEMINI_SETUP.md), [backend connection](docs/BACKEND_READY.md),
[product details](docs/PRODUCT_DETAILS.md), [QA results](docs/LIVE_GEMINI_RESULTS_20261111.md),
and [UI changes](docs/UI_CHANGES.md).

The superseded local app and old build caches are preserved in the Git-ignored
`.tools/archive/` directory; they are not active projects.
