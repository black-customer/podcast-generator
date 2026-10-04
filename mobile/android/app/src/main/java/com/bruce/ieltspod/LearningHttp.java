package com.bruce.ieltspod;

import java.net.URL;
import javax.net.ssl.HttpsURLConnection;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

/** 请求不记录响应正文；错误只暴露状态码，避免第三方回显凭据。 */
final class LearningHttp {
    interface Transport { byte[] request(String address,JSONObject body)throws Exception; }
    static volatile Transport testTransport;
    static volatile java.net.Proxy testProxy;
    static byte[] request(String address,JSONObject body,String key) throws Exception {
        return request(address,body,key,0);
    }
    private static byte[] request(String address,JSONObject body,String key,int redirects) throws Exception {
        if(redirects>4)throw new IllegalStateException("分享链接跳转次数过多，请导入文件");
        if(BuildConfig.DEBUG && LearningStore.testRoot!=null && testTransport!=null)return testTransport.request(address,body);
        URL url=new URL(address);if(!url.getProtocol().equals("https"))throw new IllegalArgumentException("API 仅支持 HTTPS");
        HttpsURLConnection c=(HttpsURLConnection)(BuildConfig.DEBUG && testProxy!=null?url.openConnection(testProxy):url.openConnection());c.setConnectTimeout(20000);c.setReadTimeout(120000);c.setInstanceFollowRedirects(false);
        c.setRequestProperty("User-Agent","Mozilla/5.0 IELTS-Pod/1.1");
        if(key!=null && !key.isEmpty())c.setRequestProperty("Authorization","Bearer "+key);
        if(body!=null){c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("Content-Type","application/json");
            try(java.io.OutputStream out=c.getOutputStream()){out.write(body.toString().getBytes(StandardCharsets.UTF_8));}}
        int status=c.getResponseCode();
        if(status>=300 && status<400 && body==null){String next=c.getHeaderField("Location");c.disconnect();URL target=new URL(url,next);
            if(!target.getHost().equals(url.getHost()))throw new IllegalStateException("分享链接跳转到了其他站点，请导入文件");
            return request(target.toString(),null,null,redirects+1);}
        if(status<200 || status>=300){c.disconnect();throw new IllegalStateException("服务返回 HTTP "+status+"，请检查配置或稍后手动重试");}
        try(InputStream in=c.getInputStream();ByteArrayOutputStream out=new ByteArrayOutputStream()){
            byte[] b=new byte[32768];int n,total=0;while((n=in.read(b))!=-1){total+=n;if(total>64*1024*1024)throw new IllegalStateException("响应超过本次处理上限，请分次导入");out.write(b,0,n);}return out.toByteArray();
        }finally{c.disconnect();}
    }
    static JSONObject json(String url,JSONObject body,String key)throws Exception{return new JSONObject(new String(request(url,body,key),StandardCharsets.UTF_8));}
}
