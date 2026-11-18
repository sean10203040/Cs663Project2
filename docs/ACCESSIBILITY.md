# Accessibility update — November 18, 2026

This update improves the Android reader and both Gemini result sections. It does
not change the detector, OCR model, Gemini endpoint, cloud configuration or token.

## Changes

- **Stop reading aloud** stops current and queued app speech. Starting another
  reading/request or cancelling resets the speech controls consistently.
- Local **Read aloud** and **Stop reading aloud** appear above the OCR transcript,
  so long results do not bury them. Scan options includes **Text size (Android
  settings)**, which opens the phone's Display settings. The 200% setting used
  in testing is a system font-size setting, not a separate in-app zoom control.
- Long readings are split into Android-sized utterances, preserving word order
  and Unicode surrogate pairs. Users explicitly choose when to read aloud.
- Speech readiness, completion and failure are shown in text. If an English voice
  is missing or speech fails, **Speech settings** opens Android's voice settings.
  Text results remain available. The speech-status live region is paused during
  app narration to avoid announcing that same status over the requested reading.
- Connection fields and evaluation controls have persistent native labels rather
  than relying solely on disappearing hints. Product-review editors, evidence
  source selectors, certainty and split selectors also have associated labels.
  The app token remains a password input and is not copied into a content label.
- Scan-options and evaluation-tools controls expose expanded/collapsed state.
  Product result cards have distinct accessibility pane titles; fine-tuned
  subsections are headings. Decorative branding and progress bars are excluded
  from redundant screen-reader traversal; existing status text announces progress.
- Dropdowns wrap selected text and menu choices instead of using fixed-height,
  single-line text. They retain at least 48dp targets. Default body text is 16sp;
  explicitly styled headings, values and supporting text retain their hierarchy.
- Connection settings scroll at large font sizes. The keyboard stays hidden on
  entry while forms can resize when it opens. Existing `sp` text respects system
  font scaling; the app does not override the user's font size.

Native labels, headings, live regions and controls follow the
[Android accessibility principles](https://developer.android.com/guide/topics/ui/accessibility/principles).

## Verification

On the existing **Medium Phone / Android 15 emulator**:

| Check | Result |
| --- | --- |
| Four accessibility instrumentation tests at normal font size | Passed |
| Same four checks at 200% system font size | Passed |
| Local photo import, OCR and export flow, including speech/stop or unavailable-voice recovery | Passed |
| Android debug APK and instrumentation APK build | Passed |
| Android lint | 0 errors; existing project warnings remain |
| Normal and 200% text screenshots | Visually inspected for wrapping/clipping |

Tests check persistent labels on the main form, minimum control targets, pane
titles, collapsible state, dropdown layout, populated connection-field labels,
password semantics, and long-text splitting. The local-flow test uses a synthetic
label fixture and makes no Gemini request. These fixtures are not project accuracy
results. The final announcement adjustment was rebuilt and linted after the
instrumentation runs. No APK was installed on the physical phone.

Local verification artifacts are under `.tools/accessibility-review/`, including
the two font-size test results, local-flow result and screenshots. The emulator's
original font size was restored. No physical-phone accessibility settings changed.

## Physical-phone TalkBack walkthrough still needed

This is an implementation and automated-verification pass, not an accessibility
certification or a study with blind/low-vision participants. Accessibility-node
checks do not verify audible announcement timing, camera usability, or every
TalkBack/OEM behavior.

Rebuild/run the project on the phone. Then:

1. Enable TalkBack in Android Settings → Accessibility. Swipe left/right to move
   through controls and double-tap to activate them. Confirm headings are useful
   and every photo, scan, speech and Gemini action is reachable in order.
2. Choose or capture a label. Run local reading, find **Label text**, activate
   **Read aloud**, and stop it with **Stop reading aloud**. Repeat with a long label.
3. Open and close Scan options. Check surface choices and expanded/collapsed
   feedback. At the largest font size you normally use, check that controls wrap
   and remain reachable by scrolling.
4. Read base and fine-tuned product details. Confirm each result card is identified
   correctly and product, brand, size, date, evidence and guidance can be reached.
   Try an unreadable label and a disconnected network; recovery instructions
   should be understandable while local reading remains available.
5. Open Connection settings. Verify both filled fields keep their labels and
   the token remains masked. Check product-review field/source labels too.

If spoken status interrupts app narration or focus moves unexpectedly, record the
exact action and phone/TalkBack version so the behavior can be reproduced.

To rerun the four automated accessibility checks on an emulator:

```powershell
.\gradlew.bat :app:connectedDebugAndroidTest '-Pandroid.testInstrumentationRunnerArguments.class=edu.cs663.labellens.project2.AccessibilityTest'
```
