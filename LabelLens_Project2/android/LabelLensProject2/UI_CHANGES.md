# Local reader and optional Gemini section

The main screen starts with photo capture/import, local Read label and Read full
photo actions, recognized text, and a manual Read aloud button. Taking a photo
does not automatically start reading or speech.

Gemini has a separate section underneath, with its own question, image choice,
Ask Gemini action, answer, and Read answer aloud button. The whole photo is the
default Gemini input; the text crop is also available. Local scans never invoke
Gemini and do not need a connection token. Local reading and its result remain
available while a Gemini request runs. A new photo or scan invalidates stale
answers. Cancelling does not recall a request already sent to the cloud.

Scan options and evaluation fields are collapsed by default. Read label uses
the existing detector and padded crop (P2); geometric correction remains
available under Scan options. Comparison and export tools remain available
under Evaluation tools.

Normal reading saves a small JSON record, then displays the result. Large PNG
images are written only when Export scan record is selected. Until exported,
the current scan images live in memory and can be lost when a new scan is
started or the activity is recreated. Exports include original images, OCR
inputs, comparison paths when requested, and completed Gemini responses.

No automatic product-name announcements or cloud requests are made. Use the
separate speech buttons for local text or Gemini answers. The backend address
is prefilled. Enter the app token once in Connection settings and save it.
The token is encrypted with an AES-GCM key held in Android Keystore, and the
connection reloads on app startup. Forget token removes the stored credential.
Clearing app data or uninstalling the app removes the saved connection. The token
is not embedded in source or the APK. Crypto and disk operations run on a worker.

Validation: debug build and lint; six native model/OCR checks; an Android UI
flow test covers photo import without automatic reading, local OCR without
Gemini setup, separate answer state, and deferred-image export. Synthetic test
images do not establish real-product OCR accuracy. Gemini service execution
was previously verified through the HTTPS backend; this layout test makes no
cloud inference requests.
