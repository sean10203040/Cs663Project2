package edu.cs663.labellens.project2.pipeline;

import static org.junit.Assert.*;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;
import edu.cs663.labellens.project2.pipeline.LabelDetector;
import edu.cs663.labellens.project2.pipeline.YoloLabelDetector;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.concurrent.TimeUnit;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.tensorflow.lite.Interpreter;

/** Native runtime checks, not evidence of accuracy on real product labels. */
@RunWith(AndroidJUnit4.class)
public class ModelPipelineTest {
    private Context context() { return InstrumentationRegistry.getInstrumentation().getTargetContext(); }

    @Test public void modelExecutesAndUsesNormalizedCoordinates() throws Exception {
        byte[] bytes;
        try (InputStream stream = context().getAssets().open("best.tflite")) {
            ByteArrayOutputStream data = new ByteArrayOutputStream();
            byte[] block = new byte[16384];
            int count;
            while ((count = stream.read(block)) != -1) data.write(block, 0, count);
            bytes = data.toByteArray();
        }
        ByteBuffer model = ByteBuffer.allocateDirect(bytes.length).order(ByteOrder.nativeOrder());
        model.put(bytes).rewind();
        try (Interpreter interpreter = new Interpreter(model)) {
            assertArrayEquals(new int[]{1, 3, 320, 320}, interpreter.getInputTensor(0).shape());
            assertArrayEquals(new int[]{1, 5, 2100}, interpreter.getOutputTensor(0).shape());
            ByteBuffer input = ByteBuffer.allocateDirect(3 * 320 * 320 * 4).order(ByteOrder.nativeOrder());
            while (input.hasRemaining()) input.putFloat(0.5f);
            input.rewind();
            float[][][] output = new float[1][5][2100];
            interpreter.run(input, output);
            float largestCenter = 0;
            for (int i = 0; i < 2100; i++) {
                for (int channel = 0; channel < 5; channel++) assertTrue(Float.isFinite(output[0][channel][i]));
                assertTrue(output[0][4][i] >= 0 && output[0][4][i] <= 1);
                largestCenter = Math.max(largestCenter, output[0][0][i]);
            }
            assertTrue("Expected normalized coordinates, got max center " + largestCenter,
                largestCenter > 0.5f && largestCenter < 2);
        }
    }

    @Test public void cropsUndoPaddingAndSuppressDuplicateBoxes() {
        float[][] prediction = new float[5][2100];
        // On an 800x400 source, letterboxing adds 80px above/below the 320x160 image.
        // This normalized box covers the center 400x200 source region.
        for (int i = 0; i < 2; i++) {
            prediction[0][i] = 0.5f;
            prediction[1][i] = 0.5f;
            prediction[2][i] = 0.5f;
            prediction[3][i] = 0.25f;
            prediction[4][i] = 0.9f - i * 0.1f;
        }
        java.util.List<LabelDetector.Detection> boxes = YoloLabelDetector.decode(prediction, 800, 400, 320, 160, 0, 80);
        assertEquals(1, boxes.size());
        assertEquals(200f, boxes.get(0).bounds.left, 0.01f);
        assertEquals(100f, boxes.get(0).bounds.top, 0.01f);
        assertEquals(600f, boxes.get(0).bounds.right, 0.01f);
        assertEquals(300f, boxes.get(0).bounds.bottom, 0.01f);
        // A box entirely in padding must not become a valid OCR crop.
        prediction[1][0] = 0.05f;
        prediction[3][0] = 0.05f;
        prediction[4][1] = 0;
        assertTrue(YoloLabelDetector.decode(prediction, 800, 400, 320, 160, 0, 80).isEmpty());
        // Portrait images use horizontal padding instead.
        prediction[0][0] = prediction[1][0] = 0.5f;
        prediction[2][0] = 0.25f;
        prediction[3][0] = 0.5f;
        boxes = YoloLabelDetector.decode(prediction, 400, 800, 160, 320, 80, 0);
        assertEquals(100f, boxes.get(0).bounds.left, 0.01f);
        assertEquals(200f, boxes.get(0).bounds.top, 0.01f);
        assertEquals(300f, boxes.get(0).bounds.right, 0.01f);
        assertEquals(600f, boxes.get(0).bounds.bottom, 0.01f);
    }

    @Test public void adapterAcceptsPortraitAndLandscapeImages() throws Exception {
        try (YoloLabelDetector detector = new YoloLabelDetector(context().getAssets())) {
            for (int[] size : new int[][]{{800, 400}, {400, 800}}) {
                Bitmap bitmap = Bitmap.createBitmap(size[0], size[1], Bitmap.Config.ARGB_8888);
                bitmap.eraseColor(Color.LTGRAY);
                for (LabelDetector.Detection detection : detector.detect(bitmap)) {
                    assertTrue(detection.bounds.left >= 0 && detection.bounds.top >= 0);
                    assertTrue(detection.bounds.right <= size[0] && detection.bounds.bottom <= size[1]);
                    assertTrue(detection.bounds.width() >= 2 && detection.bounds.height() >= 2);
                }
                bitmap.recycle();
            }
        }
    }

    @Test public void bundledOcrReadsGeneratedText() throws Exception {
        Bitmap bitmap = Bitmap.createBitmap(1200, 240, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        canvas.drawColor(Color.WHITE);
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setColor(Color.BLACK);
        paint.setTextSize(80);
        canvas.drawText("LABEL LENS TEST 123", 40, 140, paint);
        TextRecognizer recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
        try {
            String text = Tasks.await(recognizer.process(InputImage.fromBitmap(bitmap, 0)), 30, TimeUnit.SECONDS).getText();
            assertTrue(text, text.contains("LABEL"));
            assertTrue(text, text.contains("123"));
        } finally {
            recognizer.close();
            bitmap.recycle();
        }
    }

    @Test public void ocrCropKeepsOriginalDetailAndClampsMargins() throws Exception {
        Bitmap photo = Bitmap.createBitmap(4000, 1000, Bitmap.Config.ARGB_8888);
        photo.eraseColor(Color.WHITE);
        Paint paint = new Paint();
        paint.setColor(Color.BLACK);
        new Canvas(photo).drawRect(1000, 250, 3000, 750, paint);
        java.io.File file = java.io.File.createTempFile("ocr_crop_", ".png", context().getCacheDir());
        try {
            try (java.io.FileOutputStream stream = new java.io.FileOutputStream(file)) {
                photo.compress(Bitmap.CompressFormat.PNG, 100, stream);
            }
            Bitmap crop = OcrImagePreparation.decodeCrop(android.graphics.ImageDecoder.createSource(file),
                new android.graphics.RectF(0.25f, 0.25f, 0.75f, 0.75f));
            // A 2048px preview would have discarded nearly half this detail.
            assertTrue(crop.getWidth() >= 2319 && crop.getWidth() <= 2321);
            assertTrue(crop.getHeight() >= 619 && crop.getHeight() <= 621);
            assertEquals(Color.BLACK, crop.getPixel(crop.getWidth() / 2, crop.getHeight() / 2));
            assertEquals(Color.WHITE, crop.getPixel(0, 0));
            crop.recycle();
            Bitmap edge = OcrImagePreparation.decodeCrop(android.graphics.ImageDecoder.createSource(file),
                new android.graphics.RectF(0, 0, 1, 1));
            assertEquals(4000, edge.getWidth());
            assertEquals(1000, edge.getHeight());
            edge.recycle();
        } finally { photo.recycle(); file.delete(); }
    }

    @Test public void originalAndContrastPreserveThinLetterOnGeneratedLabel() throws Exception {
        Bitmap original = Bitmap.createBitmap(1200, 220, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(original);
        canvas.drawColor(Color.rgb(10, 60, 170));
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setColor(Color.WHITE);
        paint.setTextSize(80);
        canvas.drawText("POCARI SWEAT", 40, 140, paint);
        Bitmap enhanced = OcrImagePreparation.higherContrast(original);
        TextRecognizer recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
        try {
            for (Bitmap image : new Bitmap[]{original, enhanced}) {
                String text = Tasks.await(recognizer.process(InputImage.fromBitmap(image, 0)), 30, TimeUnit.SECONDS).getText();
                assertEquals("POCARISWEAT", text.replaceAll("\\s+", ""));
            }
        } finally { recognizer.close(); original.recycle(); enhanced.recycle(); }
    }
}
