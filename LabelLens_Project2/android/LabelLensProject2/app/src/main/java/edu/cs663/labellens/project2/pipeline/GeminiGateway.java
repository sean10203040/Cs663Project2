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
        URL url=new URL(endpoint.replaceAll("/+$","")+"/v1/answer");
        if(!url.getProtocol().equals("https"))throw new IOException("Use an HTTPS backend address");
        if(token.length()<24)throw new IOException("Enter the application token from your backend setup");
        if(question.trim().isEmpty())throw new IOException("Enter a question about the label");
        JSONObject body=new JSONObject().put("scan_id",scanId).put("model_variant",variant)
            .put("image_jpeg_base64",encode(image,2048)).put("question",question.trim());
        HttpURLConnection connection=(HttpURLConnection)url.openConnection();
        try {
            connection.setRequestMethod("POST");connection.setConnectTimeout(15000);connection.setReadTimeout(30000);
            connection.setRequestProperty("Content-Type","application/json");connection.setRequestProperty("Authorization","Bearer "+token);
            connection.setDoOutput(true);
            byte[] payload=body.toString().getBytes(StandardCharsets.UTF_8);connection.setFixedLengthStreamingMode(payload.length);
            try(OutputStream stream=connection.getOutputStream()){stream.write(payload);}
            int code=connection.getResponseCode();
            InputStream input=code>=200&&code<300?connection.getInputStream():connection.getErrorStream();
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            if(input!=null)try(InputStream stream=input){byte[] buffer=new byte[8192];int n;while((n=stream.read(buffer))!=-1){bytes.write(buffer,0,n);if(bytes.size()>100000)throw new IOException("Backend response too large");}}
            if(code<200||code>=300){
                String advice;
                if(code==401)advice="The service token was rejected. Re-enter it in service settings.";
                else if(code==429)advice="Gemini is busy or has reached its quota. Try again later.";
                else if(code==504)advice="Gemini took too long. Try again.";
                else if(code==503)advice="Gemini setup needs attention. Check the backend prompt, model access and endpoint region.";
                else if(code==422)advice="The image or question was rejected. Choose another photo and check the question.";
                else advice="Gemini could not answer. Try another photo.";
                throw new IOException(advice);
            }
            JSONObject result=new JSONObject(bytes.toString("UTF-8"));
            if(!scanId.equals(result.optString("scan_id"))||!question.trim().equals(result.optString("question"))
                ||!variant.equals(result.optString("model_variant"))||!result.has("qa"))throw new IOException("Unexpected backend response");
            JSONObject qa=result.getJSONObject("qa");
            if(qa.length()!=2||!(qa.get("answerable") instanceof Boolean)||!(qa.get("answer") instanceof String)
                ||qa.getString("answer").trim().isEmpty())throw new IOException("Invalid answer from the service");
            if(qa.getBoolean("answerable")==qa.getString("answer").trim().equalsIgnoreCase("unanswerable"))throw new IOException("Inconsistent answer from the service");
            return result;
        } finally {connection.disconnect();}
    }
    private static String encode(Bitmap source,int maxSide)throws IOException{
        float scale=Math.min(1f,(float)maxSide/Math.max(source.getWidth(),source.getHeight()));
        Bitmap image=scale<1?Bitmap.createScaledBitmap(source,Math.max(1,Math.round(source.getWidth()*scale)),Math.max(1,Math.round(source.getHeight()*scale)),true):source;
        try{ByteArrayOutputStream bytes=new ByteArrayOutputStream();if(!image.compress(Bitmap.CompressFormat.JPEG,95,bytes))throw new IOException("Image encoding failed");return Base64.encodeToString(bytes.toByteArray(),Base64.NO_WRAP);}
        finally{if(image!=source)image.recycle();}
    }
}
