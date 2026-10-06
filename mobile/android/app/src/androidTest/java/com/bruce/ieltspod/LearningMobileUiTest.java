package com.bruce.ieltspod;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry;
import androidx.test.runner.lifecycle.Stage;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.Assert.*;

/** 使用实际 WebView 和原生桥，不依赖浏览器模拟的界面冒烟。 */
@RunWith(AndroidJUnit4.class)
public final class LearningMobileUiTest {
    private MainActivity activity;
    private String js(String code)throws Exception{
        CountDownLatch done=new CountDownLatch(1);AtomicReference<String> out=new AtomicReference<>();
        InstrumentationRegistry.getInstrumentation().runOnMainSync(()->activity.getBridge().getWebView().evaluateJavascript(code,value->{out.set(value);done.countDown();}));
        assertTrue(done.await(10,TimeUnit.SECONDS));Object value=new org.json.JSONTokener(out.get()).nextValue();return String.valueOf(value);
    }
    private void waitText(String expected)throws Exception{long deadline=android.os.SystemClock.elapsedRealtime()+15000;String text="";
        do{Thread.sleep(100);text=js("document.getElementById('app').innerText");if(text.contains(expected))return;}while(android.os.SystemClock.elapsedRealtime()<deadline);
        fail("screen did not show "+expected+": "+text);
    }
    private void screenshot(Context app,String name)throws Exception{
        js("window.__qaPaint=false;document.getElementById('app').scrollTop=0;requestAnimationFrame(()=>requestAnimationFrame(()=>window.__qaPaint=true));");
        long deadline=android.os.SystemClock.elapsedRealtime()+5000;while(!js("window.__qaPaint===true").equals("true")){
            if(android.os.SystemClock.elapsedRealtime()>deadline)fail("WebView did not paint");Thread.sleep(30);}
        InstrumentationRegistry.getInstrumentation().waitForIdleSync();Thread.sleep(200);
        Bitmap image=InstrumentationRegistry.getInstrumentation().getUiAutomation().takeScreenshot();assertNotNull(image);
        File dir=new File(app.getCacheDir(),"mobile-qa");dir.mkdirs();try(FileOutputStream out=new FileOutputStream(new File(dir,name))){image.compress(Bitmap.CompressFormat.PNG,100,out);}image.recycle();}
    @Test public void nativeUiImportsTextAndKeepsMobileNavigation()throws Exception{
        Context app=InstrumentationRegistry.getInstrumentation().getTargetContext();LearningStore.testRoot=new File(app.getCacheDir(),"learning-ui-"+java.util.UUID.randomUUID());
        try{app.startActivity(new Intent(app,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));Thread.sleep(2500);
            AtomicReference<MainActivity> current=new AtomicReference<>();
            InstrumentationRegistry.getInstrumentation().runOnMainSync(()->{for(Stage stage:new Stage[]{Stage.RESUMED,Stage.STARTED,Stage.CREATED})
                for(Activity candidate:ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(stage))if(candidate instanceof MainActivity)current.set((MainActivity)candidate);});
            activity=current.get();assertNotNull(activity);InstrumentationRegistry.getInstrumentation().runOnMainSync(()->activity.getBridge().getWebView().reload());
            long boot=android.os.SystemClock.elapsedRealtime()+20000;
            while(!js("typeof MobileRuntime!=='undefined' && MobileRuntime.native && MobileRuntime.state!==null").equals("true")){
                if(android.os.SystemClock.elapsedRealtime()>boot)fail("native UI did not finish booting");Thread.sleep(100);}
            js("location.hash='#/today';route();");waitText("准备一份练习内容");
            js("document.body.setAttribute('data-mobile-theme','light');");
            assertEquals("true",js("MobileRuntime.native"));assertEquals("rgb(245, 247, 251)",js("getComputedStyle(document.body).backgroundColor"));
            screenshot(app,"native-today.png");
            assertEquals("英语说说说",app.getApplicationInfo().loadLabel(app.getPackageManager()).toString());
            LearningStore db=new LearningStore(app);JSONObject state=db.read();
            JSONObject texts=new JSONObject().put("question","Where did you grow up?")
                .put("original_answer","我在河边长大。").put("natural_english","I grew up by the river.")
                .put("podcast_text","B: I grew up by the river.").put("podcast_script","B: I grew up by the river.");
            state.getJSONObject("topics").put("t",new JSONObject().put("id","t").put("name","合成来源")
                .put("items",new JSONObject().put("i",new JSONObject().put("id","i").put("texts",texts)
                    .put("material",LearningEngineTest.homeMaterial(db,texts))
                    .put("audio",new JSONObject().put("podcast","/synthetic.m4a")))));
            db.write(state);js("MobileRuntime.snapshot().then(()=>route());");waitText("我在河边长大。");
            assertFalse(js("document.getElementById('app').innerText").contains("I grew up by the river."));
            js("document.getElementById('home-toggle-answer').click();");waitText("I grew up by the river.");
            assertEquals("true",js("document.getElementById('home-answer-audio').paused"));
            assertFalse(db.read().getJSONObject("topics").getJSONObject("t").getJSONObject("items").getJSONObject("i").has("progress"));
            screenshot(app,"native-home-answer.png");
            js("location.hash='#/chat-import';");waitText("整理一次英语聊天");
            js("document.getElementById('chat-import-input').value='User: How do I say dietary fiber?\\nAssistant: Dietary fiber.';document.getElementById('chat-read').click();");
            waitText("2 条文本发言");screenshot(app,"native-chat.png");
            js("location.hash='#/my/voices';");waitText("我的自然表达的声音");screenshot(app,"native-settings.png");
            assertEquals("4",js("document.querySelectorAll('.nav-menu .nav-item').length"));
            assertEquals("1",js("document.querySelectorAll('.nav-menu .active').length"));
            assertEquals("#/my",js("document.querySelector('.nav-menu [aria-current]').getAttribute('href')"));
            assertEquals("true",js("document.documentElement.scrollWidth<=innerWidth"));
        }finally{LearningStore.testRoot=null;}
    }
    @Test public void nativeRecorderPreservesInterruptedAudioAndSource()throws Exception{
        Context app=InstrumentationRegistry.getInstrumentation().getTargetContext();
        LearningStore.testRoot=new File(app.getCacheDir(),"learning-recorder-"+java.util.UUID.randomUUID());
        try{
            InstrumentationRegistry.getInstrumentation().getUiAutomation().grantRuntimePermission(app.getPackageName(),android.Manifest.permission.RECORD_AUDIO);
            app.startActivity(new Intent(app,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));Thread.sleep(2000);
            AtomicReference<MainActivity> current=new AtomicReference<>();
            InstrumentationRegistry.getInstrumentation().runOnMainSync(()->{
                for(Activity candidate:ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED))
                    if(candidate instanceof MainActivity)current.set((MainActivity)candidate);});
            activity=current.get();assertNotNull(activity);
            InstrumentationRegistry.getInstrumentation().runOnMainSync(()->activity.getBridge().getWebView().reload());
            long boot=android.os.SystemClock.elapsedRealtime()+20000;
            while(!js("typeof MobileRuntime!=='undefined' && MobileRuntime.native && MobileRuntime.state!==null").equals("true")){
                if(android.os.SystemClock.elapsedRealtime()>boot)fail("recorder UI did not boot");Thread.sleep(100);}
            js("window.__qaRecorder='waiting';MobileRuntime.plugin.recordStart({source:{topic_id:'synthetic',item_id:'answer',stage:'before'}}).then(()=>window.__qaRecorder='started').catch(e=>window.__qaRecorder=e.message);");
            long started=android.os.SystemClock.elapsedRealtime()+10000;
            while(!js("window.__qaRecorder").equals("started")){
                if(android.os.SystemClock.elapsedRealtime()>started)fail("recordStart: "+js("window.__qaRecorder"));Thread.sleep(50);}
            Thread.sleep(1200);InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand("input keyevent 3").close();
            LearningStore db=new LearningStore(app);JSONObject recording=null;long stopped=android.os.SystemClock.elapsedRealtime()+10000;
            while(recording==null){synchronized(LearningStore.LOCK){recording=db.read().optJSONObject("pending_recording");}
                if(android.os.SystemClock.elapsedRealtime()>stopped)fail("interrupted recording was not saved");Thread.sleep(50);}
            assertTrue(recording.getBoolean("interrupted"));assertEquals("before",recording.getJSONObject("source").getString("stage"));
            File audio=new File(recording.getString("path"));assertTrue(audio.length()>100);assertTrue(NativeAudio.decode(audio).length>12000);
        }finally{LearningStore.testRoot=null;}
    }
}
