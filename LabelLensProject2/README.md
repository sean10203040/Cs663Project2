# LabelLens Project 2

A separate Android app for CS663 Project 2. App ID: `edu.cs663.labellens.project2`.
It can be installed alongside Project 1 if that app uses a different ID.

## Available now

- Capture a full-resolution photo using the phone's camera app, or import an image.
- Correct photo orientation and use a preview bounded to 2048 pixels for detection.
- Read Latin-script text using bundled, on-device ML Kit OCR.
- Run the supplied `best.tflite` detector, show the strongest product-name box,
  and read a crop from the original photo (decoded with a 4096-pixel longest-side limit).
  Add an 8% horizontal / 12% vertical margin on each side. If detection fails, offer full-photo reading.
- Show the exact OCR crop and dimensions. Optionally try a mild grayscale/contrast
  alternative; original colors are the default. No automatic spelling correction is applied.
- Display the raw recognized text, report OCR processing duration, and read it aloud.
- Give rescan guidance when no text is recognized. This is not calibrated confidence.

Two paths are available: **Read label (P2): YOLO -> crop -> OCR** and
**Read full photo (P1): full photo -> OCR**. With multiple detections, Read label
uses the highest-scoring box. Displayed detector scores are not calibrated OCR confidence.
The app does not perform semantic product identification or attribute parsing.
Processing duration excludes camera capture and speech startup; P2 includes detection,
crop creation, and OCR, including model initialization on the first scan.
Photo processing is local; this app has no Internet permission. Imported images are
not copied; captured photos remain in app cache until cleared by Android or the user.

## Open and run

1. Open this directory in Android Studio and sync Gradle.
2. Select Android Studio's bundled JDK. This project uses Gradle 9.3.0 (JDK 17+)
   and Java 17 source compatibility.
3. Run `app` on an Android 9 / API 28 or newer phone or emulator.
4. Choose a label photo, tap **Read label**, inspect the green box and text, then **Read aloud**.
5. Tap **Read full photo (comparison)** to read text beyond the product-name region.
6. If letters are missing, select **Try higher contrast for label reading** and tap
   **Read label** again on the same photo. Compare both outputs to the printed label;
   contrast is an experiment, not a guarantee of improvement.

The first Gradle sync needs network access to fetch build dependencies.
Speech requires an installed English text-to-speech voice. Use a phone camera for
real capture testing; image import also works on emulators.

## Included detector

The inspected Ultralytics 8.4.171 export has FP32 input `[1,3,320,320]` (NCHW RGB,
values 0..1), FP32 output `[1,5,2100]`, class `0: product_name`, and no embedded NMS.
`YoloLabelDetector` uses gray-114 letterboxing, converts normalized center-x/center-y/
width/height to input pixels, removes padding, applies a 0.25 score threshold and 0.45 IoU
NMS, and maps boxes to the source image. It validates tensor shapes on load.

The current class is `product_name`; crops may exclude brand, size, or dates.
Label-panel detection requires appropriate annotations. Inspect the model again before
replacing it with a different export: identical tensor shapes do not guarantee identical semantics.

## Next integration steps

1. Add P3: detect -> geometric correction -> OCR. Treat perspective and curved-surface
   correction as separate methods; a four-point homography does not flatten a can.
2. Add Gemini parsing through an authenticated backend. Supply crop + OCR evidence,
   use a structured schema and missing values, and keep cloud credentials off the phone.
3. Compare P1/P2/P3 on unseen product groups with manual text ground truth. Report CER,
   attribute accuracy, failures by packaging condition, and end-to-end latency.

Geometric correction, Gemini integration, calibrated uncertainty, and dataset evaluation
are pending. No simulated detection results are included.

For OCR error analysis, keep the same photos and manually transcribe each label.
Compare old 2048-preview crops, original-photo crops, and optional contrast crops using
character error rate. Curvature, glare, blur, and stylized fonts can still cause missing
letters. This update has not been evaluated on the reported Pocari Sweat bottle photo.

## Manual device checks

- Import a clear label, read it, and verify text and speech against the image.
- Import an image with no text; verify rescan guidance and disabled Read aloud.
- Try a sideways photo and a large photo; verify orientation and responsiveness.
- Cancel capture/import, rotate the phone, and scan again.
- Repeat with airplane mode (OCR works offline; speech depends on the installed voice).

## Automated device checks

Run `gradlew.bat connectedDebugAndroidTest` with an authorized device attached.
The instrumentation checks execute the real model and verify its tensor layout and
normalized coordinate range, exercise portrait/landscape input, verify padding removal
and duplicate-box suppression, and check OCR against
generated text. Additional checks cover original-detail crop decoding, margin clamping,
and recognition of a synthetic POCARI SWEAT label in original and contrast modes.
These smoke checks do not establish accuracy on real products.

## References

- ML Kit: https://developers.google.com/ml-kit/vision/text-recognition/v2/android
- Android Gradle plugin: https://developer.android.com/build/releases/about-agp
- Interpreter API: https://developers.google.com/edge/api/tflite/java/org/tensorflow/lite/Interpreter
