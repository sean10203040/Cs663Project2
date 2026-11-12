package edu.cs663.labellens.project2.pipeline;

import android.content.Context;
import android.graphics.*;
import android.net.Uri;
import android.os.SystemClock;
import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.*;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.TimeUnit;

/** Serialized worker pipeline. All P1/P2/P3 paths share one orientation/resolution policy. */
public final class ScanPipeline implements AutoCloseable {
    public static final int MASTER_MAX_SIDE=4096;
    public static final class Options {
        public String path="P3",surface="unspecified",group="",condition="clean",split="development";
        public String reference="",endpoint="",token="",variant="tuned",question="What is the name of this product?";
        public boolean compare,contrast,contextCrop=true,cloud,referenceReviewed;
        public long actionStart,captureStart;
    }
    public static final class Result {
        public JSONObject record;public File directory;public Bitmap source,crop;public String display,speech;
        public Map<String,Bitmap> images;
    }
    private final Context context;
    private final TextRecognizer recognizer=TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
    private LabelDetector detector;
    private String modelHash;
    public ScanPipeline(Context context){this.context=context.getApplicationContext();}

    public Result run(Uri uri,Options options,java.util.function.Consumer<String> progress)throws Exception{
        String id="scan_"+System.currentTimeMillis()+"_"+UUID.randomUUID().toString().substring(0,8);
        long started=SystemClock.elapsedRealtime();
        progress.accept("Preparing the photo...");
        Bitmap source=ImageDecoder.decodeBitmap(ImageDecoder.createSource(context.getContentResolver(),uri),(decoder,info,s)->{
            decoder.setAllocator(ImageDecoder.ALLOCATOR_SOFTWARE);decoder.setTargetColorSpace(ColorSpace.get(ColorSpace.Named.SRGB));
            float scale=Math.min(1f,(float)MASTER_MAX_SIDE/Math.max(info.getSize().getWidth(),info.getSize().getHeight()));
            decoder.setTargetSize(Math.max(1,Math.round(info.getSize().getWidth()*scale)),Math.max(1,Math.round(info.getSize().getHeight()*scale)));
        });
        JSONObject record=new JSONObject().put("schema_version",2).put("scan_id",id).put("created_epoch_ms",System.currentTimeMillis())
            .put("product_group",options.group.isEmpty()?JSONObject.NULL:options.group).put("condition",options.condition)
            .put("split",options.split).put("surface",options.surface).put("comparison_run",options.compare)
            .put("reference_text",options.referenceReviewed?options.reference:JSONObject.NULL).put("reference_reviewed",options.referenceReviewed)
            .put("resolution_policy",new JSONObject().put("master_max_side",MASTER_MAX_SIDE).put("width",source.getWidth()).put("height",source.getHeight()))
            .put("processing_version","labellens-android-v2").put("contrast",options.contrast)
            .put("crop_policy",options.contextCrop?"name_box_with_50pct_horizontal_150pct_vertical_context":"name_box_with_8pct_horizontal_12pct_vertical_padding")
            .put("primary_path",options.path).put("capture_to_speech_ms",JSONObject.NULL).put("analysis_to_speech_ms",JSONObject.NULL)
            .put("timing_note","Capture-to-speech includes external-camera composition time. Analysis-to-speech starts at the read action. Comparison runs include all paths.");
        JSONObject paths=new JSONObject();record.put("paths",paths);
        Map<String,Bitmap> images=new LinkedHashMap<>();images.put("source",source);
        Bitmap chosenImage=source;Rect roi=null;JSONObject selectedStage=null;
        if(options.compare||options.path.equals("P1")){
            progress.accept("Reading the full photo...");
            Bitmap input=options.contrast?OcrImagePreparation.higherContrast(source):source;
            if(input!=source)images.put("P1_input",input);
            JSONObject stage=ocr(input).put("image",input==source?"source.png":"P1_input.png")
                .put("geometry",new JSONObject().put("method","identity").put("output_to_crop",GeometryCorrection.identity()))
                .put("crop_origin",new JSONArray().put(0).put(0));paths.put("P1",stage);
            if(options.path.equals("P1")){selectedStage=stage;chosenImage=input;}
        }
        if(options.compare||!options.path.equals("P1")){
            progress.accept("Finding the label region...");long before=SystemClock.elapsedRealtime();
            if(detector==null)detector=new YoloLabelDetector(context.getAssets());
            List<LabelDetector.Detection> detections=detector.detect(source);
            record.put("detection_ms",SystemClock.elapsedRealtime()-before).put("model_sha256",modelHash());
            JSONArray boxes=new JSONArray();for(LabelDetector.Detection d:detections)boxes.put(new JSONObject().put("xyxy",rect(d.bounds)).put("score",d.score));
            record.put("detections",boxes);
            if(detections.isEmpty()){
                for(String path:new String[]{"P2","P3"})if(options.compare||options.path.equals(path)){
                    JSONObject stage=new JSONObject().put("status","no_detection").put("text","").put("words",new JSONArray()).put("ocr_ms",0);
                    paths.put(path,stage);if(options.path.equals(path))selectedStage=stage;
                }
            }else{
                RectF name=detections.get(0).bounds;
                float px=name.width()*(options.contextCrop?0.5f:0.08f),py=name.height()*(options.contextCrop?1.5f:0.12f);
                roi=new Rect(Math.max(0,(int)Math.floor(name.left-px)),Math.max(0,(int)Math.floor(name.top-py)),
                    Math.min(source.getWidth(),(int)Math.ceil(name.right+px)),Math.min(source.getHeight(),(int)Math.ceil(name.bottom+py)));
                record.put("evaluation_region_xyxy",new JSONArray().put(roi.left).put(roi.top).put(roi.right).put(roi.bottom));
                Bitmap crop=Bitmap.createBitmap(source,roi.left,roi.top,roi.width(),roi.height());images.put("crop_original",crop);
                JSONArray origin=new JSONArray().put(roi.left).put(roi.top);
                if(options.compare||options.path.equals("P2")){
                    progress.accept("Reading the detected label...");Bitmap input=options.contrast?OcrImagePreparation.higherContrast(crop):crop;
                    images.put("P2_input",input);
                    JSONObject stage=ocr(input).put("image","P2_input.png").put("crop_origin",origin)
                        .put("geometry",new JSONObject().put("method","identity").put("output_to_crop",GeometryCorrection.identity()));
                    paths.put("P2",stage);if(options.path.equals("P2")){selectedStage=stage;chosenImage=input;}
                }
                if(options.compare||options.path.equals("P3")){
                    progress.accept("Preparing geometric correction...");long geometryStart=SystemClock.elapsedRealtime();
                    RectF seed=new RectF(name);seed.offset(-roi.left,-roi.top);
                    GeometryCorrection.Result correction=GeometryCorrection.correct(crop,seed,options.surface);
                    long geometryMs=SystemClock.elapsedRealtime()-geometryStart;
                    Bitmap input=options.contrast?OcrImagePreparation.higherContrast(correction.image):correction.image;
                    images.put("P3_input",input);progress.accept("Reading the corrected label...");
                    JSONObject stage=ocr(input).put("image","P3_input.png").put("crop_origin",origin)
                        .put("geometry",correction.metadata).put("geometry_ms",geometryMs);
                    paths.put("P3",stage);if(options.path.equals("P3")){selectedStage=stage;chosenImage=input;}
                }
            }
        }
        if(selectedStage==null)throw new IllegalStateException("No primary result");
        String text=selectedStage.optString("text");String guidance=guidance(options.surface);
        String display=text.isEmpty()?guidance:text;String speech=display;
        if(options.cloud){
            progress.accept("Asking about the label...");long cloudStart=SystemClock.elapsedRealtime();
            record.put("gemini_question",options.question).put("gemini_input_policy","single_selected_image_without_ocr_or_extra_context");
            try{
                JSONObject semantic=GeminiGateway.answer(options.endpoint,options.token,options.variant,id,chosenImage,options.question);
                record.put("semantic",semantic).put("gemini_input_image",selectedStage.optString("image","source.png"));
                JSONObject qa=semantic.getJSONObject("qa");
                String response=qa.getBoolean("answerable")?qa.getString("answer"):
                    semantic.optString("guidance","I could not answer from this image. Move closer, reduce glare, and try again.");
                display="Question: "+options.question+"\n\n"+response+"\n\nLocal OCR:\n"+(text.isEmpty()?guidance:text);
                speech=response;
            }catch(Exception error){
                String failure=error instanceof java.net.SocketTimeoutException?"Gemini took too long. Try again.":
                    error instanceof java.net.UnknownHostException?"Cannot connect to Gemini. Check your internet connection.":
                    error instanceof java.io.IOException?error.getMessage():"The Gemini answer could not be read. Try again.";
                if(failure==null)failure="Gemini is unavailable. Try again.";
                record.put("semantic_error",failure);display=display+"\n\n"+failure+" Local OCR is shown.";
                speech=speech+" "+failure;
            }
            record.put("cloud_round_trip_ms",SystemClock.elapsedRealtime()-cloudStart);
        }
        record.put("primary_ocr_text",text).put("analysis_before_save_ms",SystemClock.elapsedRealtime()-options.actionStart)
            .put("worker_ms",SystemClock.elapsedRealtime()-started).put("semantic_requested",options.cloud)
            .put("speech_text",speech).put("dataset_annotation_note","Transcriptions and product groups are evaluator-entered; unreviewed entries are not tuning ground truth.");
        // Defer large PNG compression until the user exports the scan.
        record.put("images_saved",false).put("speech_trigger","user_action");
        File directory=ScanStore.createRecord(context,id,record);
        record.put("analysis_to_result_ms",SystemClock.elapsedRealtime()-options.actionStart);ScanStore.writeRecord(directory,record);
        Result result=new Result();result.record=record;result.directory=directory;result.source=source;result.crop=chosenImage;
        result.display=display;result.speech=speech;result.images=images;return result;
    }

    private JSONObject ocr(Bitmap image)throws Exception{
        long start=SystemClock.elapsedRealtime();Text text=Tasks.await(recognizer.process(InputImage.fromBitmap(image,0)),30,TimeUnit.SECONDS);
        JSONArray words=new JSONArray(),lines=new JSONArray();
        for(Text.TextBlock block:text.getTextBlocks())for(Text.Line line:block.getLines()){
            lines.put(new JSONObject().put("text",line.getText()).put("polygon",polygon(line.getCornerPoints(),line.getBoundingBox())));
            for(Text.Element word:line.getElements())words.put(new JSONObject().put("text",word.getText()).put("polygon",polygon(word.getCornerPoints(),word.getBoundingBox())));
        }
        return new JSONObject().put("status",text.getText().trim().isEmpty()?"no_text":"read").put("text",text.getText().trim())
            .put("words",words).put("lines",lines).put("ocr_ms",SystemClock.elapsedRealtime()-start)
            .put("width",image.getWidth()).put("height",image.getHeight()).put("engine","MLKit-Latin-16.0.1");
    }
    private static JSONArray polygon(Point[] points,Rect bounds)throws Exception{
        JSONArray result=new JSONArray();if(points!=null)for(Point p:points)result.put(new JSONArray().put(p.x).put(p.y));
        else if(bounds!=null)for(int[] p:new int[][]{{bounds.left,bounds.top},{bounds.right,bounds.top},{bounds.right,bounds.bottom},{bounds.left,bounds.bottom}})result.put(new JSONArray().put(p[0]).put(p[1]));
        return result;
    }
    private static JSONArray rect(RectF r)throws org.json.JSONException{return new JSONArray().put(r.left).put(r.top).put(r.right).put(r.bottom);}
    private static String guidance(String surface){return surface.equals("deformed")?"Smooth the bag if possible, uncover the text, and take another photo.":"Move closer, reduce glare, hold steady, or rotate the package slightly and try again.";}
    private String modelHash()throws Exception{
        if(modelHash!=null)return modelHash;MessageDigest digest=MessageDigest.getInstance("SHA-256");
        try(InputStream in=context.getAssets().open("best.tflite")){byte[] buffer=new byte[65536];int n;while((n=in.read(buffer))!=-1)digest.update(buffer,0,n);}
        StringBuilder s=new StringBuilder();for(byte b:digest.digest())s.append(String.format(Locale.US,"%02x",b&255));return modelHash=s.toString();
    }
    @Override public void close(){if(detector!=null)detector.close();recognizer.close();}
}
