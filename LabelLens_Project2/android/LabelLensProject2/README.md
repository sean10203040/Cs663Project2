# LabelLens Project 2 - updated source

Read ../../GEMINI_SETUP.md from the package root for complete setup.

Implemented source includes shared-resolution P1/P2/P3 processing, explicit OpenCV planar and experimental cylinder correction, raw OCR/polygon records, optional authenticated Gemini image-question integration, spoken failure guidance, cancellation and scan export. The existing product_name detector is retained. The current integration reuses the existing tuned model's answer/answerable contract; it does not claim structured product attributes.

Open this folder in Android Studio with a compatible JDK 17+ and an API 28+ device. Configure the HTTPS backend before enabling Ask Gemini. Enter a question about the selected image. Cloud credentials stay on the server; the app uses a per-demo application token. Local OCR is retained but is not sent as additional input to the existing image-question model.

The Android changes have not been built or runtime-tested. Local build work was stopped at the user request. The existing cloud tuning job succeeded; the updated gateway, held-out comparison and device measurements have not been run live. Eight offline Python QA checks passed, which does not establish mobile functionality or model accuracy.

The existing instrumentation tests are source checks to run on your device, not proof of accuracy on real labels. Inspect correction results; a homography does not unwrap arbitrary folds and the cylinder mode assumes a declared front arc.
