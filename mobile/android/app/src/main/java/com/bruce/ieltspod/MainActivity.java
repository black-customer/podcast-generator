package com.bruce.ieltspod;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override public void onCreate(android.os.Bundle state){registerPlugin(LearningPlugin.class);capture(getIntent());super.onCreate(state);
        androidx.core.view.WindowInsetsControllerCompat bars=androidx.core.view.WindowCompat.getInsetsController(getWindow(),getWindow().getDecorView());
        bars.setAppearanceLightStatusBars(true);bars.setAppearanceLightNavigationBars(true);}
    @Override protected void onNewIntent(android.content.Intent intent){super.onNewIntent(intent);setIntent(intent);capture(intent);}
    private void capture(android.content.Intent intent){if(intent==null)return;
        if(android.content.Intent.ACTION_SEND.equals(intent.getAction())){
            String text=intent.getStringExtra(android.content.Intent.EXTRA_TEXT);if(text!=null)saveInbox(text);
            android.net.Uri stream=intent.getParcelableExtra(android.content.Intent.EXTRA_STREAM);
            if(stream!=null)try(java.io.InputStream in=getContentResolver().openInputStream(stream);java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream()){
                byte[] b=new byte[8192];int n,total=0;while((n=in.read(b))!=-1){total+=n;if(total>4*1024*1024)throw new java.io.IOException("文件过大");out.write(b,0,n);}
                saveInbox(out.toString("UTF-8"));}catch(Exception ignored){LearningPlugin.sharedText="文件读取失败，请在 APP 内重新选择文件。";}
        }
    }
    private void saveInbox(String text){LearningPlugin.sharedText=text;try{LearningStore db=new LearningStore(this);
        db.writeMedia(new java.io.File(db.root(),"import-inbox.txt"),text.getBytes(java.nio.charset.StandardCharsets.UTF_8));}catch(Exception ignored){}}
}
