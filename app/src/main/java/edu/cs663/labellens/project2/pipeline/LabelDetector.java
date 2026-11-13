package edu.cs663.labellens.project2.pipeline;

import android.graphics.Bitmap;
import android.graphics.RectF;
import java.util.List;

/** Detection boundary: callers run inference and close on the same background worker. */
public interface LabelDetector extends AutoCloseable {
    /** Return boxes in pixels of the orientation-corrected source bitmap, undoing letterboxing. */
    List<Detection> detect(Bitmap image);
    @Override void close();

    final class Detection {
        public final RectF bounds;
        public final float score;
        public Detection(RectF bounds, float score) {
            this.bounds = new RectF(bounds);
            this.score = score;
        }
    }
}
