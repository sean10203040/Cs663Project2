package edu.cs663.labellens.project2.pipeline;

import android.graphics.Bitmap;
import android.util.Base64;
import org.json.JSONObject;
import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** App token authenticates to our backend; Google credentials remain server-side. */
public final class GeminiGateway {
    public static JSONObject answer(String endpoint,String token,String variant,String scanId,
                                      Bitmap image,String question) throws Exception {
        if(question.trim().isEmpty())throw new IOException("Enter a question about the label");
        JSONObject body=new JSONObject().put("scan_id",scanId).put("model_variant",variant)
            .put("image_jpeg_base64",encode(image,2048)).put("question",question.trim());
        JSONObject result=post(endpoint,token,"/v1/answer",body);
        if(!scanId.equals(result.optString("scan_id"))||!question.trim().equals(result.optString("question"))
            ||!variant.equals(result.optString("model_variant"))||!result.has("qa"))throw new IOException("Unexpected backend response");
        JSONObject qa=result.getJSONObject("qa");
        if(qa.length()!=2||!(qa.get("answerable") instanceof Boolean)||!(qa.get("answer") instanceof String)
            ||qa.getString("answer").trim().isEmpty())throw new IOException("Invalid answer from the service");
        if(qa.getBoolean("answerable")==qa.getString("answer").trim().equalsIgnoreCase("unanswerable"))throw new IOException("Inconsistent answer from the service");
        return result;
    }

    /** Product extraction is explicitly a base-model baseline until a matching tuned model exists. */
    public static JSONObject productDetails(String endpoint,String token,String scanId,
                                            Bitmap crop,Bitmap context,String ocr) throws Exception {
        JSONObject body=new JSONObject().put("scan_id",scanId).put("model_variant","base")
            .put("crop_jpeg_base64",encode(crop,2048)).put("ocr_text",ocr);
        if(context!=null)body.put("context_jpeg_base64",encode(context,2048));
        JSONObject result=post(endpoint,token,"/v1/parse",body);
        ProductDetails.validateResponse(result,scanId);
        return result;
    }

    private static JSONObject post(String endpoint,String token,String route,JSONObject body) throws Exception {
        return post(endpoint,token,route,body,30000);
    }

    public static JSONObject compareDetails(String endpoint,String token,String scanId,Bitmap crop,Bitmap context,String ocr) throws Exception {
        JSONObject body=new JSONObject().put("scan_id",scanId).put("crop_jpeg_base64",encode(crop,2048)).put("ocr_text",ocr);
        if(context!=null)body.put("context_jpeg_base64",encode(context,2048));
        JSONObject result=post(endpoint,token,"/v1/compare",body,65000);
        if(!scanId.equals(result.optString("scan_id"))||!(result.get("available") instanceof Boolean))throw new IOException("Unexpected comparison response");
        if(result.getBoolean("available"))for(String variant:new String[]{"base","tuned"}) {
            JSONObject side=result.getJSONObject(variant);
            if("ok".equals(side.getString("status")))ProductDetails.validateResponse(side.getJSONObject("response"),scanId,variant);
            else if(!"error".equals(side.getString("status"))||!side.has("error"))throw new IOException("Invalid comparison result");
        }
        return result;
    }

    private static JSONObject post(String endpoint,String token,String route,JSONObject body,int timeout) throws Exception {
        URL url=new URL(endpoint.replaceAll("/+$","")+route);
        if(!url.getProtocol().equals("https"))throw new IOException("Use an HTTPS backend address");
        if(token.length()<24)throw new IOException("Enter the application token from your backend setup");
        HttpURLConnection connection=(HttpURLConnection)url.openConnection();
        try {
            connection.setRequestMethod("POST");connection.setConnectTimeout(15000);connection.setReadTimeout(timeout);
            connection.setInstanceFollowRedirects(false);
            connection.setRequestProperty("Content-Type","application/json");connection.setRequestProperty("Authorization","Bearer "+token);
            connection.setDoOutput(true);
            byte[] payload=body.toString().getBytes(StandardCharsets.UTF_8);connection.setFixedLengthStreamingMode(payload.length);
            try(OutputStream stream=connection.getOutputStream()){stream.write(payload);}
            int code=connection.getResponseCode();
            InputStream input=code>=200&&code<300?connection.getInputStream():connection.getErrorStream();
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            if(input!=null)try(InputStream stream=input){byte[] buffer=new byte[8192];int n;while((n=stream.read(buffer))!=-1){bytes.write(buffer,0,n);if(bytes.size()>200000)throw new IOException("Backend response too large");}}
            if(code<200||code>=300){
                String advice;
                if(code==401)advice="The service token was rejected. Re-enter it in service settings.";
                else if(code==429)advice="Gemini is busy or has reached its quota. Try again later.";
                else if(code==504)advice="Gemini took too long. Try again.";
                else if(code==503)advice="Gemini setup needs attention. Check the backend prompt, model access and endpoint region.";
                else if(code==422)advice="The image or text was rejected. Choose another photo and try again.";
                else if(code==502)advice="Gemini returned an incomplete or unsupported response. Try again with a clearer label.";
                else advice="Gemini could not answer. Try another photo.";
                throw new IOException(advice);
            }
            return new JSONObject(bytes.toString("UTF-8"));
        } finally {connection.disconnect();}
    }
    private static String encode(Bitmap source,int maxSide)throws IOException{
        float scale=Math.min(1f,(float)maxSide/Math.max(source.getWidth(),source.getHeight()));
        Bitmap image=scale<1?Bitmap.createScaledBitmap(source,Math.max(1,Math.round(source.getWidth()*scale)),Math.max(1,Math.round(source.getHeight()*scale)),true):source;
        try{ByteArrayOutputStream bytes=new ByteArrayOutputStream();if(!image.compress(Bitmap.CompressFormat.JPEG,95,bytes))throw new IOException("Image encoding failed");return Base64.encodeToString(bytes.toByteArray(),Base64.NO_WRAP);}
        finally{if(image!=source)image.recycle();}
    }
}
