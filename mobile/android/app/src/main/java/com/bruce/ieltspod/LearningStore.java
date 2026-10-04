package com.bruce.ieltspod;

import android.content.Context;
import android.util.AtomicFile;
import org.json.JSONArray;
import org.json.JSONObject;
import org.mozilla.javascript.Scriptable;
import org.mozilla.javascript.ScriptableObject;
import org.mozilla.javascript.Function;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.OffsetDateTime;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

/** 原生服务与界面共用同一文件锁，避免阶段提交覆盖用户练习。 */
public final class LearningStore {
    static volatile File testRoot;
    public static final Object LOCK = new Object();
    private final Context app;
    public LearningStore(Context context) { app = context.getApplicationContext(); }
    public static String now() {
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.ROOT);
        return f.format(new Date());
    }
    public File root() { File d = BuildConfig.DEBUG && testRoot != null ? testRoot : new File(app.getFilesDir(), "learning"); d.mkdirs(); return d; }
    public File media(String name) {
        if (!name.matches("[a-zA-Z0-9_.-]+")) throw new IllegalArgumentException("媒体名称无效");
        File d = new File(root(), "media"); d.mkdirs(); return new File(d, name);
    }
    public String asset(String path) throws Exception {
        try (java.io.InputStream in = app.getAssets().open(path);java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream()) {
            byte[] b=new byte[8192];int n;while((n=in.read(b))!=-1)out.write(b,0,n);return new String(out.toByteArray(),StandardCharsets.UTF_8); }
    }
    public JSONObject read() throws Exception {
        AtomicFile f = new AtomicFile(new File(root(), "state.v1.json"));
        if (!f.getBaseFile().exists() && !new File(f.getBaseFile()+".bak").exists())
            return call("createState", new JSONArray());
        JSONObject s = new JSONObject(new String(f.readFully(), StandardCharsets.UTF_8));
        if (s.optInt("version") != 1) throw new IllegalStateException("本机数据版本不支持，原件已保留");
        for(String key:new String[]{"topics","conversations","cards","sessions","receipts","drafts","listening","jobs","settings","migration"})
            if(!(s.opt(key) instanceof JSONObject))throw new IllegalStateException("本机数据结构损坏，原件已保留");
        if(!(s.opt("attempts") instanceof JSONArray))throw new IllegalStateException("本机练习记录损坏，原件已保留");
        return s;
    }
    public void write(JSONObject state) throws Exception {
        if (state.optInt("version") != 1) throw new IllegalArgumentException("拒绝写入未知数据版本");
        state.put("revision",state.optLong("revision",0)+1);
        AtomicFile f = new AtomicFile(new File(root(), "state.v1.json")); FileOutputStream out = null;
        try { out = f.startWrite(); out.write(state.toString().getBytes(StandardCharsets.UTF_8)); f.finishWrite(out); }
        catch (Exception e) { if (out != null) f.failWrite(out); throw e; }
    }
    public void writeMedia(File file, byte[] bytes) throws Exception {
        AtomicFile f = new AtomicFile(file); FileOutputStream out = null;
        try { out=f.startWrite();out.write(bytes);f.finishWrite(out); }
        catch(Exception e){if(out!=null)f.failWrite(out);throw e;}
    }
    public JSONObject call(String name, JSONArray args) throws Exception {
        Object value = invoke(name, args, null); return new JSONObject(String.valueOf(value));
    }
    public JSONObject mutate(String name, JSONArray args) throws Exception {
        synchronized (LOCK) { JSONObject s=read(); Object result=invoke(name,args,s);write(s);
            return new JSONObject().put("value",new org.json.JSONTokener(String.valueOf(result)).nextValue()); }
    }
    public Object invoke(String name, JSONArray args, JSONObject state) throws Exception {
        if(!name.matches("[a-zA-Z]+"))throw new IllegalArgumentException("本机动作无效");
        org.mozilla.javascript.Context cx=org.mozilla.javascript.Context.enter();
        try {
            cx.setOptimizationLevel(-1);cx.setLanguageVersion(org.mozilla.javascript.Context.VERSION_ES6);
            Scriptable scope=cx.initSafeStandardObjects();
            ScriptableObject.putProperty(scope,"NativeDigest",org.mozilla.javascript.Context.javaToJS(new Digest(),scope));
            cx.evaluateString(scope,asset("public/static/mobile-core.js"),"mobile-core",1,null);
            cx.evaluateString(scope,asset("public/static/mobile-api-core.js"),"mobile-api",1,null);
            String input=args.toString();
            if(state!=null)input="["+state.toString()+(args.length()>0?","+input.substring(1):"]");
            cx.evaluateString(scope,"var callArgs=JSON.parse("+JSONObject.quote(input)+"); var callResult=MobileCore["+JSONObject.quote(name)+"].apply(null,callArgs);", "request",1,null);
            if(state!=null){JSONObject changed=new JSONObject(org.mozilla.javascript.Context.toString(cx.evaluateString(scope,"JSON.stringify(callArgs[0])","state",1,null)));
                java.util.Iterator<String> keys=state.keys();java.util.ArrayList<String> old=new java.util.ArrayList<>();while(keys.hasNext())old.add(keys.next());for(String k:old)state.remove(k);
                java.util.Iterator<String> updated=changed.keys();while(updated.hasNext()){String k=updated.next();state.put(k,changed.get(k));}}
            return org.mozilla.javascript.Context.toString(cx.evaluateString(scope,"JSON.stringify(callResult)","result",1,null));
        } finally { org.mozilla.javascript.Context.exit(); }
    }
    public JSONObject bank() throws Exception { return bank(read()); }
    public JSONObject bank(JSONObject state) throws Exception {
        if(state.has("bank")){if(!(state.opt("bank") instanceof JSONObject) || !(state.getJSONObject("bank").opt("questions") instanceof JSONArray))throw new IllegalStateException("本机题库结构损坏，请保留原件");
            return state.getJSONObject("bank");}return new JSONObject(asset("public/static/question-bank-public.json")); }
    public static final class Digest {
        public String bytesSha256(byte[] bytes)throws Exception{return hex(MessageDigest.getInstance("SHA-256").digest(bytes));}
        private String hex(byte[] bytes){StringBuilder s=new StringBuilder();for(byte b:bytes)s.append(String.format(Locale.ROOT,"%02x",b & 255));return s.toString();}
        public String fileSha256(File file) throws Exception {
            MessageDigest md=MessageDigest.getInstance("SHA-256");
            try(java.io.FileInputStream in=new java.io.FileInputStream(file)){byte[] b=new byte[32768];int n;while((n=in.read(b))!=-1)md.update(b,0,n);}
            StringBuilder s=new StringBuilder();for(byte b:md.digest())s.append(String.format(Locale.ROOT,"%02x",b & 255));return s.toString();
        }
        public String sha256(String text) throws Exception {
            byte[] h=MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8));StringBuilder s=new StringBuilder();
            for(byte b:h)s.append(String.format(Locale.ROOT,"%02x",b & 255));return s.toString();
        }
    }
}
