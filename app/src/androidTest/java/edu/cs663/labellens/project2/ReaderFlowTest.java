package edu.cs663.labellens.project2;

import static org.junit.Assert.*;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.net.Uri;
import android.os.SystemClock;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.core.content.FileProvider;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.*;
import java.util.*;
import java.util.function.Predicate;
import java.util.zip.ZipFile;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class ReaderFlowTest {
    private final Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
    private final Context context = instrumentation.getTargetContext();

    private void await(ActivityScenario<MainActivity> scenario, Predicate<MainActivity> ready) {
        long deadline = SystemClock.elapsedRealtime() + 30000;
        boolean[] done = {false};
        while (SystemClock.elapsedRealtime() < deadline) {
            scenario.onActivity(activity -> done[0] = ready.test(activity));
            if (done[0]) return;
            SystemClock.sleep(100);
        }
        fail("Timed out waiting for the local reader");
    }

    private void screenshot(String name) throws IOException {
        Bitmap bitmap = instrumentation.getUiAutomation().takeScreenshot();
        assertNotNull(bitmap);
        File folder = new File(context.getExternalFilesDir(null), "ui-review"); folder.mkdirs();
        try (OutputStream out = new FileOutputStream(new File(folder, name))) {
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, out);
        }
        bitmap.recycle();
    }

    @Test public void localReadingDoesNotInvokeGeminiAndExportsOnDemand() throws Exception {
        File captures = new File(context.getCacheDir(), "captures"); captures.mkdirs();
        File photo = File.createTempFile("reader_fixture_", ".jpg", captures);
        Bitmap bitmap = Bitmap.createBitmap(1200, 240, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap); canvas.drawColor(Color.WHITE);
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG); paint.setColor(Color.BLACK); paint.setTextSize(80);
        canvas.drawText("POCARI SWEAT 123", 40, 140, paint);
        try (OutputStream out = new FileOutputStream(photo)) { bitmap.compress(Bitmap.CompressFormat.JPEG, 98, out); }
        bitmap.recycle();
        Uri uri = FileProvider.getUriForFile(context, context.getPackageName() + ".files", photo);
        IntentFilter filter = new IntentFilter(Intent.ACTION_GET_CONTENT); filter.addDataType("image/*");
        filter.addCategory(Intent.CATEGORY_OPENABLE);
        Instrumentation.ActivityMonitor picker = instrumentation.addMonitor(filter,
            new Instrumentation.ActivityResult(Activity.RESULT_OK, new Intent().setData(uri)), true);
        File exported = File.createTempFile("reader_export_", ".zip", captures);
        Uri output = FileProvider.getUriForFile(context, context.getPackageName() + ".files", exported);
        IntentFilter exportFilter = new IntentFilter(Intent.ACTION_CREATE_DOCUMENT); exportFilter.addDataType("application/zip");
        exportFilter.addCategory(Intent.CATEGORY_OPENABLE);
        Instrumentation.ActivityMonitor destination = instrumentation.addMonitor(exportFilter,
            new Instrumentation.ActivityResult(Activity.RESULT_OK, new Intent().setData(output)), true);
        File scans = new File(context.getFilesDir(), "scans");
        Set<String> before = new HashSet<>();
        if (scans.isDirectory()) for (File dir : scans.listFiles()) before.add(dir.getName());
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> {
                LinearLayout page = activity.findViewById(R.id.page_content);
                assertTrue(page.indexOfChild(activity.findViewById(R.id.local_section)) < page.indexOfChild(activity.findViewById(R.id.gemini_section)));
                assertFalse(activity.findViewById(R.id.ask_gemini).isEnabled());
                assertFalse(activity.findViewById(R.id.analyze_details).isEnabled());
                assertEquals(android.view.View.GONE, activity.findViewById(R.id.study_options).getVisibility());
                assertTrue(activity.findViewById(R.id.scan).getGlobalVisibleRect(new Rect()));
                activity.findViewById(R.id.import_photo).performClick();
            });
            await(scenario, activity -> activity.findViewById(R.id.scan).isEnabled());
            scenario.onActivity(activity -> {
                assertEquals("Your label text will appear here.", ((TextView) activity.findViewById(R.id.result)).getText().toString());
                activity.findViewById(R.id.full_photo).performClick();
            });
            await(scenario, activity -> ((TextView) activity.findViewById(R.id.result)).getText().toString().contains("POCARI"));
            scenario.onActivity(activity -> {
                assertTrue(activity.findViewById(R.id.ask_gemini).isEnabled());
                assertTrue(activity.findViewById(R.id.analyze_details).isEnabled());
                assertEquals(android.view.View.GONE, activity.findViewById(R.id.details_card).getVisibility());
                assertEquals("Your base Gemini answer will appear here.", ((TextView) activity.findViewById(R.id.gemini_result)).getText().toString());
                assertEquals("Your fine-tuned Gemini answer will appear here.", ((TextView) activity.findViewById(R.id.tuned_result)).getText().toString());
                assertFalse(activity.findViewById(R.id.speak_gemini).isEnabled());
            });
            File created = null;
            for (File dir : scans.listFiles()) if (!before.contains(dir.getName())) created = dir;
            assertNotNull(created);
            JSONObject record = new JSONObject(new String(java.nio.file.Files.readAllBytes(new File(created, "scan.json").toPath()), java.nio.charset.StandardCharsets.UTF_8));
            assertFalse(record.getBoolean("semantic_requested"));
            assertFalse(record.getBoolean("images_saved"));
            assertFalse(new File(created, "source.png").exists());
            screenshot("local-reader.png");
            scenario.onActivity(activity -> {
                activity.findViewById(R.id.gemini_section).requestRectangleOnScreen(new Rect(0, 0, 1, 550), true);
            });
            instrumentation.waitForIdleSync(); screenshot("gemini-section.png");
            // Do not click Ask Gemini: a real connection may already be saved on this device.
            scenario.onActivity(activity -> {
                assertTrue(((TextView) activity.findViewById(R.id.result)).getText().toString().contains("POCARI"));
            });
            scenario.onActivity(activity -> { activity.findViewById(R.id.toggle_study).performClick(); activity.findViewById(R.id.export_scan).performClick(); });
            await(scenario, activity -> ((TextView) activity.findViewById(R.id.status)).getText().toString().contains("Scan record exported"));
            try (ZipFile zip = new ZipFile(exported)) { assertNotNull(zip.getEntry("source.png")); assertNotNull(zip.getEntry("scan.json")); }
        } finally {
            instrumentation.removeMonitor(picker); instrumentation.removeMonitor(destination); photo.delete(); exported.delete();
        }
    }
}
