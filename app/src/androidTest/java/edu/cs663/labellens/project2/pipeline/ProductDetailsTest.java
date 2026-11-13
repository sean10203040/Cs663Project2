package edu.cs663.labellens.project2.pipeline;

import static org.junit.Assert.*;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class ProductDetailsTest {
    private JSONObject fixture() throws Exception {
        return new JSONObject("{\"scan_id\":\"fixture\",\"model_variant\":\"base\",\"model\":\"gemini-base\",\"reading\":{"
            + "\"product_name\":\"POCARI SWEAT\",\"brand\":null,\"key_attributes\":{\"size\":\"500 ml\",\"best_by\":null},"
            + "\"confidence\":\"medium\",\"guidance\":\"Show the printed date.\",\"evidence\":{"
            + "\"product_name\":{\"source\":\"ocr\",\"quote\":\"POCARI SWEAT\"},"
            + "\"size\":{\"source\":\"image\",\"quote\":\"500 ml\"}}}}");
    }

    @Test public void missingFieldsAreNotInventedInDisplayOrSpeech() throws Exception {
        JSONObject response = fixture(); ProductDetails.validateResponse(response, "fixture");
        JSONObject reading = response.getJSONObject("reading");
        assertEquals("Not visible", ProductDetails.value(reading, "best_by"));
        assertEquals("Not visible", ProductDetails.value(reading, "brand"));
        assertTrue(ProductDetails.speech(reading).contains("Best by: Not visible"));
        assertTrue(ProductDetails.speech(reading).contains("Show the printed date."));
    }

    @Test public void wrongTaskOrMissingEvidenceIsRejected() throws Exception {
        JSONObject response = fixture(); response.put("model_variant", "tuned");
        try { ProductDetails.validateResponse(response, "fixture"); fail(); } catch (java.io.IOException expected) { }
        response = fixture(); response.getJSONObject("reading").getJSONObject("evidence").remove("product_name");
        try { ProductDetails.validateResponse(response, "fixture"); fail(); } catch (org.json.JSONException expected) { }
        response = fixture();
        try { ProductDetails.validateResponse(response, "other-scan"); fail(); } catch (java.io.IOException expected) { }
    }

    @Test public void evidenceAndGuidanceIdentifyMissingFields() throws Exception {
        JSONObject reading=fixture().getJSONObject("reading");
        assertTrue(ProductDetails.evidence(reading,"product_name").startsWith("OCR quote:"));
        assertTrue(ProductDetails.evidence(reading,"size").startsWith("Model-read image text:"));
        assertTrue(ProductDetails.guidance(reading).contains("cap, base, seam"));
        assertFalse(ProductDetails.guidance(reading).contains("Size: show"));
    }

    @Test public void reviewRejectsUnsupportedOcrButAllowsCheckedImageText() throws Exception {
        JSONObject reading=fixture().getJSONObject("reading");
        try {ProductDetails.validateReviewed(reading,"PO CAR SWEAT");fail();}catch(java.io.IOException expected){}
        reading.getJSONObject("evidence").getJSONObject("product_name").put("source","image");
        ProductDetails.validateReviewed(reading,"PO CAR SWEAT");
    }
}
