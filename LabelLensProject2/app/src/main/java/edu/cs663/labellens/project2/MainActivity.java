package edu.cs663.labellens.project2;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.ImageDecoder;
import android.graphics.Paint;
import android.graphics.RectF;
import android.net.Uri;
import android.os.Bundle;
import android.os.SystemClock;
import android.speech.tts.TextToSpeech;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.ImageView;
import android.widget.ProgressBar;
import android.widget.TextView;
import androidx.activity.ComponentActivity;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.core.content.FileProvider;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;
import java.io.File;
import java.io.IOException;
import java.util.Locale;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import edu.cs663.labellens.project2.pipeline.LabelDetector;
import edu.cs663.labellens.project2.pipeline.YoloLabelDetector;
import edu.cs663.labellens.project2.pipeline.OcrImagePreparation;

public final class MainActivity extends ComponentActivity {
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final TextRecognizer recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
    private ActivityResultLauncher<Uri> takePhoto;
    private ActivityResultLauncher<String> choosePhoto;
    private Uri pendingCapture;
    private Uri selectedUri;
    private Bitmap selectedBitmap;
    private ImageView preview, cropPreview;
    private TextView cropInfo;
    private CheckBox higherContrast;
    private TextView status, result;
    private Button camera, importPhoto, scan, speak, fullPhoto;
    private LabelDetector detector;
    private ProgressBar progress;
    private TextToSpeech tts;
    private boolean speechReady, busy;
    private String recognizedText = "";

    @Override public void onCreate(Bundle savedState) {
        super.onCreate(savedState);
        takePhoto = registerForActivityResult(new ActivityResultContracts.TakePicture(), success -> {
            if (success && pendingCapture != null) loadPhoto(pendingCapture);
            else status.setText("Photo cancelled. You can try again.");
        });
        choosePhoto = registerForActivityResult(new ActivityResultContracts.GetContent(), uri -> {
            if (uri != null) loadPhoto(uri);
        });
        setContentView(R.layout.activity_main);
        View root = findViewById(R.id.root);
        ViewCompat.setOnApplyWindowInsetsListener(root, (v, insets) -> {
            androidx.core.graphics.Insets bars = insets.getInsets(WindowInsetsCompat.Type.systemBars());
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return insets;
        });
        preview = findViewById(R.id.preview);
        cropPreview = findViewById(R.id.crop_preview);
        cropInfo = findViewById(R.id.crop_info);
        higherContrast = findViewById(R.id.higher_contrast);
        if (savedState != null) higherContrast.setChecked(savedState.getBoolean("contrast"));
        status = findViewById(R.id.status);
        result = findViewById(R.id.result);
        camera = findViewById(R.id.camera);
        importPhoto = findViewById(R.id.import_photo);
        scan = findViewById(R.id.scan);
        fullPhoto = findViewById(R.id.full_photo);
        speak = findViewById(R.id.speak);
        progress = findViewById(R.id.progress);
        camera.setOnClickListener(v -> capture());
        importPhoto.setOnClickListener(v -> choosePhoto.launch("image/*"));
        scan.setOnClickListener(v -> readLabel(true));
        fullPhoto.setOnClickListener(v -> readLabel(false));
        speak.setOnClickListener(v -> tts.speak(recognizedText, TextToSpeech.QUEUE_FLUSH, null, "label"));
        tts = new TextToSpeech(this, code -> {
            if (isDestroyed()) return;
            if (code == TextToSpeech.SUCCESS) {
                int language = tts.setLanguage(Locale.US);
                speechReady = language != TextToSpeech.LANG_MISSING_DATA && language != TextToSpeech.LANG_NOT_SUPPORTED;
            }
            speak.setEnabled(speechReady && !busy && !recognizedText.isEmpty());
        });
        if (savedState != null) {
            String pending = savedState.getString("capture");
            if (pending != null) pendingCapture = Uri.parse(pending);
            String selected = savedState.getString("selected");
            if (selected != null) loadPhoto(Uri.parse(selected));
        }
    }

    private void capture() {
        try {
            File directory = new File(getCacheDir(), "captures");
            if (!directory.exists() && !directory.mkdirs()) throw new IOException("Cannot create photo folder");
            File photo = File.createTempFile("label_", ".jpg", directory);
            pendingCapture = FileProvider.getUriForFile(this, getPackageName() + ".files", photo);
            takePhoto.launch(pendingCapture);
        } catch (Exception e) {
            status.setText("Could not open a camera. Try choosing a photo instead.");
        }
    }

    private void loadPhoto(Uri uri) {
        if (busy) return;
        selectedUri = uri;
        recognizedText = "";
        tts.stop();
        clearCrop();
        result.setText("Your label text will appear here.");
        setBusy(true);
        status.setText("Opening photo...");
        worker.execute(() -> {
            try {
                // ImageDecoder honors EXIF orientation. Bound memory use for large phone photos.
                Bitmap bitmap = ImageDecoder.decodeBitmap(ImageDecoder.createSource(getContentResolver(), uri),
                    (decoder, info, source) -> {
                        decoder.setAllocator(ImageDecoder.ALLOCATOR_SOFTWARE);
                        int w = info.getSize().getWidth(), h = info.getSize().getHeight();
                        float scale = Math.min(1f, 2048f / Math.max(w, h));
                        decoder.setTargetSize(Math.max(1, Math.round(w * scale)), Math.max(1, Math.round(h * scale)));
                    });
                runOnUiThread(() -> {
                    if (isDestroyed()) return;
                    selectedBitmap = bitmap;
                    preview.setImageBitmap(bitmap);
                    setBusy(false);
                    status.setText("Photo ready. Tap Read label.");
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    if (isDestroyed()) return;
                    selectedBitmap = null;
                    preview.setImageDrawable(null);
                    setBusy(false);
                    status.setText("Could not open this photo. Please choose another image.");
                });
            }
        });
    }

    private void readLabel(boolean useDetector) {
        if (selectedBitmap == null || busy) return;
        tts.stop();
        recognizedText = "";
        result.setText("Reading...");
        setBusy(true);
        preview.setImageBitmap(selectedBitmap);
        clearCrop();
        status.setText(useDetector ? "Finding the product-name region..." : "Reading the full photo...");
        long start = SystemClock.elapsedRealtime();
        Bitmap source = selectedBitmap;
        Uri photoUri = selectedUri;
        boolean enhance = higherContrast.isChecked();
        if (!useDetector) {
            runOcr(source, "Full-photo OCR", start);
            return;
        }
        worker.execute(() -> {
            try {
                if (detector == null) detector = new YoloLabelDetector(getAssets());
                List<LabelDetector.Detection> detections = detector.detect(source);
                if (detections.isEmpty()) {
                    runOnUiThread(() -> {
                        if (isDestroyed()) return;
                        result.setText("No product-name region found. Move closer or rotate the package, then try again. You can also read the full photo.");
                        status.setText("No detection above the 0.25 score threshold.");
                        setBusy(false);
                    });
                    return;
                }
                LabelDetector.Detection selected = detections.get(0);
                RectF bounds = selected.bounds;
                RectF normalized = new RectF(bounds.left / source.getWidth(), bounds.top / source.getHeight(),
                    bounds.right / source.getWidth(), bounds.bottom / source.getHeight());
                Bitmap originalCrop = OcrImagePreparation.decodeCrop(
                    ImageDecoder.createSource(getContentResolver(), photoUri), normalized);
                Bitmap crop = enhance ? OcrImagePreparation.higherContrast(originalCrop) : originalCrop;
                if (enhance) originalCrop.recycle();
                Bitmap annotated = source.copy(Bitmap.Config.ARGB_8888, true);
                Canvas canvas = new Canvas(annotated);
                Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
                paint.setColor(Color.rgb(20, 145, 80));
                paint.setStyle(Paint.Style.STROKE);
                paint.setStrokeWidth(Math.max(3, source.getWidth() / 200f));
                canvas.drawRect(bounds, paint);
                runOnUiThread(() -> {
                    if (isDestroyed()) return;
                    preview.setImageBitmap(annotated);
                    cropPreview.setImageBitmap(crop);
                    cropPreview.setVisibility(View.VISIBLE);
                    cropInfo.setText(String.format(Locale.US, "Text crop: %d × %d pixels · %s",
                        crop.getWidth(), crop.getHeight(), enhance ? "higher contrast" : "original colors"));
                    cropInfo.setVisibility(View.VISIBLE);
                    status.setText("Product-name region found. Reading the crop...");
                    runOcr(crop, String.format(Locale.US, "Detected-crop OCR, %s (detector score %.2f)",
                        enhance ? "higher contrast" : "original colors", selected.score), start);
                });
            } catch (Exception | LinkageError error) {
                android.util.Log.e("LabelLens", "Detector failed", error);
                runOnUiThread(() -> {
                    if (isDestroyed()) return;
                    result.setText("Could not prepare the detected label. Try choosing the photo again, or use Read full photo.");
                    status.setText("Label reading failed. Details are in Android Studio Logcat.");
                    setBusy(false);
                });
            }
        });
    }

    private void clearCrop() {
        cropPreview.setImageDrawable(null);
        cropPreview.setVisibility(View.GONE);
        cropInfo.setVisibility(View.GONE);
    }

    private void runOcr(Bitmap image, String mode, long start) {
        recognizer.process(InputImage.fromBitmap(image, 0))
            .addOnSuccessListener(text -> {
                if (isDestroyed()) return;
                recognizedText = text.getText().trim();
                result.setText(recognizedText.isEmpty()
                    ? "No readable text found. Move closer, improve lighting, or rotate the package slightly."
                    : recognizedText);
                status.setText(String.format(Locale.US, "%s completed in %.2f seconds.", mode,
                    (SystemClock.elapsedRealtime() - start) / 1000.0));
                setBusy(false);
            })
            .addOnFailureListener(error -> {
                if (isDestroyed()) return;
                result.setText("Reading failed. Please try another photo.");
                status.setText("Could not complete text recognition.");
                setBusy(false);
            });
    }

    private void setBusy(boolean value) {
        busy = value;
        camera.setEnabled(!value);
        importPhoto.setEnabled(!value);
        scan.setEnabled(!value && selectedBitmap != null);
        fullPhoto.setEnabled(!value && selectedBitmap != null);
        higherContrast.setEnabled(!value);
        speak.setEnabled(!value && speechReady && !recognizedText.isEmpty());
        progress.setVisibility(value ? View.VISIBLE : View.GONE);
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        if (pendingCapture != null) state.putString("capture", pendingCapture.toString());
        if (selectedUri != null) state.putString("selected", selectedUri.toString());
        state.putBoolean("contrast", higherContrast.isChecked());
    }

    @Override protected void onDestroy() {
        // Queue close after any in-flight inference; Interpreter is not thread safe.
        worker.execute(() -> { if (detector != null) detector.close(); });
        worker.shutdown();
        recognizer.close();
        if (tts != null) { tts.stop(); tts.shutdown(); }
        super.onDestroy();
    }
}
