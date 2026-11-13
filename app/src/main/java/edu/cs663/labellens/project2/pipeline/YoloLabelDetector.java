package edu.cs663.labellens.project2.pipeline;

import android.content.res.AssetManager;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.RectF;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import org.tensorflow.lite.DataType;
import org.tensorflow.lite.Interpreter;

/** Adapter for the inspected Ultralytics 8.4.171 FP32 LiteRT export in assets. */
public final class YoloLabelDetector implements LabelDetector {
    private static final int SIZE = 320;
    private static final int CANDIDATES = 2100;
    private static final float SCORE_THRESHOLD = 0.25f;
    private static final float IOU_THRESHOLD = 0.45f;
    private final Interpreter interpreter;
    // Keep the direct model buffer alive for the interpreter's lifetime.
    private final ByteBuffer modelBuffer;
    private final ByteBuffer input = ByteBuffer.allocateDirect(3 * SIZE * SIZE * 4).order(ByteOrder.nativeOrder());
    private final float[][][] output = new float[1][5][CANDIDATES];

    public YoloLabelDetector(AssetManager assets) throws IOException {
        byte[] bytes;
        try (InputStream stream = assets.open("best.tflite")) {
            java.io.ByteArrayOutputStream data = new java.io.ByteArrayOutputStream();
            byte[] chunk = new byte[16384];
            int count;
            while ((count = stream.read(chunk)) != -1) data.write(chunk, 0, count);
            bytes = data.toByteArray();
        }
        modelBuffer = ByteBuffer.allocateDirect(bytes.length).order(ByteOrder.nativeOrder());
        modelBuffer.put(bytes).rewind();
        Interpreter candidate = new Interpreter(modelBuffer, new Interpreter.Options().setNumThreads(2));
        if (candidate.getInputTensorCount() != 1 || candidate.getOutputTensorCount() != 1
            || candidate.getInputTensor(0).dataType() != DataType.FLOAT32
            || candidate.getOutputTensor(0).dataType() != DataType.FLOAT32
            || !Arrays.equals(candidate.getInputTensor(0).shape(), new int[]{1, 3, SIZE, SIZE})
            || !Arrays.equals(candidate.getOutputTensor(0).shape(), new int[]{1, 5, CANDIDATES})) {
            candidate.close();
            throw new IllegalArgumentException("Model format changed. Expected FP32 [1,3,320,320] -> [1,5,2100].");
        }
        interpreter = candidate;
    }

    @Override public List<Detection> detect(Bitmap image) {
        float gain = Math.min((float) SIZE / image.getWidth(), (float) SIZE / image.getHeight());
        int width = Math.round(image.getWidth() * gain);
        int height = Math.round(image.getHeight() * gain);
        int left = (SIZE - width) / 2, top = (SIZE - height) / 2;
        Bitmap letterbox = Bitmap.createBitmap(SIZE, SIZE, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(letterbox);
        canvas.drawColor(Color.rgb(114, 114, 114));
        canvas.drawBitmap(image, null, new Rect(left, top, left + width, top + height),
            new Paint(Paint.FILTER_BITMAP_FLAG));
        int[] pixels = new int[SIZE * SIZE];
        letterbox.getPixels(pixels, 0, SIZE, 0, 0, SIZE, SIZE);
        letterbox.recycle();
        input.rewind();
        // This export is NCHW: all R pixels, then all G pixels, then all B pixels.
        for (int shift : new int[]{16, 8, 0}) {
            for (int pixel : pixels) input.putFloat(((pixel >> shift) & 255) / 255f);
        }
        input.rewind();
        interpreter.run(input, output);
        return decode(output[0], image.getWidth(), image.getHeight(), width, height, left, top);
    }

    static List<Detection> decode(float[][] prediction, int sourceWidth, int sourceHeight,
                                  int width, int height, int left, int top) {
        List<Detection> boxes = new ArrayList<>();
        for (int i = 0; i < CANDIDATES; i++) {
            float score = prediction[4][i];
            if (!Float.isFinite(score) || score < SCORE_THRESHOLD || score > 1) continue;
            // Device inference confirmed normalized xywh. Convert to letterboxed input pixels.
            float cx = prediction[0][i] * SIZE, cy = prediction[1][i] * SIZE;
            float bw = prediction[2][i] * SIZE, bh = prediction[3][i] * SIZE;
            if (!Float.isFinite(cx) || !Float.isFinite(cy) || !Float.isFinite(bw)
                || !Float.isFinite(bh) || bw <= 0 || bh <= 0) continue;
            // Undo the exact integer resize and padding used above.
            float sx = (float) sourceWidth / width, sy = (float) sourceHeight / height;
            RectF bounds = new RectF(
                clamp((cx - bw / 2 - left) * sx, sourceWidth),
                clamp((cy - bh / 2 - top) * sy, sourceHeight),
                clamp((cx + bw / 2 - left) * sx, sourceWidth),
                clamp((cy + bh / 2 - top) * sy, sourceHeight));
            if (bounds.width() >= 2 && bounds.height() >= 2) boxes.add(new Detection(bounds, score));
        }
        boxes.sort(Comparator.comparingDouble((Detection box) -> box.score).reversed());
        List<Detection> kept = new ArrayList<>();
        for (Detection box : boxes) {
            boolean overlaps = false;
            for (Detection other : kept) {
                if (iou(box.bounds, other.bounds) > IOU_THRESHOLD) { overlaps = true; break; }
            }
            if (!overlaps) kept.add(box);
            if (kept.size() == 20) break;
        }
        return kept;
    }

    private static float clamp(float value, float max) { return Math.max(0, Math.min(max, value)); }

    private static float iou(RectF a, RectF b) {
        float overlap = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left))
            * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
        return overlap / (a.width() * a.height() + b.width() * b.height() - overlap);
    }

    @Override public void close() { interpreter.close(); }
}
