package edu.cs663.labellens.project2.pipeline;

import static org.junit.Assert.*;
import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.security.GeneralSecurityException;
import java.util.UUID;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;

/** Uses only isolated test preferences/keys; makes no cloud requests. */
@RunWith(AndroidJUnit4.class)
public class GeminiConnectionStoreTest {
    private Context context;
    private String preferencesName, alias;
    private GeminiConnectionStore store;
    private static final String TOKEN = "fixture-token-for-local-storage-check-12345";
    private static final String URL = "https://example.test";

    @Before public void prepare() {
        context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        preferencesName = "gemini_connection_test_" + UUID.randomUUID();
        alias = context.getPackageName() + "." + preferencesName;
        store = new GeminiConnectionStore(context, preferencesName, alias);
    }

    @After public void cleanup() throws Exception {
        try { store.forgetToken(); } finally { context.deleteSharedPreferences(preferencesName); }
    }

    @Test public void savedConnectionReloadsAndForgetRemovesCredential() throws Exception {
        store.save(URL, TOKEN, "tuned");
        GeminiConnectionStore reopened = new GeminiConnectionStore(context, preferencesName, alias);
        GeminiConnectionStore.Connection saved = reopened.load("https://fallback.test", "base");
        assertEquals(URL, saved.endpoint); assertEquals(TOKEN, saved.token); assertEquals("tuned", saved.variant);
        assertFalse(context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE).getAll().toString().contains(TOKEN));
        reopened.forgetToken();
        assertEquals("", reopened.load("", "base").token);
        assertEquals(URL, reopened.load("", "base").endpoint);
    }

    @Test public void repeatedSavesUseFreshEncryption() throws Exception {
        store.save(URL, TOKEN, "tuned");
        String first = context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE).getString("encrypted_token", "");
        store.save(URL, TOKEN, "tuned");
        String second = context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE).getString("encrypted_token", "");
        assertNotEquals(first, second);
        assertEquals(TOKEN, store.load("", "").token);
    }

    @Test public void corruptedTokenFailsInsteadOfReturningAnUnverifiedSecret() throws Exception {
        store.save(URL, TOKEN, "tuned");
        String envelope = context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE).getString("encrypted_token", "");
        String[] parts = envelope.split(":");
        byte[] ciphertext = android.util.Base64.decode(parts[2], android.util.Base64.NO_WRAP);
        ciphertext[0] ^= 1;
        String changed = parts[0] + ":" + parts[1] + ":" + android.util.Base64.encodeToString(ciphertext, android.util.Base64.NO_WRAP);
        context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE).edit().putString("encrypted_token", changed).commit();
        try { store.load("", ""); fail("Corrupted ciphertext must be rejected"); }
        catch (GeneralSecurityException expected) { }
    }
}
