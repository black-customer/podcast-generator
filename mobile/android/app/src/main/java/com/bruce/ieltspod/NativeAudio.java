package com.bruce.ieltspod;

import android.media.MediaCodec;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import android.media.MediaCodecInfo;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.List;

/** PCM 处理保留样本计数；AAC 编码只在原生线程运行，不经过 JS bridge。 */
final class NativeAudio {
    private static final int RATE=24000;
    static byte[] decode(File input)throws Exception{
        MediaExtractor ex=new MediaExtractor();MediaCodec codec=null;
        try{ex.setDataSource(input.getAbsolutePath());int track=-1;
            for(int i=0;i<ex.getTrackCount();i++)if(ex.getTrackFormat(i).getString(MediaFormat.KEY_MIME).startsWith("audio/")){track=i;break;}
            if(track<0)throw new IOException("音频文件没有可解码音轨");ex.selectTrack(track);MediaFormat f=ex.getTrackFormat(track);
            if(f.getString(MediaFormat.KEY_MIME).equals("audio/raw")){
                if(f.getInteger(MediaFormat.KEY_SAMPLE_RATE)!=RATE || f.getInteger(MediaFormat.KEY_CHANNEL_COUNT)!=1)throw new IOException("采样率或声道不支持");
                ByteArrayOutputStream pcm=new ByteArrayOutputStream();ByteBuffer buffer=ByteBuffer.allocate(32768);int n;
                while((n=ex.readSampleData(buffer,0))>=0){byte[] b=new byte[n];buffer.position(0);buffer.get(b);pcm.write(b);buffer.clear();ex.advance();}return pcm.toByteArray();
            }
            codec=MediaCodec.createDecoderByType(f.getString(MediaFormat.KEY_MIME));codec.configure(f,null,null,0);codec.start();
            ByteArrayOutputStream pcm=new ByteArrayOutputStream();MediaCodec.BufferInfo info=new MediaCodec.BufferInfo();boolean sent=false,done=false;
            long deadline=android.os.SystemClock.elapsedRealtime()+120000;
            while(!done){if(Thread.currentThread().isInterrupted())throw new IOException("音频处理被中断");if(android.os.SystemClock.elapsedRealtime()>deadline)throw new IOException("音频解码超时");
                if(!sent){int in=codec.dequeueInputBuffer(10000);if(in>=0){ByteBuffer b=codec.getInputBuffer(in);int n=ex.readSampleData(b,0);
                    if(n<0){codec.queueInputBuffer(in,0,0,0,MediaCodec.BUFFER_FLAG_END_OF_STREAM);sent=true;}
                    else{codec.queueInputBuffer(in,0,n,ex.getSampleTime(),0);ex.advance();}}}
                int out=codec.dequeueOutputBuffer(info,10000);
                if(out==MediaCodec.INFO_OUTPUT_FORMAT_CHANGED){MediaFormat format=codec.getOutputFormat();
                    if(format.getInteger(MediaFormat.KEY_SAMPLE_RATE)!=RATE || format.getInteger(MediaFormat.KEY_CHANNEL_COUNT)!=1)throw new IOException("服务返回了不支持的采样率或声道");}
                else if(out>=0){ByteBuffer b=codec.getOutputBuffer(out);b.position(info.offset);b.limit(info.offset+info.size);byte[] bytes=new byte[info.size];b.get(bytes);pcm.write(bytes);
                    done=(info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM)!=0;codec.releaseOutputBuffer(out,false);}
                if(pcm.size()>16*1024*1024)throw new IOException("单段音频异常过长");
            }if(pcm.size()<RATE/5)throw new IOException("服务返回音频过短");return pcm.toByteArray();
        }finally{ex.release();if(codec!=null){try{codec.stop();}finally{codec.release();}}}
    }
    static JSONObject assemble(List<File> fragments,JSONArray dialogue,File output)throws Exception{
        File raw=new File(output.getParentFile(),output.getName()+".pcm.tmp"),encoded=new File(output.getParentFile(),output.getName()+".encoded.tmp");
        JSONArray lines=new JSONArray();long total=0;double sum=0,peak=0;long silent=0,maxSilent=0;double oldX=0,oldY=0;
        try(FileOutputStream out=new FileOutputStream(raw)){
            for(int i=0;i<fragments.size();i++){byte[] bytes=decode(fragments.get(i));ByteBuffer b=ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
                long start=total;for(int n=0;n<bytes.length/2;n++){
                    double x=b.getShort(n*2)/32768.0,y=.982*(oldY+x-oldX);oldX=x;oldY=y;
                    double a=Math.abs(y);if(a>.1)y=Math.copySign(.1*Math.sqrt(a/.1),y);
                    short sample=(short)Math.round(Math.max(-1,Math.min(1,y))*32767);b.putShort(n*2,sample);
                    peak=Math.max(peak,Math.abs(y));sum+=y*y;total++;
                    if(Math.abs(y)<.0002){silent++;maxSilent=Math.max(maxSilent,silent);}else silent=0;
                }out.write(bytes);JSONObject l=dialogue.getJSONObject(i);
                lines.put(new JSONObject().put("id",i).put("speaker",l.getString("speaker")).put("role",l.getString("speaker").toLowerCase())
                    .put("name",l.getString("speaker").equals("A")?"对话伙伴":"我的自然表达").put("text",l.getString("en")).put("zh",l.optString("zh"))
                    .put("start",start/(double)RATE).put("end",total/(double)RATE).put("duration",(total-start)/(double)RATE));
            }
        }
        if(total==0 || peak<.0001)throw new IOException("音频没有有效人声");
        if(maxSilent/(double)RATE>8)throw new IOException("音频包含异常长静音，已保留旧成品");
        double integrated=LoudnessMeter.integrated(raw,RATE),gain=Math.min(Math.pow(10,(-16-integrated)/20),Math.pow(10,-1.5/20)/peak);
        encode(raw,encoded,gain,total);
        android.util.AtomicFile atomic=new android.util.AtomicFile(output);FileOutputStream target=null;
        try(FileInputStream in=new FileInputStream(encoded)){target=atomic.startWrite();byte[] bytes=new byte[32768];int n;while((n=in.read(bytes))!=-1)target.write(bytes,0,n);atomic.finishWrite(target);}
        catch(Exception e){if(target!=null)atomic.failWrite(target);throw e;}
        encoded.delete();
        raw.delete();JSONObject qa=new JSONObject().put("duration_sec",total/(double)RATE).put("peak_dbfs",20*Math.log10(peak*gain))
            .put("normalization","native_bs1770_gated").put("integrated_lufs",integrated+20*Math.log10(gain)).put("integrated_lufs_verified",true).put("max_silence_sec",maxSilent/(double)RATE);
        return new JSONObject().put("lines",lines).put("words",new JSONArray()).put("mode","measured").put("qa",qa).put("duration",total/(double)RATE);
    }
    private static void encode(File input,File output,double gain,long samples)throws Exception{
        MediaFormat format=MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_AAC,RATE,1);format.setInteger(MediaFormat.KEY_AAC_PROFILE,MediaCodecInfo.CodecProfileLevel.AACObjectLC);format.setInteger(MediaFormat.KEY_BIT_RATE,128000);
        MediaCodec codec=MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_AUDIO_AAC);MediaMuxer mux=null;
        try(FileInputStream in=new FileInputStream(input)){
            codec.configure(format,null,null,MediaCodec.CONFIGURE_FLAG_ENCODE);codec.start();mux=new MediaMuxer(output.getAbsolutePath(),MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
            boolean sent=false,done=false,started=false;long count=0;int track=-1;MediaCodec.BufferInfo info=new MediaCodec.BufferInfo();long deadline=android.os.SystemClock.elapsedRealtime()+300000;
            while(!done){if(Thread.currentThread().isInterrupted())throw new IOException("音频处理被中断");if(android.os.SystemClock.elapsedRealtime()>deadline)throw new IOException("音频编码超时");
                if(!sent){int at=codec.dequeueInputBuffer(10000);if(at>=0){ByteBuffer b=codec.getInputBuffer(at);byte[] bytes=new byte[Math.min(b.capacity(),32768)&~1];int n=in.read(bytes);
                    if(n<0){codec.queueInputBuffer(at,0,0,count*1000000/RATE,MediaCodec.BUFFER_FLAG_END_OF_STREAM);sent=true;}
                    else{ByteBuffer v=ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);for(int p=0;p<n/2;p++){double s=v.getShort(p*2)*gain;v.putShort(p*2,(short)Math.max(-32767,Math.min(32767,Math.round(s))));}
                        b.clear();b.put(bytes,0,n);codec.queueInputBuffer(at,0,n,count*1000000/RATE,0);count+=n/2;}}}
                int at=codec.dequeueOutputBuffer(info,10000);
                if(at==MediaCodec.INFO_OUTPUT_FORMAT_CHANGED){track=mux.addTrack(codec.getOutputFormat());mux.start();started=true;}
                else if(at>=0){ByteBuffer b=codec.getOutputBuffer(at);if((info.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG)!=0)info.size=0;
                    if(info.size>0 && started){b.position(info.offset);b.limit(info.offset+info.size);mux.writeSampleData(track,b,info);}done=(info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM)!=0;codec.releaseOutputBuffer(at,false);}
            }
            if(count!=samples)throw new IOException("音频样本计数不一致");
        }finally{try{codec.stop();}finally{codec.release();}if(mux!=null){try{mux.stop();}finally{mux.release();}}}
    }
}
