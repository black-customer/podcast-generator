package com.bruce.ieltspod;

import android.app.AlarmManager;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import androidx.core.app.NotificationCompat;
import org.json.JSONObject;

/** 可选每日提醒仅通知真实到期内容，不要求精确闹钟权限。 */
public final class ReviewReminder extends BroadcastReceiver {
    static void schedule(Context app,boolean enabled){
        AlarmManager manager=(AlarmManager)app.getSystemService(Context.ALARM_SERVICE);
        PendingIntent action=PendingIntent.getBroadcast(app,51,new Intent(app,ReviewReminder.class),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        manager.cancel(action);if(!enabled)return;
        java.util.Calendar time=java.util.Calendar.getInstance();time.set(java.util.Calendar.HOUR_OF_DAY,20);time.set(java.util.Calendar.MINUTE,0);time.set(java.util.Calendar.SECOND,0);
        if(time.getTimeInMillis()<=System.currentTimeMillis())time.add(java.util.Calendar.DAY_OF_MONTH,1);
        manager.setInexactRepeating(AlarmManager.RTC_WAKEUP,time.getTimeInMillis(),AlarmManager.INTERVAL_DAY,action);
    }
    @Override public void onReceive(Context app,Intent intent){PendingResult pending=goAsync();new Thread(()->{try{synchronized(LearningStore.LOCK){
        LearningStore db=new LearningStore(app);JSONObject s=db.read();if(!s.getJSONObject("settings").optBoolean("reminder_enabled",false))return;
        String day=LearningStore.now().substring(0,10);JSONObject cards=s.getJSONObject("cards");int due=0;
        for(java.util.Iterator<String> keys=cards.keys();keys.hasNext();){JSONObject c=cards.getJSONObject(keys.next());if(!c.optBoolean("paused") && !c.optBoolean("superseded") && c.optString("due_date").compareTo(day)<=0)due++;}
        if(due==0)return;NotificationManager manager=(NotificationManager)app.getSystemService(Context.NOTIFICATION_SERVICE);
        if(android.os.Build.VERSION.SDK_INT>=26)manager.createNotificationChannel(new NotificationChannel("review","复习提醒",NotificationManager.IMPORTANCE_DEFAULT));
        PendingIntent open=PendingIntent.getActivity(app,51,new Intent(app,MainActivity.class),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        manager.notify(51,new NotificationCompat.Builder(app,"review").setSmallIcon(android.R.drawable.ic_menu_edit).setContentTitle("今天的英语复习")
            .setContentText(due+" 个学习点到期，每轮最多 10 个。").setContentIntent(open).setAutoCancel(true).build());
    }}catch(Exception ignored){}finally{pending.finish();}}).start();}
}
