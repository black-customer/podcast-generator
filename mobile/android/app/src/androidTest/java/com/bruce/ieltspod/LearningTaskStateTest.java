package com.bruce.ieltspod;

import android.content.Context;
import android.content.Intent;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.Assert.*;

/** 原生收费任务的失败与取消边界：只使用隔离文件和合成请求。 */
@RunWith(AndroidJUnit4.class)
public final class LearningTaskStateTest {
    private String queue(LearningStore db) throws Exception {
        JSONObject raw=new JSONObject().put("title","Synthetic task failure").put("messages",new JSONArray()
            .put(new JSONObject().put("id","m1").put("role","user").put("text","How do I say whole grain?"))
            .put(new JSONObject().put("id","m2").put("role","assistant").put("text","Whole grain.")));
        String id=((JSONObject)db.mutate("importConversation",new JSONArray().put(raw).put(LearningStore.now())).get("value")).getString("id");
        synchronized(LearningStore.LOCK){JSONObject s=db.read();s.getJSONObject("jobs").put(id,new JSONObject().put("id",id).put("kind","conversation")
            .put("conversation_id",id).put("state","queued").put("created_at",LearningStore.now()));db.write(s);}
        return id;
    }
    private JSONObject awaitStopped(LearningStore db,String id) throws Exception {
        long deadline=android.os.SystemClock.elapsedRealtime()+15000;
        while(android.os.SystemClock.elapsedRealtime()<deadline){Thread.sleep(50);JSONObject job;
            synchronized(LearningStore.LOCK){job=db.read().getJSONObject("jobs").getJSONObject(id);}
            if(!GenerationService.running.contains(id) && !job.optString("state").equals("queued"))return job;}
        throw new AssertionError("native task did not stop");
    }
    @Test public void failuresAndCancellationNeverRetryAutomatically() throws Exception {
        Context app=InstrumentationRegistry.getInstrumentation().getTargetContext();
        LearningStore.testRoot=new File(app.getCacheDir(),"learning-errors-"+java.util.UUID.randomUUID());LearningStore db=new LearningStore(app);
        try {
            app.startActivity(new Intent(app,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));Thread.sleep(2500);
            LearningSecrets secrets=new LearningSecrets(app);secrets.save("synthetic-vault-check");
            assertEquals("synthetic-vault-check",new LearningSecrets(app).read());
            assertFalse(app.getSharedPreferences("learning_test_secrets",Context.MODE_PRIVATE).getString("stepfun","").contains("synthetic-vault-check"));
            for(int status:new int[]{401,429,503}){
                AtomicInteger calls=new AtomicInteger();LearningHttp.testTransport=(address,body)->{calls.incrementAndGet();throw new IllegalStateException("服务返回 HTTP "+status+"，请稍后手动重试");};
                String id=queue(db);androidx.core.content.ContextCompat.startForegroundService(app,new Intent(app,GenerationService.class).putExtra("job_id",id));
                JSONObject job=awaitStopped(db,id);assertEquals("interrupted",job.getString("state"));assertEquals(1,calls.get());
                assertTrue("HTTP status must reach the user",job.getJSONArray("errors").getJSONObject(0).getString("message").contains("HTTP "+status));
                assertFalse("received error response is not unknown",job.has("inflight"));
            }
            AtomicInteger unknownCalls=new AtomicInteger();LearningHttp.testTransport=(address,body)->{unknownCalls.incrementAndGet();throw new java.io.IOException("synthetic disconnected response");};
            String unknown=queue(db);androidx.core.content.ContextCompat.startForegroundService(app,new Intent(app,GenerationService.class).putExtra("job_id",unknown));
            JSONObject paused=awaitStopped(db,unknown);assertEquals("text",paused.getString("inflight"));assertEquals("interrupted",paused.getString("state"));
            Thread.sleep(200);assertEquals(1,unknownCalls.get());
            CountDownLatch sent=new CountDownLatch(1),release=new CountDownLatch(1);
            LearningHttp.testTransport=(address,body)->{sent.countDown();assertTrue(release.await(10,TimeUnit.SECONDS));return "{}".getBytes(java.nio.charset.StandardCharsets.UTF_8);};
            String cancelled=queue(db);androidx.core.content.ContextCompat.startForegroundService(app,new Intent(app,GenerationService.class).putExtra("job_id",cancelled));
            assertTrue(sent.await(10,TimeUnit.SECONDS));app.startService(new Intent(app,GenerationService.class).setAction("cancel").putExtra("job_id",cancelled));
            long cancelDeadline=android.os.SystemClock.elapsedRealtime()+5000;
            while(!db.read().getJSONObject("jobs").getJSONObject(cancelled).getString("state").equals("cancelled")){
                if(android.os.SystemClock.elapsedRealtime()>cancelDeadline)fail("cancel was not persisted");Thread.sleep(30);}
            release.countDown();assertEquals("cancelled",awaitStopped(db,cancelled).getString("state"));
            JSONObject conversation=db.read().getJSONObject("conversations").getJSONObject(cancelled);
            assertEquals("How do I say whole grain?",conversation.getJSONArray("messages").getJSONObject(0).getString("text"));
            assertEquals(0,conversation.getJSONArray("dialogue").length());assertTrue(conversation.isNull("audio"));
        } finally {
            app.stopService(new Intent(app,GenerationService.class));LearningHttp.testTransport=null;LearningStore.testRoot=null;
            app.getSharedPreferences("learning_test_secrets",Context.MODE_PRIVATE).edit().clear().commit();
        }
    }
}
