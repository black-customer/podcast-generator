package com.bruce.ieltspod;

import android.content.Context;
import android.content.Intent;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public final class LearningNativeFlowTest {
    private byte[] tone(){
        int samples=24000;ByteBuffer b=ByteBuffer.allocate(44+samples*2).order(ByteOrder.LITTLE_ENDIAN);
        b.put("RIFF".getBytes()).putInt(36+samples*2).put("WAVEfmt ".getBytes()).putInt(16).putShort((short)1).putShort((short)1)
            .putInt(24000).putInt(48000).putShort((short)2).putShort((short)16).put("data".getBytes()).putInt(samples*2);
        for(int n=0;n<samples;n++)b.putShort((short)(Math.sin(n*2*Math.PI*440/24000)*3500));return b.array();
    }
    @Test public void publicShareParsersOnAndroid() throws Exception {
        android.os.Bundle args=InstrumentationRegistry.getArguments();LearningStore db=new LearningStore(InstrumentationRegistry.getInstrumentation().getTargetContext());
        if(args.containsKey("proxy_port"))LearningHttp.testProxy=new java.net.Proxy(java.net.Proxy.Type.HTTP,new java.net.InetSocketAddress("10.0.2.2",Integer.parseInt(args.getString("proxy_port"))));
        try {
        for(String provider:new String[]{"chatgpt","doubao"}){
            String url=args.getString(provider+"_url");if(url==null)continue;
            String html=new String(LearningHttp.request(url,null,null),java.nio.charset.StandardCharsets.UTF_8);
            if(args.containsKey("capture_share_response"))db.writeMedia(new File(InstrumentationRegistry.getInstrumentation().getTargetContext().getCacheDir(),"share-qa-"+provider+".html"),html.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            JSONObject parsed=db.call(provider.equals("chatgpt")?"parseChatGPTPage":"parseDoubaoPage",new JSONArray().put(html));
            JSONArray messages=parsed.getJSONArray("messages");assertTrue(messages.length()>1);assertEquals("shared_snapshot",parsed.getString("scope"));
            assertFalse(messages.getJSONObject(0).getString("text").isEmpty());assertFalse(messages.getJSONObject(messages.length()-1).getString("text").isEmpty());
            System.out.println("SHARE_IMPORT "+provider+" messages="+messages.length()+" title="+parsed.getString("title"));
        }
        }finally{LearningHttp.testProxy=null;}
    }
    @Test public void nativeGenerationSurvivesBackgroundAndProducesPlayableAudio() throws Exception {
        Context app=InstrumentationRegistry.getInstrumentation().getTargetContext();
        File test=new File(app.getCacheDir(),"learning-instrument-"+java.util.UUID.randomUUID());LearningStore.testRoot=test;
        LearningStore db=new LearningStore(app);
        try{
            new LearningSecrets(app).save("synthetic-instrument-key");
            JSONObject raw=new JSONObject().put("title","Synthetic native flow").put("messages",new JSONArray()
                .put(new JSONObject().put("id","m1").put("role","user").put("text","How do I say dietary fiber?"))
                .put(new JSONObject().put("id","m2").put("role","assistant").put("text","Dietary fiber.")));
            JSONObject imported=(JSONObject)db.mutate("importConversation",new JSONArray().put(raw).put(LearningStore.now())).get("value");String cid=imported.getString("id");
            JSONObject result=new JSONObject().put("dialogue",new JSONArray()
                .put(new JSONObject().put("speaker","A").put("en","What would you like to say?").put("zh","你想说什么？"))
                .put(new JSONObject().put("speaker","B").put("en","Mushrooms have some dietary fiber.").put("zh","蘑菇含有一些膳食纤维。")))
                .put("notes",new JSONArray().put(new JSONObject().put("kind","explicit_gap").put("target","dietary fiber").put("prompt_zh","说说蘑菇含有的成分。")
                    .put("reference_en","Mushrooms have some dietary fiber.").put("explanation","fiber 不可数。")
                    .put("sources",new JSONArray().put(new JSONObject().put("message_id","m1").put("quote","dietary fiber")))));
            LearningHttp.testTransport=(address,body)->{
                Thread.sleep(200);
                if(address.endsWith("/audio/speech"))return tone();
                return new JSONObject().put("usage",new JSONObject().put("total_tokens",123)).put("choices",new JSONArray().put(new JSONObject()
                    .put("message",new JSONObject().put("content",result.toString())))).toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
            };
            Intent open=new Intent(app,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);app.startActivity(open);
            Thread.sleep(2500);
            synchronized(LearningStore.LOCK){JSONObject state=db.read();state.getJSONObject("jobs").put(cid,new JSONObject().put("id",cid).put("job_id",cid)
                .put("kind","conversation").put("conversation_id",cid).put("state","queued").put("created_at",LearningStore.now()));db.write(state);}
            androidx.core.content.ContextCompat.startForegroundService(app,new Intent(app,GenerationService.class).putExtra("job_id",cid));
            InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand("input keyevent 223").close();
            long deadline=android.os.SystemClock.elapsedRealtime()+30000;JSONObject job;
            do{Thread.sleep(200);synchronized(LearningStore.LOCK){job=db.read().getJSONObject("jobs").getJSONObject(cid);}
                if(job.optString("state").equals("interrupted") && job.has("inflight"))fail(job.toString());
            }while(!job.optString("state").equals("done") && android.os.SystemClock.elapsedRealtime()<deadline);
            assertEquals("done",job.getString("state"));JSONObject state=db.read(),conv=state.getJSONObject("conversations").getJSONObject(cid);
            assertTrue(new File(conv.getString("audio")).length()>1000);assertEquals(2,conv.getJSONObject("timeline").getJSONArray("lines").length());
            assertEquals(1,state.getJSONObject("cards").length());assertTrue(NativeAudio.decode(new File(conv.getString("audio"))).length>24000);
            assertFalse(state.toString().contains("synthetic-instrument-key"));
            InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand("input keyevent 224").close();
            InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand("wm dismiss-keyguard").close();
            app.startActivity(open);Thread.sleep(700);
            java.util.concurrent.atomic.AtomicReference<com.google.common.util.concurrent.ListenableFuture<androidx.media3.session.MediaController>> connection=new java.util.concurrent.atomic.AtomicReference<>();
            InstrumentationRegistry.getInstrumentation().runOnMainSync(()->connection.set(new androidx.media3.session.MediaController.Builder(app,
                new androidx.media3.session.SessionToken(app,new android.content.ComponentName(app,PlaybackService.class))).buildAsync()));
            androidx.media3.session.MediaController player=connection.get().get(15,java.util.concurrent.TimeUnit.SECONDS);
            InstrumentationRegistry.getInstrumentation().runOnMainSync(()->{player.setMediaItem(androidx.media3.common.MediaItem.fromUri(android.net.Uri.fromFile(new File(conv.optString("audio")))));player.prepare();player.play();});
            java.util.concurrent.atomic.AtomicBoolean playing=new java.util.concurrent.atomic.AtomicBoolean();long ready=android.os.SystemClock.elapsedRealtime()+10000;
            do{Thread.sleep(50);InstrumentationRegistry.getInstrumentation().runOnMainSync(()->playing.set(player.isPlaying()));}while(!playing.get() && android.os.SystemClock.elapsedRealtime()<ready);
            assertTrue("native playback must start",playing.get());
            InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand("input keyevent 3").close();Thread.sleep(500);
            InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand("input keyevent 223").close();Thread.sleep(500);
            java.util.concurrent.atomic.AtomicLong position=new java.util.concurrent.atomic.AtomicLong();
            InstrumentationRegistry.getInstrumentation().runOnMainSync(()->{position.set(player.getCurrentPosition());player.pause();player.release();});
            assertTrue("playback must advance while app is backgrounded",position.get()>300);
        } finally {app.stopService(new Intent(app,GenerationService.class));LearningHttp.testTransport=null;LearningStore.testRoot=null;
            InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand("input keyevent 224").close();
            InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand("wm dismiss-keyguard").close();
            app.stopService(new Intent(app,PlaybackService.class));
            app.getSharedPreferences("learning_test_secrets",Context.MODE_PRIVATE).edit().clear().commit();}
    }
}
