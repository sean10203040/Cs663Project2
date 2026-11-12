package edu.cs663.labellens.project2.pipeline;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.ColorMatrix;
import android.graphics.ColorMatrixColorFilter;
import android.graphics.ColorSpace;
import android.graphics.ImageDecoder;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.RectF;
import java.io.IOException;

/** Prepare OCR from the original photo, independently of the smaller detector preview. */
public final class OcrImagePreparation {
    private OcrImagePreparation() { }

    public static Bitmap decodeCrop(ImageDecoder.Source source, RectF normalizedBox) throws IOException {
        RectF box = new RectF(normalizedBox);
        // Context protects strokes and ascenders near detector edges.
        box.inset(-box.width() * 0.08f, -box.height() * 0.12f);
        return ImageDecoder.decodeBitmap(source, (decoder, info, ignored) -> {
            int originalWidth = info.getSize().getWidth(), originalHeight = info.getSize().getHeight();
            // Bound decoding cost for very large imports. Never upscale missing source detail.
            float scale = Math.min(1f, 4096f / Math.max(originalWidth, originalHeight));
            int width = Math.max(1, Math.round(originalWidth * scale));
            int height = Math.max(1, Math.round(originalHeight * scale));
            decoder.setAllocator(ImageDecoder.ALLOCATOR_SOFTWARE);
            decoder.setTargetColorSpace(ColorSpace.get(ColorSpace.Named.SRGB));
            decoder.setTargetSize(width, height);
            int left = Math.max(0, Math.min(width - 1, (int) Math.floor(box.left * width)));
            int top = Math.max(0, Math.min(height - 1, (int) Math.floor(box.top * height)));
            int right = Math.max(left + 1, Math.min(width, (int) Math.ceil(box.right * width)));
            int bottom = Math.max(top + 1, Math.min(height, (int) Math.ceil(box.bottom * height)));
            decoder.setCrop(new Rect(left, top, right, bottom));
        });
    }

    /** Optional alternative; avoid binary thresholding that can erase thin letters. */
    public static Bitmap higherContrast(Bitmap source) {
        Bitmap result = Bitmap.createBitmap(source.getWidth(), source.getHeight(), Bitmap.Config.ARGB_8888);
        ColorMatrix gray = new ColorMatrix();
        gray.setSaturation(0);
        float gain = 1.15f, offset = 128f * (1f - gain);
        ColorMatrix contrast = new ColorMatrix(new float[]{
            gain, 0, 0, 0, offset,
            0, gain, 0, 0, offset,
            0, 0, gain, 0, offset,
            0, 0, 0, 1, 0});
        contrast.postConcat(gray);
        Paint paint = new Paint();
        paint.setColorFilter(new ColorMatrixColorFilter(contrast));
        new Canvas(result).drawBitmap(source, 0, 0, paint);
        return result;
    }
}
