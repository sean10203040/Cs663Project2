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
    private TextView tunedStatus, tunedResult;
    private Button askTuned, speakTuned;
    private String tunedSpeech = "";
    private TextView detailsStatus, detailProduct, detailBrand, detailSize, detailDate, detailsGuidance, detailsCertainty;
    private View detailsCard;
    private CheckBox detailsContext;
    private Button analyzeDetails, speakDetails;
    private String detailsSpeech = "";
    private JSONObject detailsReading;
    private String detailsInputCrop, detailsInputOcr;
    private boolean detailsInputContext;
    private TextView[] detailEvidence;
    private Button compareProducts, reviewDetails, exportReviewed;
    private TextView productComparisonStatus;
    private LinearLayout productComparison;
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
        tunedStatus = findViewById(R.id.tuned_status); tunedResult = findViewById(R.id.tuned_result);
        askTuned = findViewById(R.id.ask_tuned); speakTuned = findViewById(R.id.speak_tuned);
        detailsStatus = findViewById(R.id.details_status); detailsCard = findViewById(R.id.details_card);
        detailProduct = findViewById(R.id.detail_product); detailBrand = findViewById(R.id.detail_brand);
        detailSize = findViewById(R.id.detail_size); detailDate = findViewById(R.id.detail_date);
        detailsGuidance = findViewById(R.id.details_guidance); detailsCertainty = findViewById(R.id.details_certainty);
        detailsContext = findViewById(R.id.details_context); analyzeDetails = findViewById(R.id.analyze_details);
        speakDetails = findViewById(R.id.speak_details);
        detailEvidence = new TextView[]{findViewById(R.id.evidence_product),findViewById(R.id.evidence_brand),findViewById(R.id.evidence_size),findViewById(R.id.evidence_date)};
        compareProducts = findViewById(R.id.compare_products); reviewDetails = findViewById(R.id.review_details);
        exportReviewed = findViewById(R.id.export_reviewed); productComparisonStatus = findViewById(R.id.product_comparison_status);
        productComparison = findViewById(R.id.product_comparison);
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
        askGemini.setOnClickListener(v -> askGemini("base")); speakGemini.setOnClickListener(v -> say(geminiSpeech));
        askTuned.setOnClickListener(v -> askGemini("tuned")); speakTuned.setOnClickListener(v -> say(tunedSpeech));
        analyzeDetails.setOnClickListener(v -> analyzeDetails()); speakDetails.setOnClickListener(v -> say(detailsSpeech));
        compareProducts.setOnClickListener(v -> compareProducts()); reviewDetails.setOnClickListener(v -> reviewDetails());
        exportReviewed.setOnClickListener(v -> exportScan());
        settings.setOnClickListener(v -> backendSettings()); export.setOnClickListener(v -> exportScan());
        cancel.setOnClickListener(v -> {
            generation++; geminiGeneration++; cloudBusy = false; tts.stop(); setBusy(false);
            status.setText("Scan cancelled."); geminiStatus.setText("Request cancelled. Local text is still available.");
            tunedStatus.setText("Request cancelled. Local text is still available.");
            detailsStatus.setText("Request cancelled. Tap Analyze product details to try again.");
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
        geminiGeneration++; cloudBusy = false; geminiSpeech = ""; tunedSpeech = "";
        geminiResult.setText("Your base Gemini answer will appear here.");
        geminiStatus.setText("Enter a question, then tap Ask base Gemini.");
        tunedResult.setText("Your fine-tuned Gemini answer will appear here.");
        tunedStatus.setText("Uses the question and image selected above.");
        detailsSpeech = ""; detailsReading = null; detailsCard.setVisibility(View.GONE);
        productComparison.removeAllViews(); productComparisonStatus.setText("Compare base and fine-tuned product extraction on the same photo and OCR.");
        detailsStatus.setText("Read a label above to begin.");
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
                    geminiStatus.setText("Ready when you are. Ask Gemini a question below.");
                    detailsStatus.setText("Ready. Analyze details using this image and its OCR text."); setBusy(false);
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

    private void askGemini(String model) {
        ScanPipeline.Result reading = activeResult;
        if (busy || cloudBusy || reading == null || connectionLoading) return;
        TextView answerStatus = model.equals("tuned") ? tunedStatus : geminiStatus;
        TextView answerResult = model.equals("tuned") ? tunedResult : geminiResult;
        String modelLabel = model.equals("tuned") ? "Fine-tuned Gemini" : "Base Gemini";
        String asked = question.getText().toString().trim();
        if (asked.isEmpty()) { answerStatus.setText("Enter a question about this label above."); question.requestFocus(); return; }
        if (endpoint.isEmpty() || token.length() < 24) {
            answerStatus.setText("Enter your app token in Connection settings, then try again."); backendSettings(); return;
        }
        int ticket = ++geminiGeneration;
        String service = endpoint, secret = token;
        boolean full = geminiImage.getSelectedItemPosition() == 0;
        Bitmap image = full ? reading.source : reading.crop;
        JSONObject stage = reading.record.optJSONObject("paths").optJSONObject(reading.record.optString("primary_path"));
        String imageName = full || stage == null ? "source.png" : stage.optString("image", "source.png");
        cloudBusy = true;
        if(model.equals("tuned"))tunedSpeech="";else geminiSpeech="";
        tts.stop();
        answerStatus.setText("Asking " + modelLabel + "... Your local text is ready above."); answerResult.setText("Waiting for an answer..."); setBusy(busy);
        cloudWorker.execute(() -> {
            if (closed || ticket != geminiGeneration) return;
            long started = SystemClock.elapsedRealtime();
            try {
            worker.execute(() -> {
                try {
                    reading.record.remove("semantic"); reading.record.remove("semantic_error");
                    JSONObject answers=reading.record.optJSONObject("qa_answers");
                    if(answers==null){answers=new JSONObject();reading.record.put("qa_answers",answers);}
                    answers.put(model,new JSONObject().put("status","pending").put("question",asked).put("input_image",imageName));
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
                    cloudBusy = false;
                    if(model.equals("tuned"))tunedSpeech=response;else geminiSpeech=response;
                    answerResult.setText(response);
                    answerStatus.setText(String.format(Locale.US, "%s · %.2f seconds\nQuestion: %s\nImage: %s", modelLabel, elapsed / 1000.0, asked, full ? "Whole photo" : "Text crop")); setBusy(busy);
                    worker.execute(() -> {
                        try {
                            reading.record.put("semantic_requested", true).put("semantic", answer)
                                .put("gemini_question", asked).put("cloud_round_trip_ms", elapsed)
                                .put("gemini_trigger", "separate_user_action")
                                .put("gemini_input_image", imageName)
                                .put("gemini_input_policy", "single_selected_image_without_ocr_or_extra_context");
                            reading.record.getJSONObject("qa_answers").put(model,new JSONObject().put("status","ok").put("response",answer)
                                .put("question",asked).put("input_image",imageName).put("round_trip_ms",elapsed));
                            ScanStore.writeRecord(reading.directory, reading.record);
                        } catch (Exception error) { android.util.Log.e("LabelLens", "Answer record save failed", error); }
                    });
                });
            } catch (Exception error) {
                long elapsed = SystemClock.elapsedRealtime() - started;
                runOnUiThread(() -> {
                    if (closed || ticket != geminiGeneration || activeResult != reading) return;
                    cloudBusy = false; answerResult.setText(modelLabel + " could not answer. Your local OCR text is still available above.");
                    answerStatus.setText(error instanceof IOException ? error.getMessage() : "Try again with a clearer photo."); setBusy(busy);
                    worker.execute(() -> {
                        try {
                            reading.record.put("semantic_error", error.getMessage() == null ? "Gemini request failed" : error.getMessage())
                                .put("cloud_round_trip_ms", elapsed);
                            JSONObject answers=reading.record.optJSONObject("qa_answers");
                            if(answers==null){answers=new JSONObject();reading.record.put("qa_answers",answers);}
                            answers.put(model,new JSONObject().put("status","error").put("question",asked).put("input_image",imageName)
                                .put("error",error.getMessage()==null?"Gemini request failed":error.getMessage()).put("round_trip_ms",elapsed));
                            ScanStore.writeRecord(reading.directory, reading.record);
                        } catch (Exception failure) { android.util.Log.e("LabelLens", "Failure record save failed", failure); }
                    });
                });
            }
        });
    }

    private void analyzeDetails() {
        ScanPipeline.Result reading = activeResult;
        if (busy || cloudBusy || reading == null || connectionLoading) return;
        if (endpoint.isEmpty() || token.length() < 24) {
            detailsStatus.setText("Add your app token in Connection settings, then try again."); backendSettings(); return;
        }
        int ticket = ++geminiGeneration;
        String service = endpoint, secret = token, scanId = reading.record.optString("scan_id");
        String ocr = reading.record.optString("primary_ocr_text");
        boolean includeContext = detailsContext.isChecked() && reading.source != reading.crop;
        Bitmap context = includeContext ? reading.source : null;
        JSONObject stage = reading.record.optJSONObject("paths").optJSONObject(reading.record.optString("primary_path"));
        String imageName = stage == null ? "source.png" : stage.optString("image", "source.png");
        cloudBusy = true; detailsSpeech = ""; detailsReading = null; detailsCard.setVisibility(View.GONE); tts.stop();
        detailsStatus.setText("Analyzing product details... Local text is still available above."); setBusy(busy);
        worker.execute(() -> {
            try {
                reading.record.remove("product_details"); reading.record.remove("product_details_error");
                reading.record.put("product_details_requested", true).put("product_details_variant", "base")
                    .put("product_details_crop", imageName).put("product_details_context", includeContext ? "source.png" : JSONObject.NULL)
                    .put("product_details_ocr_text", ocr);
                ScanStore.writeRecord(reading.directory, reading.record);
            } catch (Exception error) { android.util.Log.e("LabelLens", "Details request record failed", error); }
        });
        cloudWorker.execute(() -> {
            if (closed || ticket != geminiGeneration) return;
            long started = SystemClock.elapsedRealtime();
            try {
                JSONObject response = GeminiGateway.productDetails(service, secret, scanId, reading.crop, context, ocr);
                JSONObject fields = response.getJSONObject("reading");
                // Format before publishing so malformed responses cannot leave a half-populated card.
                String product = ProductDetails.value(fields, "product_name"), brand = ProductDetails.value(fields, "brand");
                String size = ProductDetails.value(fields, "size"), date = ProductDetails.value(fields, "best_by");
                String guidance = ProductDetails.guidance(fields), spoken = ProductDetails.speech(fields);
                String certainty = "Model-reported certainty: " + fields.getString("confidence") + ". Not calibrated.";
                long elapsed = SystemClock.elapsedRealtime() - started;
                runOnUiThread(() -> {
                    if (closed || ticket != geminiGeneration || activeResult != reading) return;
                    cloudBusy = false; detailsSpeech = spoken; detailsReading = fields;
                    detailsInputCrop = imageName; detailsInputOcr = ocr; detailsInputContext = includeContext;
                    detailProduct.setText(product); detailBrand.setText(brand); detailSize.setText(size); detailDate.setText(date);
                    try { String[] keys={"product_name","brand","size","best_by"};
                        for(int i=0;i<keys.length;i++)detailEvidence[i].setText(ProductDetails.evidence(fields,keys[i]));
                    } catch(Exception impossible) { android.util.Log.e("LabelLens","Evidence display failed",impossible); }
                    detailsGuidance.setText(guidance); detailsCertainty.setText(certainty); detailsCard.setVisibility(View.VISIBLE);
                    detailsStatus.setText(String.format(Locale.US, "Base Gemini · %.2f seconds · %s", elapsed / 1000.0, response.optString("model")));
                    setBusy(busy);
                    worker.execute(() -> {
                        try {
                            reading.record.put("product_details", response).put("product_details_round_trip_ms", elapsed);
                            ScanStore.writeRecord(reading.directory, reading.record);
                        } catch (Exception error) { android.util.Log.e("LabelLens", "Details response record failed", error); }
                    });
                });
            } catch (Exception error) {
                long elapsed = SystemClock.elapsedRealtime() - started;
                runOnUiThread(() -> {
                    if (closed || ticket != geminiGeneration || activeResult != reading) return;
                    cloudBusy = false;
                    String message = error instanceof java.net.UnknownHostException ? "Connect your phone to Wi-Fi or mobile data, then try again."
                        : error instanceof java.net.SocketTimeoutException ? "The request timed out. Try again."
                        : error instanceof IOException ? error.getMessage() : "Product details could not be read. Try a clearer photo.";
                    detailsStatus.setText(message + " Local OCR is still available above."); setBusy(busy);
                    worker.execute(() -> {
                        try {
                            reading.record.put("product_details_error", message).put("product_details_round_trip_ms", elapsed);
                            ScanStore.writeRecord(reading.directory, reading.record);
                        } catch (Exception failure) { android.util.Log.e("LabelLens", "Details failure record failed", failure); }
                    });
                });
            }
        });
    }

    private void compareProducts() {
        ScanPipeline.Result reading=activeResult;
        if(busy||cloudBusy||reading==null||connectionLoading)return;
        if(token.length()<24){backendSettings();return;}
        int ticket=++geminiGeneration;
        String service=endpoint,secret=token,id=reading.record.optString("scan_id"),ocr=reading.record.optString("primary_ocr_text");
        Bitmap context=detailsContext.isChecked()&&reading.source!=reading.crop?reading.source:null;
        JSONObject stage=reading.record.optJSONObject("paths").optJSONObject(reading.record.optString("primary_path"));
        String image=stage==null?"source.png":stage.optString("image","source.png");
        cloudBusy=true;productComparison.removeAllViews();productComparisonStatus.setText("Checking comparison availability. When configured, this runs two models on the same input.");setBusy(busy);
        cloudWorker.execute(()->{
            try {
                JSONObject response=GeminiGateway.compareDetails(service,secret,id,reading.crop,context,ocr);
                runOnUiThread(()->{
                    if(closed||ticket!=geminiGeneration||activeResult!=reading)return;
                    cloudBusy=false;
                    try { renderProductComparison(response); }
                    catch(Exception error){productComparisonStatus.setText("The comparison response could not be displayed. Try again.");}
                    setBusy(busy);
                    worker.execute(()->{
                        try {
                            reading.record.put("product_comparison",response).put("product_comparison_crop",image)
                                .put("product_comparison_context",context==null?JSONObject.NULL:"source.png").put("product_comparison_ocr_text",ocr);
                            ScanStore.writeRecord(reading.directory,reading.record);
                        } catch(Exception error){android.util.Log.e("LabelLens","Comparison save failed",error);}
                    });
                });
            } catch(Exception failure){runOnUiThread(()->{
                if(closed||ticket!=geminiGeneration||activeResult!=reading)return;
                cloudBusy=false;productComparisonStatus.setText(failure instanceof IOException?failure.getMessage():"Comparison failed. Try again.");setBusy(busy);
            });}
        });
    }

    private void renderProductComparison(JSONObject response) throws Exception {
        if(!response.getBoolean("available")){productComparisonStatus.setText(response.getString("reason"));return;}
        TableLayout table=new TableLayout(this);table.setStretchAllColumns(true);table.setShrinkAllColumns(true);
        addComparisonRow(table,new String[]{"Field","Base","Fine-tuned"});
        String[] keys={"product_name","brand","size","best_by"}, labels={"Product","Brand","Size","Best by"};
        for(int i=0;i<keys.length;i++) {
            String[] row={labels[i],"",""};
            for(int j=0;j<2;j++) {
                JSONObject side=response.getJSONObject(j==0?"base":"tuned");
                row[j+1]="ok".equals(side.getString("status"))?ProductDetails.value(side.getJSONObject("response").getJSONObject("reading"),keys[i]):"Request failed";
            }
            addComparisonRow(table,row);
        }
        productComparison.addView(table);
        for(String variant:new String[]{"base","tuned"}) {
            JSONObject side=response.getJSONObject(variant);TextView provenance=new TextView(this);provenance.setTextIsSelectable(true);
            if("ok".equals(side.getString("status"))) {
                JSONObject result=side.getJSONObject("response"), fields=result.getJSONObject("reading");
                StringBuilder text=new StringBuilder(variant.equals("base")?"Base":"Fine-tuned");
                text.append(" · ").append(result.getString("model")).append(" · ").append(result.optDouble("backend_ms")/1000.0).append(" seconds\n");
                for(int i=0;i<keys.length;i++)text.append(labels[i]).append(" — ").append(ProductDetails.evidence(fields,keys[i])).append("\n");
                text.append(ProductDetails.guidance(fields));provenance.setText(text);
            } else provenance.setText(variant+": "+side.getJSONObject("error").optString("detail"));
            productComparison.addView(provenance);
        }
        JSONObject agreement=response.optJSONObject("agreement");
        productComparisonStatus.setText((agreement==null?"One or both models failed.":agreement.optInt("equal_fields")+" / 4 fields agree (includes shared missing values).")
            +" Same images, OCR and prompt. Agreement is not accuracy; compare with your checked reference.");
    }

    private void addComparisonRow(TableLayout table,String[] values) {
        TableRow row=new TableRow(this);
        for(String value:values){TextView cell=new TextView(this);cell.setText(value);cell.setTextIsSelectable(true);cell.setPadding(8,12,8,12);row.addView(cell,new TableRow.LayoutParams(0,TableRow.LayoutParams.WRAP_CONTENT,1));}
        table.addView(row);
    }

    private void reviewDetails() {
        ScanPipeline.Result reading=activeResult;
        if(reading==null||detailsReading==null||busy||cloudBusy)return;
        try {
            String image=detailsInputCrop,ocr=detailsInputOcr;boolean context=detailsInputContext;
            JSONObject modelDraft=new JSONObject(detailsReading.toString());
            JSONObject previous=reading.record.optJSONObject("product_review");
            if(previous!=null&&(!image.equals(previous.optString("crop"))||!ocr.equals(previous.optString("ocr_text"))
                ||context!=!previous.isNull("context")))previous=null;
            ProductReviewDialog.show(this,detailsReading,previous,ocr,
                group.getText().toString().trim(),reading.record.optString("split","development"),reading.crop,context?reading.source:null,review->{
                    setBusy(true);
                    worker.execute(()->{
                        try {
                            review.put("crop",image).put("context",context?"source.png":JSONObject.NULL).put("ocr_text",ocr).put("prediction",modelDraft);
                            reading.record.put("product_review",review);
                            ScanStore.writeRecord(reading.directory,reading.record);
                            runOnUiThread(()->{if(!closed&&activeResult==reading){setBusy(false);detailsStatus.setText("Checked reference saved separately from Gemini's prediction. You can export this scan now.");}});
                        } catch(Exception failure){runOnUiThread(()->{if(!closed&&activeResult==reading){setBusy(false);detailsStatus.setText("Could not save the checked reference. Please try again.");}});}
                    });
                });
        } catch(Exception error){detailsStatus.setText("Could not open the review. Analyze product details again.");}
    }

    private void backendSettings() {
        if (connectionLoading) { geminiStatus.setText("Loading your saved connection..."); return; }
        LinearLayout fields = new LinearLayout(this); fields.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (24 * getResources().getDisplayMetrics().density); fields.setPadding(pad, 0, pad, 0);
        EditText url = new EditText(this); url.setHint("HTTPS backend URL"); url.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI); url.setText(endpoint); fields.addView(url);
        TextView help = new TextView(this); help.setText("Paste the application token from APP_CONNECTION.txt. This app saves it encrypted on this device."); fields.addView(help);
        EditText secret = new EditText(this); secret.setHint("Application token"); secret.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        secret.setSaveEnabled(false); secret.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO); secret.setText(token); fields.addView(secret);
        TextView modelHelp = new TextView(this); modelHelp.setText("Use Ask base Gemini or Ask fine-tuned Gemini on the main screen to choose the question-answer model."); fields.addView(modelHelp);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("Gemini connection").setView(fields)
            .setNegativeButton("Cancel", null).setNeutralButton("Forget token", null).setPositiveButton("Save", null).create();
        dialog.show();
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String address = url.getText().toString().trim(), entered = secret.getText().toString().trim();
            String selectedVariant = variant; // Retain legacy connection metadata; buttons now choose the model explicitly.
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
        askGemini.setEnabled(!value && !cloudBusy && !connectionLoading && activeResult != null);
        askTuned.setEnabled(!value && !cloudBusy && !connectionLoading && activeResult != null);
        analyzeDetails.setEnabled(!value && !cloudBusy && !connectionLoading && activeResult != null);
        compareProducts.setEnabled(!value && !cloudBusy && !connectionLoading && activeResult != null);
        reviewDetails.setEnabled(!value && !cloudBusy && detailsReading != null && activeResult != null);
        exportReviewed.setEnabled(!value && !cloudBusy && activeResult != null && activeResult.record.optJSONObject("product_review") != null);
        detailsContext.setEnabled(!cloudBusy); speakDetails.setEnabled(speechReady && !detailsSpeech.isEmpty());
        speakGemini.setEnabled(speechReady && !geminiSpeech.isEmpty()); export.setEnabled(!value && !cloudBusy && activeResult != null);
        speakTuned.setEnabled(speechReady && !tunedSpeech.isEmpty());
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
