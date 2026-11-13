package edu.cs663.labellens.project2.pipeline;

import org.json.JSONObject;
import java.io.IOException;

/** Validate and present partial readings without turning missing values into product facts. */
public final class ProductDetails {
    private ProductDetails() { }

    public static void validateResponse(JSONObject response,String scanId) throws Exception {
        validateResponse(response,scanId,"base");
    }

    public static void validateResponse(JSONObject response,String scanId,String variant) throws Exception {
        if(!scanId.equals(response.optString("scan_id")) || !variant.equals(response.optString("model_variant"))
            || response.optString("model").isEmpty()) throw new IOException("Unexpected product-details response");
        JSONObject reading=response.getJSONObject("reading"), attributes=reading.getJSONObject("key_attributes");
        String[] fields={"product_name","brand","size","best_by"};
        JSONObject evidence=reading.getJSONObject("evidence");
        int found=0;
        for(String field:fields) {
            JSONObject container=(field.equals("size")||field.equals("best_by"))?attributes:reading;
            Object value=container.get(field);
            if(value==JSONObject.NULL) {
                if(evidence.has(field)) throw new IOException("Unsupported field evidence");
                continue;
            }
            if(!(value instanceof String)||((String)value).trim().isEmpty())throw new IOException("Invalid product field");
            JSONObject support=evidence.getJSONObject(field);
            if(!support.getString("source").equals("image")&&!support.getString("source").equals("ocr"))throw new IOException("Invalid evidence source");
            if(support.getString("quote").trim().isEmpty())throw new IOException("Missing supporting text");
            found++;
        }
        String certainty=reading.getString("confidence");
        if(!certainty.equals("high")&&!certainty.equals("medium")&&!certainty.equals("low"))throw new IOException("Invalid certainty flag");
        Object guidance=reading.get("guidance");
        if(guidance!=JSONObject.NULL&&!(guidance instanceof String))throw new IOException("Invalid reading guidance");
        if(found==0&&(!certainty.equals("low")||guidance==JSONObject.NULL||((String)guidance).trim().isEmpty()))
            throw new IOException("Unreadable labels require rescan guidance");
    }

    public static String value(JSONObject reading,String field) throws Exception {
        JSONObject container=(field.equals("size")||field.equals("best_by"))?reading.getJSONObject("key_attributes"):reading;
        return container.isNull(field)?"Not visible":container.getString(field);
    }

    public static String guidance(JSONObject reading) {
        String instructions=reading.isNull("guidance")?"":reading.optString("guidance").trim();
        StringBuilder steps=new StringBuilder();
        if(reading.isNull("product_name")||reading.isNull("brand"))steps.append("Name / brand: photograph the front straight on with all letters in focus. Move the light if glare covers the text.\n\n");
        JSONObject attributes=reading.optJSONObject("key_attributes");
        if(attributes!=null&&attributes.isNull("size"))steps.append("Size: show the printed net weight or volume, often at the bottom of the front or on the back. Include the units.\n\n");
        if(attributes!=null&&attributes.isNull("best_by"))steps.append("Best-by date: check the cap, base, seam or back. Photograph the date and its heading together. A lot code alone is not a best-by date.\n\n");
        if(!instructions.isEmpty())steps.append("Gemini suggests: ").append(instructions);
        return steps.length()==0?"Check these details and their supporting text against the photo.":steps.toString().trim();
    }

    public static String evidence(JSONObject reading,String field) throws Exception {
        JSONObject support=reading.getJSONObject("evidence").optJSONObject(field);
        if(support==null)return "Evidence: no supporting text returned.";
        return ("ocr".equals(support.getString("source"))?"OCR quote: ":"Model-read image text: ")+"\u201c"+support.getString("quote")+"\u201d";
    }

    public static void validateReviewed(JSONObject reading,String ocr) throws Exception {
        validateResponse(new JSONObject().put("scan_id","review").put("model_variant","base").put("model","human-review").put("reading",reading),"review");
        JSONObject evidence=reading.getJSONObject("evidence");
        java.util.Iterator<String> keys=evidence.keys();
        while(keys.hasNext()) {
            JSONObject support=evidence.getJSONObject(keys.next());
            if("ocr".equals(support.getString("source"))&&!normalize(ocr).contains(normalize(support.getString("quote"))))
                throw new IOException("An OCR quote must appear in the OCR text. Use image text for a correction read from the photo.");
        }
    }

    private static String normalize(String text){return text.toLowerCase(java.util.Locale.ROOT).replaceAll("\\s+"," ").trim();}

    public static String speech(JSONObject reading) throws Exception {
        StringBuilder text=new StringBuilder();
        String[] fields={"product_name","brand","size","best_by"};
        String[] labels={"Product","Brand","Size","Best by"};
        for(int i=0;i<fields.length;i++)text.append(labels[i]).append(": ").append(value(reading,fields[i])).append(". ");
        return text.append(guidance(reading)).toString();
    }
}
