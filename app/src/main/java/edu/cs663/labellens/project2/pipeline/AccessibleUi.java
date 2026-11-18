package edu.cs663.labellens.project2.pipeline;

import android.content.Context;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Spinner;
import android.widget.TextView;

/** Native labels and wrapping controls preserve platform screen-reader behavior. */
public final class AccessibleUi {
    private AccessibleUi() { }

    public static int dp(Context context, int value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }

    public static void label(TextView title, View input) {
        if (input.getId() == View.NO_ID) input.setId(View.generateViewId());
        title.setLabelFor(input.getId());
        input.setMinimumHeight(dp(input.getContext(), 48));
    }

    public static void fill(Spinner spinner, String[] values) {
        Context context = spinner.getContext();
        ArrayAdapter<String> adapter = new ArrayAdapter<String>(context, android.R.layout.simple_spinner_item, values) {
            private View readable(View view) {
                TextView text = (TextView) view;
                text.setSingleLine(false);
                text.setMaxLines(Integer.MAX_VALUE);
                text.setEllipsize(null);
                text.setTextSize(18);
                text.setMinHeight(dp(context, 56));
                text.setPadding(dp(context, 12), dp(context, 12), dp(context, 12), dp(context, 12));
                ViewGroup.LayoutParams params = text.getLayoutParams();
                if (params != null) { params.height = ViewGroup.LayoutParams.WRAP_CONTENT; text.setLayoutParams(params); }
                return view;
            }
            @Override public View getView(int position, View convertView, ViewGroup parent) {
                return readable(super.getView(position, convertView, parent));
            }
            @Override public View getDropDownView(int position, View convertView, ViewGroup parent) {
                return readable(super.getDropDownView(position, convertView, parent));
            }
        };
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinner.setAdapter(adapter);
    }
}
