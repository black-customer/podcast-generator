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
    @Test public void homePracticeUsesNativeDigestWithoutCreatingProgress() throws Exception {
        LearningStore db=new LearningStore(InstrumentationRegistry.getInstrumentation().getTargetContext());
        JSONObject state=db.call("createState",new JSONArray());
        JSONObject texts=new JSONObject().put("question","Where did you grow up?")
            .put("original_answer","我在河边长大。").put("natural_english","I grew up by the river.")
            .put("podcast_text","B: I grew up by the river.").put("podcast_script","B: I grew up by the river.");
        JSONObject material=homeMaterial(db,texts);
        state.getJSONObject("topics").put("t",new JSONObject().put("id","t").put("name","合成来源")
            .put("items",new JSONObject().put("i",new JSONObject().put("id","i").put("texts",texts)
                .put("material",material).put("audio",new JSONObject().put("podcast","/synthetic.m4a")))));
        JSONObject result=new JSONObject(String.valueOf(db.invoke("route",new JSONArray().put("GET")
            .put("/api/study/today").put(new JSONObject()).put("2026-10-06T10:00:00+08:00").put(new JSONObject()),state)));
        assertEquals("我在河边长大。",result.getJSONArray("home_practice").getJSONObject(0).getString("zh"));
        assertFalse(state.getJSONObject("topics").getJSONObject("t").getJSONObject("items").getJSONObject("i").has("progress"));
        assertEquals(0,state.getJSONObject("sessions").length());assertEquals(0,state.getJSONArray("attempts").length());
    }
    static JSONObject homeMaterial(LearningStore db,JSONObject texts)throws Exception {
        return db.call("validateStudyMaterial",new JSONArray().put(new JSONObject().put("complete_chinese","我在河边长大。")
            .put("sentences",new JSONArray().put(new JSONObject().put("zh","我在河边长大。")
                .put("en","I grew up by the river.").put("explanation","合成解释").put("usage","合成用法")))).put(texts));
    }
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
