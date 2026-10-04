package com.bruce.ieltspod;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** 凭据仅在请求线程内解密，不作为本机 API 的返回值。 */
final class LearningSecrets {
    private final Context app;
    private static final String ALIAS="ieltspod.stepfun.v1";
    private String prefs(){return BuildConfig.DEBUG && LearningStore.testRoot!=null?"learning_test_secrets":"learning_secrets";}
    LearningSecrets(Context app){this.app=app.getApplicationContext();}
    private SecretKey key() throws Exception {
        KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);
        if(!ks.containsAlias(ALIAS)){KeyGenerator g=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
            g.init(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());g.generateKey();}
        return (SecretKey)ks.getKey(ALIAS,null);
    }
    void save(String value) throws Exception {
        Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.ENCRYPT_MODE,key());
        String encoded=Base64.encodeToString(c.getIV(),Base64.NO_WRAP)+":"+Base64.encodeToString(c.doFinal(value.getBytes(java.nio.charset.StandardCharsets.UTF_8)),Base64.NO_WRAP);
        if(!app.getSharedPreferences(prefs(),Context.MODE_PRIVATE).edit().putString("stepfun",encoded).commit())throw new IllegalStateException("密钥保存失败");
    }
    String read() throws Exception {
        String saved=app.getSharedPreferences(prefs(),Context.MODE_PRIVATE).getString("stepfun","");if(saved.isEmpty())return "";
        String[] a=saved.split(":",2);Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Base64.decode(a[0],Base64.NO_WRAP)));
        return new String(c.doFinal(Base64.decode(a[1],Base64.NO_WRAP)),java.nio.charset.StandardCharsets.UTF_8);
    }
    boolean configured(){return app.getSharedPreferences(prefs(),Context.MODE_PRIVATE).contains("stepfun");}
}
