package edu.cs663.labellens.project2;

import android.app.AlertDialog;
import android.graphics.Bitmap;
import android.graphics.ImageDecoder;
import android.net.Uri;
import android.os.Bundle;
import android.os.SystemClock;
import android.speech.tts.TextToSpeech;
import android.text.InputType;
import android.view.View;
import android.widget.*;
import androidx.activity.ComponentActivity;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.core.content.FileProvider;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import edu.cs663.labellens.project2.pipeline.*;
import org.json.JSONObject;
import java.io.*;
import java.util.Locale;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends ComponentActivity {
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final ExecutorService cloudWorker = Executors.newSingleThreadExecutor();
    private ScanPipeline pipeline;
    private GeminiConnectionStore connectionStore;
    private ActivityResultLauncher<Uri> takePhoto;
    private ActivityResultLauncher<String> choosePhoto, saveDocument;
    private Uri pendingCapture, selectedUri;
    private ImageView preview, cropPreview;
    private TextView status, result, cropInfo, geminiStatus, geminiResult;
    private CheckBox contrast, contextCrop, referenceReviewed;
    private EditText group, reference, question;
    private Spinner surface, condition, split, geminiImage;
    private Button camera, importPhoto, scan, fullPhoto, corrected, compare, speak, export, cancel, settings, askGemini, speakGemini;
    private ProgressBar progress, geminiProgress;
    private TextToSpeech tts;
    private boolean busy, cloudBusy, speechReady, connectionLoading = true;
    private volatile boolean closed;
    private volatile int generation, geminiGeneration;
    private volatile ScanPipeline.Result activeResult;
    private long captureStarted;
    private String endpoint = "", token = "", variant = "tuned", geminiSpeech = "";
    private File pendingExport;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        takePhoto = registerForActivityResult(new ActivityResultContracts.TakePicture(), ok -> {
            if (ok && pendingCapture != null) loadPhoto(pendingCapture);
            else status.setText("Photo cancelled. You can try again.");
        });
        choosePhoto = registerForActivityResult(new ActivityResultContracts.GetContent(), uri -> {
            if (uri != null) { captureStarted = 0; loadPhoto(uri); }
        });
        saveDocument = registerForActivityResult(new ActivityResultContracts.CreateDocument("application/zip"), uri -> {
            if (uri == null || pendingExport == null) return;
            File file = pendingExport; setBusy(true);
            worker.execute(() -> {
                try (InputStream in = new FileInputStream(file); OutputStream out = getContentResolver().openOutputStream(uri)) {
                    if (out == null) throw new IOException("Cannot open export destination");
                    byte[] buffer = new byte[65536]; int n;
                    while ((n = in.read(buffer)) != -1) out.write(buffer, 0, n);
                    runOnUiThread(() -> { if (!closed) { setBusy(false); status.setText("Scan record exported."); } });
                } catch (Exception error) {
                    runOnUiThread(() -> { if (!closed) { setBusy(false); status.setText("Could not save the export. Please try again."); } });
                }
            });
        });
        setContentView(R.layout.activity_main);
        pipeline = new ScanPipeline(this);
        connectionStore = new GeminiConnectionStore(this);
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.root), (v, insets) -> {
            androidx.core.graphics.Insets bars = insets.getInsets(WindowInsetsCompat.Type.systemBars());
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom); return insets;
        });
        preview = findViewById(R.id.preview); cropPreview = findViewById(R.id.crop_preview);
        status = findViewById(R.id.status); result = findViewById(R.id.result); cropInfo = findViewById(R.id.crop_info);
        progress = findViewById(R.id.progress); geminiProgress = findViewById(R.id.gemini_progress);
        geminiStatus = findViewById(R.id.gemini_status); geminiResult = findViewById(R.id.gemini_result);
        contrast = findViewById(R.id.higher_contrast); contextCrop = findViewById(R.id.context_crop);
        referenceReviewed = findViewById(R.id.reference_reviewed); group = findViewById(R.id.product_group);
        reference = findViewById(R.id.reference_text); question = findViewById(R.id.label_question);
        surface = findViewById(R.id.surface); condition = findViewById(R.id.condition); split = findViewById(R.id.dataset_split);
        geminiImage = findViewById(R.id.gemini_image);
        fill(surface, new String[]{"Keep original", "Flat label: perspective correction", "Bottle/can: experimental correction", "Folded or damaged: keep original"});
        fill(condition, new String[]{"Clean", "Cylindrical curvature", "Crumpled/folded", "Damaged/torn", "Partially occluded", "Glare/shadows"});
        fill(split, new String[]{"Development / not assigned", "Training", "Validation", "Final test"});
        fill(geminiImage, new String[]{"Whole photo", "Text crop from last scan"});
        camera = findViewById(R.id.camera); importPhoto = findViewById(R.id.import_photo);
        scan = findViewById(R.id.scan); fullPhoto = findViewById(R.id.full_photo); corrected = findViewById(R.id.corrected_scan);
        compare = findViewById(R.id.compare); speak = findViewById(R.id.speak); export = findViewById(R.id.export_scan);
        cancel = findViewById(R.id.cancel); settings = findViewById(R.id.backend_settings);
        askGemini = findViewById(R.id.ask_gemini); speakGemini = findViewById(R.id.speak_gemini);
        endpoint = getPreferences(MODE_PRIVATE).getString("backend", "https://labellens-qa-1056598944825.us-central1.run.app");
        variant = getPreferences(MODE_PRIVATE).getString("variant", "tuned");
        camera.setOnClickListener(v -> capture()); importPhoto.setOnClickListener(v -> choosePhoto.launch("image/*"));
        scan.setOnClickListener(v -> read("P2", false)); fullPhoto.setOnClickListener(v -> read("P1", false));
        corrected.setOnClickListener(v -> read("P3", false)); compare.setOnClickListener(v -> read("P3", true));
        speak.setOnClickListener(v -> { if (activeResult != null) say(activeResult.speech); });
        askGemini.setOnClickListener(v -> askGemini()); speakGemini.setOnClickListener(v -> say(geminiSpeech));
        settings.setOnClickListener(v -> backendSettings()); export.setOnClickListener(v -> exportScan());
        cancel.setOnClickListener(v -> {
            generation++; geminiGeneration++; cloudBusy = false; tts.stop(); setBusy(false);
            status.setText("Scan cancelled."); geminiStatus.setText("Request cancelled. Local text is still available.");
        });
        toggle(R.id.toggle_options, R.id.scan_options, "Scan options", "Hide scan options");
        toggle(R.id.toggle_study, R.id.study_options, "Evaluation tools", "Hide evaluation tools");
        tts = new TextToSpeech(this, code -> {
            if (closed) return;
            if (code == TextToSpeech.SUCCESS) {
                int language = tts.setLanguage(Locale.US);
                speechReady = language != TextToSpeech.LANG_MISSING_DATA && language != TextToSpeech.LANG_NOT_SUPPORTED;
            }
            setBusy(busy);
        });
        setBusy(false);
        restoreConnection();
        if (saved != null) {
            String pending = saved.getString("capture"), selected = saved.getString("selected");
            captureStarted = saved.getLong("capture_start", 0);
            if (pending != null) pendingCapture = Uri.parse(pending);
            if (selected != null) loadPhoto(Uri.parse(selected));
        }
    }

    private void restoreConnection() {
        String defaultEndpoint = endpoint, defaultVariant = variant;
        worker.execute(() -> {
            try {
                GeminiConnectionStore.Connection saved = connectionStore.load(defaultEndpoint, defaultVariant);
                runOnUiThread(() -> {
                    if (closed) return;
                    endpoint = saved.endpoint; token = saved.token; variant = saved.variant;
                    connectionLoading = false;
                    if (!token.isEmpty()) geminiStatus.setText("Saved Gemini connection loaded. Read a label above, then ask a question.");
                    setBusy(busy);
                });
            } catch (Exception error) {
                runOnUiThread(() -> {
                    if (closed) return;
                    connectionLoading = false; token = "";
                    geminiStatus.setText("Saved connection could not be opened. Enter your app token in Connection settings.");
                    setBusy(busy);
                });
            }
        });
    }

    private void toggle(int buttonId, int panelId, String show, String hide) {
        Button button = findViewById(buttonId); View panel = findViewById(panelId);
        button.setOnClickListener(v -> {
            boolean open = panel.getVisibility() != View.VISIBLE;
            panel.setVisibility(open ? View.VISIBLE : View.GONE); button.setText(open ? hide : show);
        });
    }

    private void capture() {
        try {
            File dir = new File(getCacheDir(), "captures");
            if (!dir.mkdirs() && !dir.isDirectory()) throw new IOException("Capture folder unavailable");
            pendingCapture = FileProvider.getUriForFile(this, getPackageName() + ".files", File.createTempFile("label_", ".jpg", dir));
            captureStarted = SystemClock.elapsedRealtime(); takePhoto.launch(pendingCapture);
        } catch (Exception error) { status.setText("Could not open the camera. Try choosing a photo."); }
    }

    private void resetGemini() {
        geminiGeneration++; cloudBusy = false; geminiSpeech = "";
        geminiResult.setText("Your Gemini answer will appear here.");
        geminiStatus.setText("Optional. Read a label above, then ask a question.");
    }

    private void loadPhoto(Uri uri) {
        int ticket = ++generation;
        selectedUri = uri; activeResult = null; resetGemini(); tts.stop(); setBusy(true);
        result.setText("Your label text will appear here."); status.setText("Opening photo...");
        cropPreview.setImageDrawable(null); cropPreview.setVisibility(View.GONE); cropInfo.setVisibility(View.GONE);
        worker.execute(() -> {
            try {
                Bitmap image = ImageDecoder.decodeBitmap(ImageDecoder.createSource(getContentResolver(), uri), (decoder, info, source) -> {
                    decoder.setAllocator(ImageDecoder.ALLOCATOR_SOFTWARE);
                    float scale = Math.min(1f, 2048f / Math.max(info.getSize().getWidth(), info.getSize().getHeight()));
                    decoder.setTargetSize(Math.max(1, Math.round(info.getSize().getWidth() * scale)), Math.max(1, Math.round(info.getSize().getHeight() * scale)));
                });
                runOnUiThread(() -> {
                    if (closed || ticket != generation) { image.recycle(); return; }
                    preview.setImageBitmap(image); setBusy(false); status.setText("Photo ready. Tap Read label.");
                });
            } catch (Exception error) {
                runOnUiThread(() -> {
                    if (closed || ticket != generation) return;
                    selectedUri = null; setBusy(false); status.setText("Could not open that photo. Choose another image.");
                });
            }
        });
    }

    private void read(String path, boolean comparison) {
        if (busy || selectedUri == null) return;
        int ticket = ++generation;
        activeResult = null; resetGemini(); tts.stop(); setBusy(true); result.setText("Reading...");
        ScanPipeline.Options options = new ScanPipeline.Options();
        options.path = path; options.compare = comparison; options.contrast = contrast.isChecked();
        options.contextCrop = contextCrop.isChecked(); options.cloud = false;
        options.surface = new String[]{"unspecified", "flat", "cylinder", "deformed"}[surface.getSelectedItemPosition()];
        options.condition = new String[]{"clean", "curved", "crumpled", "damaged", "occluded", "optical_noise"}[condition.getSelectedItemPosition()];
        options.split = new String[]{"development", "train", "validation", "test"}[split.getSelectedItemPosition()];
        options.group = group.getText().toString().trim(); options.reference = reference.getText().toString();
        options.referenceReviewed = referenceReviewed.isChecked();
        options.actionStart = SystemClock.elapsedRealtime(); options.captureStart = captureStarted;
        Uri uri = selectedUri;
        worker.execute(() -> {
            try {
                ScanPipeline.Result reading = pipeline.run(uri, options, message -> {
                    if (closed || ticket != generation) throw new CancellationException();
                    runOnUiThread(() -> { if (!closed && ticket == generation) status.setText(message); });
                });
                runOnUiThread(() -> {
                    if (closed || ticket != generation) return;
                    activeResult = reading; preview.setImageBitmap(reading.source); cropPreview.setImageBitmap(reading.crop);
                    cropPreview.setVisibility(View.VISIBLE); cropInfo.setVisibility(View.VISIBLE);
                    cropInfo.setText(String.format(Locale.US, "Text image: %d × %d pixels", reading.crop.getWidth(), reading.crop.getHeight()));
                    result.setText(reading.display);
                    status.setText(String.format(Locale.US, "Local reading completed in %.2f seconds.", reading.record.optLong("analysis_to_result_ms") / 1000.0));
                    geminiStatus.setText("Ready when you are. Ask Gemini a question below."); setBusy(false);
                });
            } catch (CancellationException ignored) {
            } catch (Exception | LinkageError error) {
                android.util.Log.e("LabelLens", "Scan failed", error);
                runOnUiThread(() -> {
                    if (closed || ticket != generation) return;
                    setBusy(false); result.setText("Reading could not finish. Try another photo or Read full photo.");
                    status.setText("Hold steady, improve the light, and try again.");
                });
            }
        });
    }

    private void askGemini() {
        ScanPipeline.Result reading = activeResult;
        if (busy || cloudBusy || reading == null) return;
        String asked = question.getText().toString().trim();
        if (asked.isEmpty()) { geminiStatus.setText("Enter a question about this label."); question.requestFocus(); return; }
        if (endpoint.isEmpty() || token.length() < 24) {
            geminiStatus.setText("Enter your app token in Connection settings, then tap Ask Gemini."); backendSettings(); return;
        }
        int ticket = ++geminiGeneration;
        String service = endpoint, secret = token, model = variant;
        boolean full = geminiImage.getSelectedItemPosition() == 0;
        Bitmap image = full ? reading.source : reading.crop;
        JSONObject stage = reading.record.optJSONObject("paths").optJSONObject(reading.record.optString("primary_path"));
        String imageName = full || stage == null ? "source.png" : stage.optString("image", "source.png");
        cloudBusy = true; geminiSpeech = ""; tts.stop();
        geminiStatus.setText("Asking Gemini... Your local text is ready above."); geminiResult.setText("Waiting for an answer..."); setBusy(busy);
        cloudWorker.execute(() -> {
            if (closed || ticket != geminiGeneration) return;
            long started = SystemClock.elapsedRealtime();
            try {
            worker.execute(() -> {
                try {
                    reading.record.remove("semantic"); reading.record.remove("semantic_error");
                    reading.record.put("semantic_requested", true).put("gemini_question", asked)
                        .put("gemini_trigger", "separate_user_action")
                        .put("gemini_input_image", imageName)
                        .put("gemini_input_policy", "single_selected_image_without_ocr_or_extra_context");
                    ScanStore.writeRecord(reading.directory, reading.record);
                } catch (Exception error) { android.util.Log.e("LabelLens", "Request record save failed", error); }
            });
                JSONObject answer = GeminiGateway.answer(service, secret, model, reading.record.getString("scan_id"), image, asked);
                long elapsed = SystemClock.elapsedRealtime() - started;
                JSONObject qa = answer.getJSONObject("qa");
                String response = qa.getBoolean("answerable") ? qa.getString("answer") : answer.optString("guidance", "Try a clearer photo.");
                runOnUiThread(() -> {
                    if (closed || ticket != geminiGeneration || activeResult != reading) return;
                    cloudBusy = false; geminiSpeech = response; geminiResult.setText(response);
                    geminiStatus.setText(String.format(Locale.US, "%s · %.2f seconds", model.equals("tuned") ? "Fine-tuned Gemini" : "Base Gemini", elapsed / 1000.0)); setBusy(busy);
                    worker.execute(() -> {
                        try {
                            reading.record.put("semantic_requested", true).put("semantic", answer)
                                .put("gemini_question", asked).put("cloud_round_trip_ms", elapsed)
                                .put("gemini_trigger", "separate_user_action")
                                .put("gemini_input_image", imageName)
                                .put("gemini_input_policy", "single_selected_image_without_ocr_or_extra_context");
                            ScanStore.writeRecord(reading.directory, reading.record);
                        } catch (Exception error) { android.util.Log.e("LabelLens", "Answer record save failed", error); }
                    });
                });
            } catch (Exception error) {
                long elapsed = SystemClock.elapsedRealtime() - started;
                runOnUiThread(() -> {
                    if (closed || ticket != geminiGeneration || activeResult != reading) return;
                    cloudBusy = false; geminiResult.setText("Gemini could not answer. Your local OCR text is still available above.");
                    geminiStatus.setText(error instanceof IOException ? error.getMessage() : "Try again with a clearer photo."); setBusy(busy);
                    worker.execute(() -> {
                        try {
                            reading.record.put("semantic_error", error.getMessage() == null ? "Gemini request failed" : error.getMessage())
                                .put("cloud_round_trip_ms", elapsed);
                            ScanStore.writeRecord(reading.directory, reading.record);
                        } catch (Exception failure) { android.util.Log.e("LabelLens", "Failure record save failed", failure); }
                    });
                });
            }
        });
    }

    private void backendSettings() {
        if (connectionLoading) { geminiStatus.setText("Loading your saved connection..."); return; }
        LinearLayout fields = new LinearLayout(this); fields.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (24 * getResources().getDisplayMetrics().density); fields.setPadding(pad, 0, pad, 0);
        EditText url = new EditText(this); url.setHint("HTTPS backend URL"); url.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI); url.setText(endpoint); fields.addView(url);
        TextView help = new TextView(this); help.setText("Paste the application token from APP_CONNECTION.txt. This app saves it encrypted on this device."); fields.addView(help);
        EditText secret = new EditText(this); secret.setHint("Application token"); secret.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        secret.setSaveEnabled(false); secret.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO); secret.setText(token); fields.addView(secret);
        Spinner model = new Spinner(this); fill(model, new String[]{"Fine-tuned Gemini", "Base Gemini (comparison)"}); model.setSelection(variant.equals("base") ? 1 : 0); fields.addView(model);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("Gemini connection").setView(fields)
            .setNegativeButton("Cancel", null).setNeutralButton("Forget token", null).setPositiveButton("Save", null).create();
        dialog.show();
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String address = url.getText().toString().trim(), entered = secret.getText().toString().trim();
            String selectedVariant = model.getSelectedItemPosition() == 0 ? "tuned" : "base";
            Uri parsed = Uri.parse(address);
            if (!"https".equalsIgnoreCase(parsed.getScheme()) || parsed.getHost() == null || parsed.getUserInfo() != null) {
                url.setError("Enter the HTTPS backend address from APP_CONNECTION.txt"); return;
            }
            if (entered.length() < 24) { secret.setError("Paste the full application token from APP_CONNECTION.txt"); return; }
            connectionDialogBusy(dialog, true);
            worker.execute(() -> {
                try {
                    connectionStore.save(address, entered, selectedVariant);
                    runOnUiThread(() -> {
                        if (closed) return;
                        endpoint = address; token = entered; variant = selectedVariant;
                        geminiStatus.setText("Connection saved on this device. It will be remembered when you reopen the app."); dialog.dismiss();
                    });
                } catch (Exception error) {
                    runOnUiThread(() -> {
                        if (closed) return;
                        connectionDialogBusy(dialog, false); secret.setError("Could not securely save the connection. Please try again.");
                    });
                }
            });
        });
        dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(v -> {
            connectionDialogBusy(dialog, true);
            worker.execute(() -> {
                try {
                    connectionStore.forgetToken();
                    runOnUiThread(() -> {
                        if (closed) return;
                        token = ""; geminiStatus.setText("Saved token removed. Local reading is still available."); dialog.dismiss();
                    });
                } catch (Exception error) {
                    runOnUiThread(() -> { if (!closed) { connectionDialogBusy(dialog, false); secret.setError("Could not remove the saved token. Please try again."); } });
                }
            });
        });
    }

    private void connectionDialogBusy(AlertDialog dialog, boolean value) {
        dialog.setCancelable(!value); dialog.setCanceledOnTouchOutside(!value);
        for (int button : new int[]{AlertDialog.BUTTON_POSITIVE, AlertDialog.BUTTON_NEGATIVE, AlertDialog.BUTTON_NEUTRAL}) dialog.getButton(button).setEnabled(!value);
    }

    private void exportScan() {
        ScanPipeline.Result reading = activeResult;
        if (reading == null || busy || cloudBusy) return;
        setBusy(true); status.setText("Preparing the scan export...");
        worker.execute(() -> {
            try {
                ScanStore.save(this, reading.record.getString("scan_id"), reading.record, reading.images);
                File zip = ScanStore.export(this, reading.directory);
                runOnUiThread(() -> { if (!closed) { pendingExport = zip; setBusy(false); saveDocument.launch(zip.getName()); } });
            } catch (Exception error) {
                runOnUiThread(() -> { if (!closed) { setBusy(false); status.setText("Could not prepare the export. Please try again."); } });
            }
        });
    }

    private void say(String text) {
        if (!closed && speechReady && text != null && !text.isEmpty()) tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "user-reading");
    }

    private void setBusy(boolean value) {
        busy = value;
        if (camera == null) return;
        camera.setEnabled(!value); importPhoto.setEnabled(!value);
        scan.setEnabled(!value && selectedUri != null); fullPhoto.setEnabled(!value && selectedUri != null);
        corrected.setEnabled(!value && selectedUri != null); compare.setEnabled(!value && !cloudBusy && selectedUri != null);
        contrast.setEnabled(!value); contextCrop.setEnabled(!value); surface.setEnabled(!value);
        condition.setEnabled(!value); split.setEnabled(!value); group.setEnabled(!value); reference.setEnabled(!value); referenceReviewed.setEnabled(!value);
        settings.setEnabled(!cloudBusy && !connectionLoading); question.setEnabled(!cloudBusy); geminiImage.setEnabled(!cloudBusy);
        speak.setEnabled(!value && speechReady && activeResult != null);
        askGemini.setEnabled(!value && !cloudBusy && activeResult != null);
        speakGemini.setEnabled(speechReady && !geminiSpeech.isEmpty()); export.setEnabled(!value && !cloudBusy && activeResult != null);
        cancel.setEnabled(value || cloudBusy); cancel.setVisibility(value || cloudBusy ? View.VISIBLE : View.GONE);
        progress.setVisibility(value ? View.VISIBLE : View.GONE); geminiProgress.setVisibility(cloudBusy ? View.VISIBLE : View.GONE);
    }

    private void fill(Spinner spinner, String[] values) {
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, values);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item); spinner.setAdapter(adapter);
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        if (pendingCapture != null) state.putString("capture", pendingCapture.toString());
        if (selectedUri != null) state.putString("selected", selectedUri.toString()); state.putLong("capture_start", captureStarted);
    }

    @Override protected void onDestroy() {
        closed = true; generation++; geminiGeneration++; cloudWorker.shutdownNow();
        worker.execute(() -> pipeline.close()); worker.shutdown();
        if (tts != null) { tts.stop(); tts.shutdown(); } super.onDestroy();
    }
}
