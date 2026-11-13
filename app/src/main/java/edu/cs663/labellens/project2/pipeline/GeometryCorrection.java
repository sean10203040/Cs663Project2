package edu.cs663.labellens.project2.pipeline;

import android.graphics.Bitmap;
import android.graphics.RectF;
import org.json.JSONArray;
import org.json.JSONObject;
import org.opencv.android.OpenCVLoader;
import org.opencv.android.Utils;
import org.opencv.core.*;
import org.opencv.imgproc.Imgproc;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/** Explicit geometric experiments, never reconstruction of missing label text. */
public final class GeometryCorrection {
    public static final class Result {
        public final Bitmap image;
        public final JSONObject metadata;
        Result(Bitmap image, JSONObject metadata) { this.image = image; this.metadata = metadata; }
    }

    public static Result correct(Bitmap image, RectF nameInCrop, String surface) throws Exception {
        if (!surface.equals("flat") && !surface.equals("cylinder"))
            return fallback(image, surface.equals("deformed") ? "deformation_requires_another_view" : "surface_unspecified");
        if (!OpenCVLoader.initLocal()) return fallback(image, "opencv_unavailable");
        if ((long) image.getWidth() * image.getHeight() > 6_000_000)
            return fallback(image, "correction_resource_limit_original_retained");
        return surface.equals("cylinder") ? cylinder(image) : planar(image, nameInCrop);
    }

    private static Result fallback(Bitmap source, String status) throws Exception {
        return new Result(source, new JSONObject().put("status", status).put("applied", false)
            .put("method", "identity").put("output_to_crop", identity()));
    }

    private static Result planar(Bitmap source, RectF seed) throws Exception {
        Mat rgba = new Mat(), small = new Mat(), gray = new Mat(), edges = new Mat(), hierarchy = new Mat();
        List<MatOfPoint> contours = new ArrayList<>();
        try {
            Utils.bitmapToMat(source, rgba);
            double scale = Math.min(1.0, 1000.0 / Math.max(source.getWidth(), source.getHeight()));
            Imgproc.resize(rgba, small, new Size(Math.round(source.getWidth()*scale), Math.round(source.getHeight()*scale)));
            Imgproc.cvtColor(small, gray, Imgproc.COLOR_RGBA2GRAY);
            Imgproc.GaussianBlur(gray, gray, new Size(5,5), 0);
            Imgproc.Canny(gray, edges, 60, 160);
            Imgproc.findContours(edges, contours, hierarchy, Imgproc.RETR_LIST, Imgproc.CHAIN_APPROX_SIMPLE);
            contours.sort(Comparator.comparingDouble((MatOfPoint c) -> Imgproc.contourArea(c)).reversed());
            for (MatOfPoint contour : contours.subList(0, Math.min(40, contours.size()))) {
                double ratio = Imgproc.contourArea(contour) / (small.rows()*small.cols());
                if (ratio < 0.15 || ratio > 0.97) continue;
                MatOfPoint2f curve = new MatOfPoint2f(contour.toArray()), approx = new MatOfPoint2f();
                MatOfPoint convex = new MatOfPoint();
                try {
                    Imgproc.approxPolyDP(curve, approx, 0.025*Imgproc.arcLength(curve,true), true);
                    Point[] points = approx.toArray();
                    if (points.length != 4) continue;
                    convex.fromArray(points);
                    if (!Imgproc.isContourConvex(convex)) continue;
                    // Candidate must contain all four corners of the detected name.
                    boolean contains = true;
                    for (Point p : new Point[]{new Point(seed.left*scale,seed.top*scale), new Point(seed.right*scale,seed.top*scale),
                            new Point(seed.right*scale,seed.bottom*scale), new Point(seed.left*scale,seed.bottom*scale)})
                        if (Imgproc.pointPolygonTest(approx,p,false) < 0) contains = false;
                    if (!contains) continue;
                    for (Point p : points) { p.x = Math.max(0,Math.min(source.getWidth()-1,p.x/scale)); p.y = Math.max(0,Math.min(source.getHeight()-1,p.y/scale)); }
                    Point[] ordered = order(points);
                    int width = (int)Math.round(Math.max(distance(ordered[0],ordered[1]),distance(ordered[3],ordered[2])));
                    int height = (int)Math.round(Math.max(distance(ordered[0],ordered[3]),distance(ordered[1],ordered[2])));
                    if (width < 40 || height < 20 || (long)width*height > 8_000_000) continue;
                    MatOfPoint2f src = new MatOfPoint2f(ordered), dst = new MatOfPoint2f(new Point(0,0),new Point(width-1,0),new Point(width-1,height-1),new Point(0,height-1));
                    Mat matrix = Imgproc.getPerspectiveTransform(src,dst), inverse = matrix.inv(), warped = new Mat();
                    try {
                        Imgproc.warpPerspective(rgba,warped,matrix,new Size(width,height));
                        Bitmap output = Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);
                        Utils.matToBitmap(warped,output);
                        JSONArray quad = new JSONArray();
                        for (Point p : ordered) quad.put(new JSONArray().put(p.x).put(p.y));
                        double[] values = new double[9]; inverse.get(0,0,values);
                        JSONArray transform = new JSONArray(); for (double v : values) transform.put(v);
                        return new Result(output,new JSONObject().put("status","planar_candidate_requires_review").put("applied",true)
                            .put("method","homography").put("corners_crop_xy",quad).put("output_to_crop",transform));
                    } finally { src.release(); dst.release(); matrix.release(); inverse.release(); warped.release(); }
                } finally { curve.release(); approx.release(); convex.release(); }
            }
            return fallback(source,"no_valid_panel_quad_original_retained");
        } finally {
            rgba.release(); small.release(); gray.release(); edges.release(); hierarchy.release();
            for (MatOfPoint contour : contours) contour.release();
        }
    }

    private static Result cylinder(Bitmap source) throws Exception {
        // Orthographic front-arc hypothesis, not estimated 3-D geometry. Evaluate
        // separately; tilted/irregular cylinders can get worse under this model.
        int sw = source.getWidth(), height = source.getHeight();
        double theta = Math.PI/3, radius = (sw-1)/(2*Math.sin(theta));
        int width = Math.max(2,(int)Math.round(2*radius*theta));
        if ((long)width*height > 8_000_000) return fallback(source,"cylinder_resource_limit_original_retained");
        Mat input = new Mat(), mapX = new Mat(height,width,CvType.CV_32FC1), mapY = new Mat(height,width,CvType.CV_32FC1), output = new Mat();
        try {
            Utils.bitmapToMat(source,input);
            float[] xs = new float[width*height], ys = new float[width*height];
            for (int y=0;y<height;y++) for (int x=0;x<width;x++) {
                xs[y*width+x] = (float)((sw-1)/2.0 + radius*Math.sin(-theta+2*theta*x/(width-1)));
                ys[y*width+x] = y;
            }
            mapX.put(0,0,xs); mapY.put(0,0,ys);
            Imgproc.remap(input,output,mapX,mapY,Imgproc.INTER_LINEAR,Core.BORDER_REPLICATE);
            Bitmap bitmap = Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888); Utils.matToBitmap(output,bitmap);
            return new Result(bitmap,new JSONObject().put("status","experimental_cylinder_front_arc_requires_review")
                .put("method","cylinder").put("applied",true).put("theta_half_radians",theta)
                .put("radius_pixels",radius).put("source_width",sw).put("output_width",width));
        } finally { input.release(); mapX.release(); mapY.release(); output.release(); }
    }

    private static Point[] order(Point[] input) {
        double cx=0,cy=0; for(Point p:input){cx+=p.x/4;cy+=p.y/4;} final double x=cx,y=cy;
        java.util.Arrays.sort(input,Comparator.comparingDouble(p -> Math.atan2(p.y-y,p.x-x)));
        int start=0; for(int i=1;i<4;i++)if(input[i].x+input[i].y<input[start].x+input[start].y)start=i;
        Point[] result=new Point[4];for(int i=0;i<4;i++)result[i]=input[(start+i)%4];return result;
    }
    private static double distance(Point a,Point b){return Math.hypot(a.x-b.x,a.y-b.y);}
    public static JSONArray identity(){return new JSONArray().put(1).put(0).put(0).put(0).put(1).put(0).put(0).put(0).put(1);}
}
