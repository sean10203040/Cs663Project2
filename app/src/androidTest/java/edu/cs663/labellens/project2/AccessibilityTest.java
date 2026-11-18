package edu.cs663.labellens.project2;

import static org.junit.Assert.*;
import android.app.Instrumentation;
import android.os.SystemClock;
import android.view.View;
import android.view.ViewGroup;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.*;
import androidx.core.view.ViewCompat;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import edu.cs663.labellens.project2.pipeline.SpeechText;
import java.util.ArrayList;
import java.util.List;
import org.junit.Test;
import org.junit.runner.RunWith;

/** Offline checks: no image upload, Gemini request, or account configuration. */
@RunWith(AndroidJUnit4.class)
public class AccessibilityTest {
    private final Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();

    private List<View> descendants(View root) {
        List<View> result = new ArrayList<>(); result.add(root);
        if (root instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) root;
            for (int i=0;i<group.getChildCount();i++) result.addAll(descendants(group.getChildAt(i)));
        }
        return result;
    }

    @Test public void mainFormControlsHavePersistentLabelsAndTouchTargets() {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> {
                List<View> all = descendants(activity.findViewById(R.id.page_content));
                float density = activity.getResources().getDisplayMetrics().density;
                for (View view : all) {
                    if (view instanceof EditText || view instanceof Spinner) {
                        assertTrue("Missing persistent label for view " + view.getId(), all.stream().anyMatch(v -> v.getLabelFor()==view.getId()));
                    }
                    if (view instanceof Button || view instanceof Spinner) {
                        assertTrue("Touch target too short for view " + view.getId(), view.getMinimumHeight() >= 48*density-1);
                    }
                }
                assertEquals("Base Gemini product details", activity.findViewById(R.id.details_card).getAccessibilityPaneTitle());
                assertEquals("Fine-tuned Gemini product details", activity.findViewById(R.id.tuned_details_card).getAccessibilityPaneTitle());
                assertFalse(activity.findViewById(R.id.stop_speech).isEnabled());
            });
        }
    }

    @Test public void expandablePanelsExposeTheirStateAndDropdownDoesNotClip() {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> {
                View button = activity.findViewById(R.id.toggle_options);
                assertEquals("Collapsed", ViewCompat.getStateDescription(button));
                button.performClick();
                assertEquals("Expanded", ViewCompat.getStateDescription(button));
                assertEquals(View.VISIBLE, activity.findViewById(R.id.scan_options).getVisibility());
                ((Spinner) activity.findViewById(R.id.surface)).setSelection(2);
            });
            instrumentation.waitForIdleSync();
            scenario.onActivity(activity -> {
                Spinner spinner = activity.findViewById(R.id.surface);
                TextView text = (TextView) spinner.getSelectedView();
                assertNotNull(text.getLayout());
                assertNull(text.getEllipsize());
                assertTrue(text.getMaxLines()>1);
                assertTrue("Enlarged dropdown text clipped", text.getHeight() >= text.getLayout().getHeight()+text.getCompoundPaddingTop()+text.getCompoundPaddingBottom());
                activity.findViewById(R.id.toggle_options).performClick();
                assertEquals(View.GONE, activity.findViewById(R.id.scan_options).getVisibility());
            });
        }
    }

    private List<AccessibilityNodeInfo> editableNodes(AccessibilityNodeInfo node) {
        List<AccessibilityNodeInfo> result = new ArrayList<>();
        if (node == null) return result;
        if (node.isEditable()) result.add(node);
        for (int i=0;i<node.getChildCount();i++) result.addAll(editableNodes(node.getChild(i)));
        return result;
    }

    @Test public void connectionFieldsStayLabeledAndTokenStaysPasswordProtected() {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            boolean[] ready={false}; long deadline=SystemClock.elapsedRealtime()+15000;
            while(!ready[0] && SystemClock.elapsedRealtime()<deadline) {
                scenario.onActivity(activity -> ready[0]=activity.findViewById(R.id.backend_settings).isEnabled());
                if(!ready[0]) SystemClock.sleep(50);
            }
            assertTrue("Connection settings did not become available",ready[0]);
            scenario.onActivity(activity -> activity.findViewById(R.id.backend_settings).performClick());
            instrumentation.waitForIdleSync();
            List<AccessibilityNodeInfo> inputs=editableNodes(instrumentation.getUiAutomation().getRootInActiveWindow());
            assertEquals(2,inputs.size());
            boolean password=false;
            for(AccessibilityNodeInfo input:inputs) {
                assertNotNull("Input loses its label when populated",input.getLabeledBy());
                password |= input.isPassword();
            }
            assertTrue("App token must remain a password field",password);
        }
    }

    @Test public void longSpeechPreservesWordsAndSurrogatePairsWithinAndroidLimit() {
        String original=("POCARI SWEAT 500 ml. ").repeat(800);
        List<String> chunks=SpeechText.chunks(original,4000);
        assertTrue(chunks.size()>1);
        assertEquals(original.trim().replaceAll("\\s+"," "),String.join(" ",chunks));
        for(String chunk:chunks)assertTrue(chunk.length()<=4000);
        for(String chunk:SpeechText.chunks("😀😀😀",3)) {
            assertEquals(2,chunk.length());
            assertTrue(Character.isSurrogatePair(chunk.charAt(0),chunk.charAt(1)));
        }
    }
}
