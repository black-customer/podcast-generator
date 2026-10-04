package com.bruce.ieltspod;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.json.JSONObject;
import org.json.JSONArray;
import static org.junit.Assert.*;

/** Android 上执行实际发货的共享引擎；不改用户目录、不使用网络或真实凭据。 */
@RunWith(AndroidJUnit4.class)
public final class LearningEngineTest {
    @Test public void nativeEngineCanCreateImportAndKeepEvidence() throws Exception {
        LearningStore db=new LearningStore(InstrumentationRegistry.getInstrumentation().getTargetContext());
        JSONObject state=db.call("createState",new JSONArray());
        assertEquals(1,state.getInt("version"));
        JSONObject raw=new JSONObject().put("title","Synthetic test").put("messages",new JSONArray()
            .put(new JSONObject().put("id","m1").put("role","user").put("text","How do I say dietary fiber?"))
            .put(new JSONObject().put("id","m2").put("role","assistant").put("text","Dietary fiber.")));
        JSONObject item=new JSONObject(String.valueOf(db.invoke("importConversation",new JSONArray().put(raw).put("2026-10-03T10:00:00+08:00"),state)));
        assertEquals(2,item.getJSONArray("messages").length());assertEquals(1,state.getJSONObject("conversations").length());
        JSONObject again=new JSONObject(String.valueOf(db.invoke("importConversation",new JSONArray().put(raw).put("2026-10-03T11:00:00+08:00"),state)));
        assertEquals(item.getString("id"),again.getString("id"));
        assertEquals("2027-01-01",new org.json.JSONTokener(String.valueOf(db.invoke("addDays",new JSONArray().put("2026-12-31").put(1),null))).nextValue());
        assertEquals("2028-02-29",new org.json.JSONTokener(String.valueOf(db.invoke("addDays",new JSONArray().put("2028-02-28").put(1),null))).nextValue());
    }
}
