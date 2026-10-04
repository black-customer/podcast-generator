package com.bruce.ieltspod;

import org.junit.Test;
import java.io.File;
import java.io.FileOutputStream;
import static org.junit.Assert.*;

public final class LoudnessMeterTest {
    @Test public void referenceToneMatchesFfmpegEbur128() throws Exception {
        File pcm=File.createTempFile("loudness-reference-",".pcm");
        try(FileOutputStream out=new FileOutputStream(pcm)){
            for(int n=0;n<24000*4;n++){short sample=(short)Math.round(Math.sin(n*2*Math.PI*440/24000)*3276.7);
                out.write(sample & 255);out.write((sample>>>8)&255);}
        }
        try {assertEquals(-23.7,LoudnessMeter.integrated(pcm,24000),.15);}finally{pcm.delete();}
    }
    @Test public void silenceDoesNotReturnANormalizationGain() throws Exception {
        File pcm=File.createTempFile("loudness-silence-",".pcm");
        try(FileOutputStream out=new FileOutputStream(pcm)){out.write(new byte[24000]);}
        try{assertEquals(-100,LoudnessMeter.integrated(pcm,24000),0);}finally{pcm.delete();}
    }
}
