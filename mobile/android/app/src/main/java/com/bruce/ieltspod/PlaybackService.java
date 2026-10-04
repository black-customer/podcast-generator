package com.bruce.ieltspod;

import androidx.media3.common.AudioAttributes;
import androidx.media3.common.C;
import androidx.media3.common.Player;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.session.MediaSession;
import androidx.media3.session.MediaSessionService;
import org.json.JSONObject;
import android.os.Handler;
import android.os.Looper;

/** 原生媒体会话负责音频焦点与锁屏控制，进度也不依赖 WebView。 */
public final class PlaybackService extends MediaSessionService {
    private MediaSession session;
    private ExoPlayer player;
    private final java.util.Set<String> played=new java.util.HashSet<>();
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final Runnable saveTick=new Runnable(){public void run(){savePosition();handler.postDelayed(this,5000);}};
    @Override public void onCreate(){super.onCreate();player=new ExoPlayer.Builder(this).build();
        player.setAudioAttributes(new AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_SPEECH).build(),true);
        player.setHandleAudioBecomingNoisy(true);session=new MediaSession.Builder(this,player).build();
        player.addListener(new Player.Listener(){@Override public void onIsPlayingChanged(boolean playing){if(playing && player.getCurrentMediaItem()!=null)played.add(player.getCurrentMediaItem().mediaId);savePosition();}});handler.post(saveTick);}
    private void savePosition(){if(player==null || player.getCurrentMediaItem()==null)return;
        String path=player.getCurrentMediaItem().mediaId;double position=player.getCurrentPosition()/1000.0;boolean completed=player.getPlaybackState()==Player.STATE_ENDED;
        android.os.Bundle extras=player.getCurrentMediaItem().mediaMetadata.extras;String fingerprint=extras==null?"":extras.getString("fingerprint","");
        String title=String.valueOf(player.getCurrentMediaItem().mediaMetadata.title);
        if(path.isEmpty() || !played.contains(path))return;new Thread(()->{try{synchronized(LearningStore.LOCK){LearningStore db=new LearningStore(this);JSONObject s=db.read();
            JSONObject record=new JSONObject().put("path",path).put("position",position).put("completed",completed).put("fingerprint",fingerprint).put("title",title);
            JSONObject positions=s.optJSONObject("media_positions");if(positions==null)positions=new JSONObject();positions.put(path,record);s.put("media_positions",positions);
            s.put("native_playback",record);db.write(s);}}
            catch(Exception ignored){}}).start();}
    @Override public MediaSession onGetSession(MediaSession.ControllerInfo info){return session;}
    @Override public void onDestroy(){handler.removeCallbacks(saveTick);if(session!=null)session.release();if(player!=null)player.release();super.onDestroy();}
}
