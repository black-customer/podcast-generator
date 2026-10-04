package com.bruce.ieltspod;

import android.Manifest;
import android.content.Intent;
import android.media.MediaRecorder;
import android.util.Base64;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;

@CapacitorPlugin(name="Learning",permissions={@Permission(alias="microphone",strings={Manifest.permission.RECORD_AUDIO}),@Permission(alias="notifications",strings={Manifest.permission.POST_NOTIFICATIONS})})
public final class LearningPlugin extends Plugin {
    private final ExecutorService worker=Executors.newFixedThreadPool(4);
    private final Object previewLock=new Object();
    private final java.util.concurrent.CountDownLatch recovered=new java.util.concurrent.CountDownLatch(1);
    private MediaRecorder recorder;
    private File recording;
    private long recordingStarted;
    private JSONObject recordingSource=new JSONObject();
    private com.google.common.util.concurrent.ListenableFuture<androidx.media3.session.MediaController> controller;
    private final android.os.Handler mediaHandler=new android.os.Handler(android.os.Looper.getMainLooper());
    private final Runnable mediaTick=new Runnable(){public void run(){try{if(controller!=null && controller.isDone()){
        androidx.media3.session.MediaController p=controller.get();notifyListeners("mediaState",new JSObject().put("position",p.getCurrentPosition()/1000.0)
            .put("duration",Math.max(0,p.getDuration()/1000.0)).put("playing",p.isPlaying()).put("path",p.getCurrentMediaItem()==null?"":p.getCurrentMediaItem().mediaId).put("ended",p.getPlaybackState()==androidx.media3.common.Player.STATE_ENDED));}
        }catch(Exception ignored){}mediaHandler.postDelayed(this,250);}};
    public static volatile String sharedText="";
    private LearningStore store(){return new LearningStore(getContext());}
    private JSONObject settingsView(JSONObject settings)throws Exception{
        JSONObject safe=new JSONObject();for(String k:new String[]{"stepfun_text_model","stepfun_text_base_url","question_voice_id","answer_voice_id","speed","answer_voice_male","reminder_enabled"})if(settings.has(k))safe.put(k,settings.get(k));
        boolean configured=new LearningSecrets(getContext()).configured();return safe.put("stepfun_api_key_configured",configured).put("stepfun_api_key_set",configured).put("tts_provider","stepfun").put("dry_run",false);
    }
    @Override public void load(){super.load();mediaHandler.post(mediaTick);worker.execute(()->{try{synchronized(LearningStore.LOCK){
        JSONObject s=store().read(),jobs=s.getJSONObject("jobs");boolean changed=false;
        for(java.util.Iterator<String> ids=jobs.keys();ids.hasNext();){String id=ids.next();JSONObject j=jobs.getJSONObject(id);
            if((j.optString("state").equals("running") || j.optString("state").equals("queued")) && !GenerationService.running.contains(id)){
                j.put("state","interrupted").put("errors",new JSONArray().put(new JSONObject().put("message","上次处理被系统中断；已保存阶段保留，可以手动继续。")));changed=true;}}
        if(changed)store().write(s);ReviewReminder.schedule(getContext(),s.getJSONObject("settings").optBoolean("reminder_enabled",false));
    }}catch(Exception ignored){}finally{recovered.countDown();}});}
    @Override protected void handleOnDestroy(){mediaHandler.removeCallbacks(mediaTick);if(controller!=null)androidx.media3.session.MediaController.releaseFuture(controller);worker.shutdownNow();super.handleOnDestroy();}
    @PluginMethod public void media(PluginCall call){getActivity().runOnUiThread(()->{
        if(controller==null){androidx.media3.session.SessionToken token=new androidx.media3.session.SessionToken(getContext(),new android.content.ComponentName(getContext(),PlaybackService.class));
            controller=new androidx.media3.session.MediaController.Builder(getContext(),token).buildAsync();}
        controller.addListener(()->{try{androidx.media3.session.MediaController p=controller.get();String action=call.getString("action","");
            if(action.equals("load")){String path=call.getString("path","");File file=new File(path);
                if(!file.isFile() || !file.getCanonicalPath().startsWith(store().root().getCanonicalPath()+File.separator))throw new IllegalArgumentException("音频不属于本机材料");
                android.os.Bundle extra=new android.os.Bundle();extra.putString("fingerprint",call.getString("fingerprint",""));
                p.setMediaItem(new androidx.media3.common.MediaItem.Builder().setUri(android.net.Uri.fromFile(file)).setMediaId(path)
                    .setMediaMetadata(new androidx.media3.common.MediaMetadata.Builder().setTitle(call.getString("title","英语学习")).setExtras(extra).build()).build());p.prepare();
                double position=call.getDouble("position",0.0);p.seekTo((long)(position*1000));}
            else if(action.equals("play"))p.play();else if(action.equals("pause"))p.pause();else if(action.equals("seek"))p.seekTo((long)(call.getDouble("position",0.0)*1000));
            else if(action.equals("speed"))p.setPlaybackSpeed(call.getFloat("speed",1f));else if(action.equals("volume"))p.setVolume(call.getFloat("volume",1f));
            else throw new IllegalArgumentException("播放动作无效");call.resolve();
        }catch(Exception e){call.reject("音频播放失败，请重新打开材料");}},androidx.core.content.ContextCompat.getMainExecutor(getContext()));
    });}
    @PluginMethod public void request(PluginCall call){worker.execute(()->{
        try{if(!recovered.await(20,java.util.concurrent.TimeUnit.SECONDS))throw new IllegalStateException("本机恢复尚未完成，请重新打开应用");
            String method=call.getString("method","GET"),path=call.getString("url","");JSObject body=call.getObject("body",new JSObject());
            JSONObject parsedImport=null;File preview=null;
            if(path.equals("/api/conversations/import-link")){
                java.net.URL url=new java.net.URL(body.getString("url"));String host=url.getHost();
                if(!url.getProtocol().equals("https") || !(host.equals("chatgpt.com") && url.getPath().startsWith("/share/") || host.equals("www.doubao.com") && url.getPath().startsWith("/thread/")))
                    throw new IllegalArgumentException("请使用 ChatGPT 或豆包的 HTTPS 分享链接");
                String html=new String(LearningHttp.request(url.toString(),null,null),StandardCharsets.UTF_8);
                parsedImport=store().call(host.equals("chatgpt.com")?"parseChatGPTPage":"parseDoubaoPage",new JSONArray().put(html));parsedImport.put("source_url",url.toString());
            }
            if(path.equals("/api/mobile/voice-preview") && method.equals("POST")){
                String voice=body.getString("voice");JSONArray catalogue=new JSONArray(store().asset("public/static/voices.json"));boolean valid=false;
                for(int n=0;n<catalogue.length();n++){JSONObject v=catalogue.getJSONObject(n);if(v.optString("provider").equals("stepfun") && v.optString("voice_id").equals(voice))valid=true;}
                if(!valid)throw new IllegalArgumentException("音色不在当前目录中");preview=store().media("preview-"+voice+".mp3");
                synchronized(previewLock){if(!preview.isFile()){String key=new LearningSecrets(getContext()).read();if(key.isEmpty())throw new IllegalStateException("请先保存 StepFun Key");
                    byte[] bytes=LearningHttp.request("https://api.stepfun.com/v1/audio/speech",new JSONObject().put("model","stepaudio-2.5-tts")
                        .put("input","It's good to hear from you. I'm practising English, one conversation at a time.").put("voice",voice).put("response_format","mp3").put("sample_rate",24000).put("speed",1),key);
                    store().writeMedia(preview,bytes);}}
            }
            synchronized(LearningStore.LOCK){
                LearningStore db=store();JSONObject state=db.read();JSONObject settings=state.getJSONObject("settings");Object result;
                if(path.equals("/api/settings")){
                    LearningSecrets secrets=new LearningSecrets(getContext());
                    if(method.equals("PUT")){
                        String requestedBase=body.optString("stepfun_text_base_url",settings.optString("stepfun_text_base_url",""));
                        if(!requestedBase.isEmpty()){java.net.URL endpoint=new java.net.URL(requestedBase);
                            if(!endpoint.getProtocol().equals("https") || endpoint.getUserInfo()!=null || endpoint.getQuery()!=null || endpoint.getRef()!=null)throw new IllegalArgumentException("文本接口需为不含凭据、查询参数的 HTTPS 地址");}
                        if(body.has("speed") && (body.getDouble("speed")<.5 || body.getDouble("speed")>2))throw new IllegalArgumentException("生成语速需在 0.5 到 2 倍之间");
                        if(body.has("stepfun_api_key") && !body.optString("stepfun_api_key").isEmpty())secrets.save(body.getString("stepfun_api_key"));
                        for(String k:new String[]{"stepfun_text_model","stepfun_text_base_url","question_voice_id","answer_voice_id","speed","answer_voice_male","reminder_enabled"})
                            if(body.has(k))settings.put(k,body.get(k));
                        String base=settings.optString("stepfun_text_base_url","");if(!base.isEmpty() && !base.startsWith("https://"))throw new IllegalArgumentException("文本接口仅支持 HTTPS");
                        ReviewReminder.schedule(getContext(),settings.optBoolean("reminder_enabled",false));
                    }
                    result=settingsView(settings);
                }else if(path.equals("/api/conversations/import-link")){
                    result=new org.json.JSONTokener(String.valueOf(db.invoke("importConversation",new JSONArray().put(parsedImport).put(LearningStore.now()),state))).nextValue();
                }else if(path.equals("/api/mobile/migrate") && method.equals("POST")){
                    JSONArray items=body.getJSONArray("items");
                    for(int n=0;n<items.length();n++){JSONObject i=items.getJSONObject(n),audio=i.optJSONObject("audioData");JSONObject paths=new JSONObject();
                        if(audio!=null)for(java.util.Iterator<String> keys=audio.keys();keys.hasNext();){String tr=keys.next();if(!tr.matches("podcast|monologue|default"))throw new IllegalArgumentException("音轨无效");
                            byte[] bytes=Base64.decode(audio.getString(tr),Base64.DEFAULT);LearningStore.Digest digest=new LearningStore.Digest();
                            File f=db.media(digest.sha256(i.getString("topic_id")+":"+i.getString("id")+":"+tr+":"+digest.bytesSha256(bytes))+".mp3");db.writeMedia(f,bytes);paths.put(tr,f.getAbsolutePath());}
                        JSONObject fingerprints=new JSONObject();for(java.util.Iterator<String> keys=paths.keys();keys.hasNext();){String tr=keys.next();fingerprints.put(tr,new LearningStore.Digest().fileSha256(new File(paths.getString(tr))));}
                        i.remove("audioData");i.put("audio",paths).put("audioFingerprints",fingerprints);
                    }
                    db.invoke("migratePack",new JSONArray().put(body.getJSONObject("manifest")).put(items),state);result=new JSONObject().put("ok",true);
                    if(body.optJSONObject("bank")!=null)state.put("bank",body.getJSONObject("bank"));
                }else if(path.equals("/api/mobile/snapshot")){JSONObject safe=new JSONObject(state.toString());safe.put("settings",settingsView(settings));result=safe;
                }else if(path.equals("/api/mobile/storage") || path.equals("/api/mobile/storage/clear-temp")){
                    File directory=db.media("unused-placeholder").getParentFile();long bytes=0,cleared=0;int count=0;
                    if(path.endsWith("clear-temp") && !GenerationService.running.isEmpty())throw new IllegalStateException("正在生成材料，完成后再清理临时文件");
                    File[] files=directory.listFiles();if(files!=null)for(File f:files){if(!f.isFile())continue;count++;bytes+=f.length();
                        if(path.endsWith("clear-temp") && (f.getName().endsWith(".pcm.tmp") || f.getName().endsWith(".encoded.tmp") || f.getName().endsWith(".pending.tmp"))){
                            if(!f.getCanonicalPath().startsWith(directory.getCanonicalPath()+File.separator))throw new IllegalStateException("临时文件路径异常");long size=f.length();if(f.delete())cleared+=size;}}
                    result=new JSONObject().put("media_bytes",bytes-cleared).put("media_files",count).put("cleared_bytes",cleared);
                }else if(path.equals("/api/voices")){result=new JSONArray(db.asset("public/static/voices.json"));
                }else if(path.equals("/api/mobile/voice-preview") && method.equals("POST")){
                    result=new JSONObject().put("path",preview.getAbsolutePath());
                }else if(path.equals("/api/mobile/import-draft") && method.equals("POST")){
                    String draft=body.getString("text");if(draft.length()>4*1024*1024)throw new IllegalArgumentException("导入文字过长，请分次导入");
                    db.writeMedia(new File(db.root(),"import-inbox.txt"),draft.getBytes(StandardCharsets.UTF_8));result=new JSONObject().put("ok",true);
                }else if(path.equals("/api/mobile/shared")){
                    boolean incoming=!sharedText.isEmpty();String text=sharedText;sharedText="";File inbox=new File(db.root(),"import-inbox.txt");
                    if(text.isEmpty() && inbox.isFile())try(java.io.FileInputStream in=new java.io.FileInputStream(inbox);java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream()){
                        byte[] bytes=new byte[8192];int n;while((n=in.read(bytes))!=-1)out.write(bytes,0,n);text=out.toString("UTF-8");}
                    result=new JSONObject().put("text",text).put("incoming",incoming);
                }else if(path.matches("/api/conversations/[^/]+/generate") && method.equals("POST")){
                    String cid=path.split("/")[3];if(!state.getJSONObject("conversations").has(cid))throw new IllegalArgumentException("聊天不存在");
                    if(GenerationService.running.contains(cid) && state.getJSONObject("jobs").optJSONObject(cid)!=null && state.getJSONObject("jobs").getJSONObject(cid).optString("state").equals("cancelled"))throw new IllegalStateException("任务仍在停止中，请稍后继续；已有成果保留");
                    JSONObject jobs=state.getJSONObject("jobs"),existing=jobs.optJSONObject(cid);
                    if(existing!=null && (existing.optString("state").equals("running") || existing.optString("state").equals("queued")))result=existing;
                    else {JSONObject job=existing==null?new JSONObject().put("id",cid).put("job_id",cid).put("kind","conversation").put("conversation_id",cid).put("created_at",LearningStore.now()):existing;
                        job.put("state","queued").put("errors",new JSONArray());jobs.put(cid,job);result=job;}
                    db.write(state);startTask(cid);
                }else if(path.matches("/api/jobs/[^/]+/resume") && method.equals("POST")){
                    JSONObject job=state.getJSONObject("jobs").getJSONObject(path.split("/")[3]);if(GenerationService.running.contains(job.getString("id")))throw new IllegalStateException("任务仍在停止中，请稍后继续；已有成果保留");job.put("state","queued");db.write(state);startTask(job.getString("id"));result=job;
                }else{
                    result=new org.json.JSONTokener(String.valueOf(db.invoke("route",new JSONArray().put(method).put(path).put(body).put(LearningStore.now()).put(db.bank(state)),state))).nextValue();
                    if((path.equals("/api/generation-requests") || path.endsWith("/study/prepare")) && method.equals("POST")){db.write(state);startTask(((JSONObject)result).getString("job_id"));}
                }
                if(!method.equals("GET") || path.equals("/api/conversations/import-link"))db.write(state);
                if((path.equals("/api/conversations/import") || path.equals("/api/conversations/import-link")) && method.equals("POST"))new File(db.root(),"import-inbox.txt").delete();
                call.resolve(new JSObject().put("value",result));
            }
        }catch(Exception e){call.reject(safeError(e));}
    });}
    private String safeError(Exception e){String message=e.getMessage();return message==null?"本机处理失败，原始记录仍保留":message.replaceAll("(?i)(Bearer\\s+|sk-)[^\\s\"']+","[redacted]");}
    private void startTask(String id){Intent i=new Intent(getContext(),GenerationService.class).putExtra("job_id",id);
        androidx.core.content.ContextCompat.startForegroundService(getContext(),i);}
    @PluginMethod public void recordStart(PluginCall call){
        if(getPermissionState("microphone")!=com.getcapacitor.PermissionState.GRANTED){requestPermissionForAlias("microphone",call,"microphoneGranted");return;}startRecording(call);
    }
    @PermissionCallback private void microphoneGranted(PluginCall call){if(getPermissionState("microphone")==com.getcapacitor.PermissionState.GRANTED)startRecording(call);else call.reject("麦克风未授权，可以不录音继续");}
    private void startRecording(PluginCall call){try{
        if(recorder!=null)throw new IllegalStateException("已有录音正在进行");recording=store().media("record-"+java.util.UUID.randomUUID()+".m4a");
        recordingSource=call.getObject("source",new JSObject());
        recorder=new MediaRecorder();recorder.setAudioSource(MediaRecorder.AudioSource.MIC);recorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
        recorder.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);recorder.setAudioSamplingRate(24000);recorder.setAudioChannels(1);recorder.setOutputFile(recording.getAbsolutePath());
        recorder.prepare();recorder.start();recordingStarted=android.os.SystemClock.elapsedRealtime();call.resolve();
    }catch(Exception e){if(recorder!=null){recorder.release();recorder=null;}call.reject("录音启动失败，可以不录音继续");}}
    @PluginMethod public void recordStop(PluginCall call){try{call.resolve(stopRecording(false));}catch(Exception e){call.reject("录音太短或未能保存，请重新录制");}}
    private JSObject stopRecording(boolean interrupted)throws Exception{
        if(recorder==null)throw new IllegalStateException("没有正在录制");try{recorder.stop();}finally{recorder.release();recorder=null;}
        JSObject out=new JSObject().put("path",recording.getAbsolutePath()).put("duration_sec",(android.os.SystemClock.elapsedRealtime()-recordingStarted)/1000.0).put("interrupted",interrupted).put("source",recordingSource);
        synchronized(LearningStore.LOCK){JSONObject s=store().read();s.put("pending_recording",new JSONObject(out.toString()));JSONObject inbox=s.optJSONObject("recording_inbox");if(inbox==null)inbox=new JSONObject();
            inbox.put(recording.getName(),new JSONObject(out.toString()));s.put("recording_inbox",inbox);store().write(s);}return out;
    }
    @Override protected void handleOnPause(){if(recorder!=null){try{notifyListeners("recordingInterrupted",stopRecording(true),true);}catch(Exception ignored){}}}
    @PluginMethod public void readRecording(PluginCall call){worker.execute(()->{try{
        File f=new File(call.getString("path",""));if(!f.getCanonicalPath().startsWith(store().root().getCanonicalPath()+File.separator))throw new IllegalArgumentException("录音路径不属于本机材料");
        try(java.io.FileInputStream in=new java.io.FileInputStream(f);java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream()){
            byte[] bytes=new byte[8192];int n;while((n=in.read(bytes))!=-1)out.write(bytes,0,n);
            call.resolve(new JSObject().put("base64",Base64.encodeToString(out.toByteArray(),Base64.NO_WRAP)));}
    }catch(Exception e){call.reject("录音读取失败，文件仍保留");}});}
    @PluginMethod public void exportDocument(PluginCall call){
        android.content.Intent intent=new android.content.Intent(android.content.Intent.ACTION_CREATE_DOCUMENT).addCategory(android.content.Intent.CATEGORY_OPENABLE);
        intent.setType(call.getString("mime","application/json"));intent.putExtra(android.content.Intent.EXTRA_TITLE,call.getString("name","personal-learning-exchange.json"));
        startActivityForResult(call,intent,"documentDestination");
    }
    @com.getcapacitor.annotation.ActivityCallback private void documentDestination(PluginCall call,androidx.activity.result.ActivityResult result){
        if(call==null)return;if(result.getResultCode()!=android.app.Activity.RESULT_OK || result.getData()==null){call.reject("已取消导出，原始材料仍保留");return;}
        worker.execute(()->{try(java.io.OutputStream out=getContext().getContentResolver().openOutputStream(result.getData().getData())){
            String path=call.getString("path","");
            if(!path.isEmpty()){File f=new File(path);if(!f.isFile() || !f.getCanonicalPath().startsWith(store().root().getCanonicalPath()+File.separator))throw new IllegalArgumentException("文件不属于本机材料");
                try(java.io.FileInputStream in=new java.io.FileInputStream(f)){byte[] b=new byte[32768];int n;while((n=in.read(b))!=-1)out.write(b,0,n);}}
            else out.write(call.getString("data","").getBytes(StandardCharsets.UTF_8));call.resolve();
        }catch(Exception e){call.reject("文件导出失败，本机原件仍保留");}});
    }
    @PluginMethod public void reminderPermission(PluginCall call){
        if(android.os.Build.VERSION.SDK_INT<33 || getPermissionState("notifications")==com.getcapacitor.PermissionState.GRANTED){call.resolve();return;}
        requestPermissionForAlias("notifications",call,"notificationGranted");
    }
    @PermissionCallback private void notificationGranted(PluginCall call){
        if(getPermissionState("notifications")==com.getcapacitor.PermissionState.GRANTED)call.resolve();else call.reject("提醒通知未授权，仍可随时打开今日练习");
    }
    @PluginMethod public void attachRecording(PluginCall call){worker.execute(()->{try{
        synchronized(LearningStore.LOCK){JSONObject s=store().read(),body=call.getObject("body",new JSObject());String path=call.getString("path","");
            File f=new File(path);if(!f.isFile() || !f.getCanonicalPath().startsWith(store().root().getCanonicalPath()+File.separator))throw new IllegalArgumentException("录音文件不存在");
            String rid=f.getName();body.put("id",rid).put("path",path).put("mime_type","audio/mp4");
            Object result;
            String sid=body.optString("session_id","");
                if(!sid.isEmpty()){JSONObject session=s.getJSONObject("sessions").getJSONObject(sid);
                    JSONObject pending=s.optJSONObject("recording_inbox")==null?null:s.getJSONObject("recording_inbox").optJSONObject(rid);
                    if(pending!=null){JSONObject source=pending.optJSONObject("source");if(source!=null && (!source.optString("session_id").equals(sid) || !source.optString("card_id").equals(session.getJSONArray("cards").optString(session.optInt("current_index")))))throw new IllegalStateException("录音属于之前的句子，可以导出；不会绑定到当前口答");}
                    if(!session.optString("state").equals("active"))throw new IllegalStateException("原口答轮次已结束，可以导出这段录音");
                    session.put("recording_id",path).put("responded",true).put("answer_visible",true);
                result=new JSONObject().put("session",new org.json.JSONTokener(String.valueOf(store().invoke("publicSession",new JSONArray().put(sid),s))).nextValue());}
            else result=new org.json.JSONTokener(String.valueOf(store().invoke("route",new JSONArray().put("POST").put(call.getString("url")).put(body).put(LearningStore.now()).put(store().bank(s)),s))).nextValue();
            if(s.optJSONObject("recording_inbox")!=null)s.getJSONObject("recording_inbox").remove(rid);
            s.remove("pending_recording");store().write(s);call.resolve(new JSObject().put("value",result));
        }
    }catch(Exception e){call.reject(safeError(e));}});}
}
