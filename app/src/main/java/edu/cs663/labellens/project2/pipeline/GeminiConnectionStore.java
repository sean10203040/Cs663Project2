package edu.cs663.labellens.project2.pipeline;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Device-local connection storage. Call crypto and disk operations on a worker. */
public final class GeminiConnectionStore {
    private static final String PROVIDER = "AndroidKeyStore";
    private static final String CIPHER = "AES/GCM/NoPadding";
    private final SharedPreferences preferences;
    private final String alias;

    public static final class Connection {
        public final String endpoint, token, variant;
        private Connection(String endpoint, String token, String variant) {
            this.endpoint = endpoint; this.token = token; this.variant = variant;
        }
    }

    public GeminiConnectionStore(Context context) {
        this(context, "gemini_connection_v1", context.getPackageName() + ".gemini_token.v1");
    }

    // Separate namespace for instrumentation checks, without touching a real saved token.
    GeminiConnectionStore(Context context, String preferencesName, String alias) {
        preferences = context.getApplicationContext().getSharedPreferences(preferencesName, Context.MODE_PRIVATE);
        this.alias = alias;
    }

    private KeyStore keyStore() throws GeneralSecurityException, IOException {
        KeyStore store = KeyStore.getInstance(PROVIDER); store.load(null); return store;
    }

    private SecretKey key(boolean create) throws GeneralSecurityException, IOException {
        KeyStore store = keyStore();
        if (store.containsAlias(alias)) return (SecretKey) store.getKey(alias, null);
        if (!create) throw new GeneralSecurityException("Saved connection key is unavailable");
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, PROVIDER);
        generator.init(new KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setKeySize(256).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
        return generator.generateKey();
    }

    public Connection load(String defaultEndpoint, String defaultVariant) throws GeneralSecurityException, IOException {
        String envelope = preferences.getString("encrypted_token", ""), token = "";
        if (!envelope.isEmpty()) {
            String[] parts = envelope.split(":", -1);
            if (parts.length != 3 || !parts[0].equals("v1")) throw new GeneralSecurityException("Invalid saved connection format");
            try {
                byte[] iv = Base64.decode(parts[1], Base64.NO_WRAP);
                byte[] data = Base64.decode(parts[2], Base64.NO_WRAP);
                if (iv.length != 12) throw new GeneralSecurityException("Invalid saved connection nonce");
                Cipher cipher = Cipher.getInstance(CIPHER);
                cipher.init(Cipher.DECRYPT_MODE, key(false), new GCMParameterSpec(128, iv));
                cipher.updateAAD(alias.getBytes(StandardCharsets.UTF_8));
                token = new String(cipher.doFinal(data), StandardCharsets.UTF_8);
            } catch (IllegalArgumentException error) {
                throw new GeneralSecurityException("Invalid saved connection encoding", error);
            }
        }
        return new Connection(preferences.getString("backend", defaultEndpoint), token,
            preferences.getString("variant", defaultVariant));
    }

    public void save(String endpoint, String token, String variant) throws GeneralSecurityException, IOException {
        if (token.length() < 24) throw new IllegalArgumentException("Application token is too short");
        Cipher cipher = Cipher.getInstance(CIPHER);
        cipher.init(Cipher.ENCRYPT_MODE, key(true)); // Provider generates a fresh random nonce.
        cipher.updateAAD(alias.getBytes(StandardCharsets.UTF_8));
        String envelope = "v1:" + Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":"
            + Base64.encodeToString(cipher.doFinal(token.getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP);
        if (!preferences.edit().putString("encrypted_token", envelope).putString("backend", endpoint)
            .putString("variant", variant).commit()) throw new IOException("Could not save the connection");
    }

    public void forgetToken() throws GeneralSecurityException, IOException {
        if (!preferences.edit().remove("encrypted_token").commit()) throw new IOException("Could not remove the saved token");
        KeyStore store = keyStore();
        if (store.containsAlias(alias)) store.deleteEntry(alias);
    }
}
