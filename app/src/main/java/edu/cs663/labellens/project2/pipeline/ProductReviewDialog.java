package edu.cs663.labellens.project2.pipeline;

import android.app.Activity;
import android.app.AlertDialog;
import android.text.InputType;
import android.widget.*;
import org.json.JSONObject;

/** Human references are deliberately separate from the immutable model prediction. */
public final class ProductReviewDialog {
    public interface Saved { void save(JSONObject review); }
    private static final String[] KEYS={"product_name","brand","size","best_by"};
    private static final String[] LABELS={"Product name","Brand","Size / net weight","Best-by date"};

    private static EditText edit(Activity activity,LinearLayout layout,String label,String value,int limit) {
        TextView title=new TextView(activity);title.setText(label);layout.addView(title);
        EditText input=new EditText(activity);input.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        input.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(limit)});
        input.setText(value);input.setContentDescription(label);layout.addView(input);return input;
    }
    private static Spinner choices(Activity activity,LinearLayout layout,String[] values) {
        Spinner spinner=new Spinner(activity);ArrayAdapter<String> adapter=new ArrayAdapter<>(activity,android.R.layout.simple_spinner_item,values);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);spinner.setAdapter(adapter);layout.addView(spinner);return spinner;
    }
    public static void show(Activity activity,JSONObject prediction,JSONObject previous,String ocr,String group,String split,
                            android.graphics.Bitmap crop,android.graphics.Bitmap context,Saved callback) throws Exception {
        JSONObject draft=previous==null?prediction:previous.getJSONObject("target");
        LinearLayout fields=new LinearLayout(activity);fields.setOrientation(LinearLayout.VERTICAL);
        int pad=(int)(20*activity.getResources().getDisplayMetrics().density);fields.setPadding(pad,pad,pad,pad);
        TextView help=new TextView(activity);help.setText("Check the photo for every field and supporting quote. These are model drafts until you confirm them. Leave an absent or unreadable value blank. Use image evidence when correcting OCR mistakes.");fields.addView(help);
        for(android.graphics.Bitmap image:new android.graphics.Bitmap[]{crop,context})if(image!=null){
            ImageView preview=new ImageView(activity);preview.setImageBitmap(image);preview.setAdjustViewBounds(true);
            preview.setContentDescription(image==crop?"Product image supplied to Gemini":"Context photo supplied to Gemini");fields.addView(preview);
        }
        TextView rawOcr=new TextView(activity);rawOcr.setText("OCR supplied to Gemini:\n"+ocr);rawOcr.setTextIsSelectable(true);fields.addView(rawOcr);
        EditText[] values=new EditText[4],quotes=new EditText[4];Spinner[] sources=new Spinner[4];
        for(int i=0;i<4;i++) {
            values[i]=edit(activity,fields,LABELS[i]+" (blank = not visible)","Not visible".equals(ProductDetails.value(draft,KEYS[i]))?"":ProductDetails.value(draft,KEYS[i]),500);
            JSONObject support=draft.getJSONObject("evidence").optJSONObject(KEYS[i]);
            quotes[i]=edit(activity,fields,LABELS[i]+" supporting text",support==null?"":support.optString("quote"),500);
            sources[i]=choices(activity,fields,new String[]{"Read from photo","Exact OCR quote"});
            sources[i].setContentDescription(LABELS[i]+" evidence source");
            sources[i].setSelection(support!=null&&"ocr".equals(support.optString("source"))?1:0);
        }
        EditText guidance=edit(activity,fields,"Guidance for missing details",draft.isNull("guidance")?"":draft.optString("guidance"),1000);
        TextView certaintyLabel=new TextView(activity);certaintyLabel.setText("Reading certainty (subjective, not an accuracy score)");fields.addView(certaintyLabel);
        Spinner certainty=choices(activity,fields,new String[]{"Low","Medium","High"});
        certainty.setSelection("high".equals(draft.optString("confidence"))?2:"medium".equals(draft.optString("confidence"))?1:0);
        EditText productGroup=edit(activity,fields,"Product group ID (same product across all photos)",previous==null?group:previous.optString("product_group",group),100);
        TextView splitLabel=new TextView(activity);splitLabel.setText("Dataset split");fields.addView(splitLabel);
        Spinner dataset=choices(activity,fields,new String[]{"Development / not assigned","Training","Validation","Final test"});
        String chosen=previous==null?split:previous.optString("split",split);
        dataset.setSelection("train".equals(chosen)?1:"validation".equals(chosen)?2:"test".equals(chosen)?3:0);
        CheckBox checked=new CheckBox(activity);checked.setText("I checked every value and supporting quote against this photo");fields.addView(checked);
        TextView error=new TextView(activity);error.setTextColor(0xffa02020);fields.addView(error);
        ScrollView scroll=new ScrollView(activity);scroll.addView(fields);
        AlertDialog dialog=new AlertDialog.Builder(activity).setTitle("Review product details").setView(scroll)
            .setNegativeButton("Cancel",null).setPositiveButton("Save checked reference",null).create();dialog.show();
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{
            try {
                if(!checked.isChecked())throw new IllegalArgumentException("Confirm that you checked the photo first.");
                String id=productGroup.getText().toString().trim();
                if(id.isEmpty())throw new IllegalArgumentException("Enter a product group ID to keep related photos in the same split.");
                JSONObject target=new JSONObject(),attributes=new JSONObject(),evidence=new JSONObject();int found=0;
                for(int i=0;i<4;i++) {
                    String value=values[i].getText().toString().trim();
                    (i<2?target:attributes).put(KEYS[i],value.isEmpty()?JSONObject.NULL:value);
                    if(!value.isEmpty()) {
                        found++;evidence.put(KEYS[i],new JSONObject().put("quote",quotes[i].getText().toString().trim()).put("source",sources[i].getSelectedItemPosition()==1?"ocr":"image"));
                    }
                }
                String instruction=guidance.getText().toString().trim();
                target.put("key_attributes",attributes).put("evidence",evidence)
                    .put("confidence",found==0?"low":new String[]{"low","medium","high"}[certainty.getSelectedItemPosition()])
                    .put("guidance",instruction.isEmpty()?JSONObject.NULL:instruction);
                ProductDetails.validateReviewed(target,ocr);
                String[] splits={"development","train","validation","test"};
                callback.save(new JSONObject().put("reviewed",true).put("target",target).put("product_group",id)
                    .put("split",splits[dataset.getSelectedItemPosition()]).put("reviewed_epoch_ms",System.currentTimeMillis())
                    .put("certainty_origin","human-reviewed subjective flag; not measured accuracy or calibration"));
                dialog.dismiss();
            } catch(Exception failure){error.setText(failure.getMessage());}
        });
    }
}
