package com.bruce.ieltspod;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.util.ArrayList;

/** BS.1770 单声道 K 加权与双门限整合响度；400ms 块、75% 重叠。 */
final class LoudnessMeter {
    private static final class Filter {
        final double b0,b1,b2,a1,a2;
        double x1,x2,y1,y2;
        Filter(double b0,double b1,double b2,double a1,double a2){this.b0=b0;this.b1=b1;this.b2=b2;this.a1=a1;this.a2=a2;}
        double apply(double x){double y=b0*x+b1*x1+b2*x2-a1*y1-a2*y2;x2=x1;x1=x;y2=y1;y1=y;return y;}
    }
    private static Filter shelf(int rate){double k=Math.tan(Math.PI*1681.974450955533/rate),q=.7071752369554196;
        double h=Math.pow(10,3.999843853973347/20),b=Math.pow(h,.4996667741545416),a0=1+k/q+k*k;
        return new Filter((h+b*k/q+k*k)/a0,2*(k*k-h)/a0,(h-b*k/q+k*k)/a0,2*(k*k-1)/a0,(1-k/q+k*k)/a0);}
    private static Filter highpass(int rate){double k=Math.tan(Math.PI*38.13547087602444/rate),q=.5003270373238773,a0=1+k/q+k*k;
        return new Filter(1,-2,1,2*(k*k-1)/a0,(1-k/q+k*k)/a0);}
    static double integrated(File pcm,int rate)throws IOException{
        int block=(int)(rate*.4),step=block/4;double[] ring=new double[block];double sum=0;long count=0;
        ArrayList<Double> energies=new ArrayList<>();Filter shelf=shelf(rate),hp=highpass(rate);
        try(FileInputStream in=new FileInputStream(pcm)){byte[] bytes=new byte[32768];int n;
            while((n=in.read(bytes))!=-1){if((n&1)!=0)throw new IOException("PCM 样本边界错误");
                for(int i=0;i<n;i+=2){short v=(short)((bytes[i]&255)|(bytes[i+1]<<8));double y=hp.apply(shelf.apply(v/32768.0)),energy=y*y;
                    int at=(int)(count%block);sum+=energy-ring[at];ring[at]=energy;count++;
                    if(count>=block && (count-block)%step==0)energies.add(Math.max(0,sum/block));}
            }
        }
        if(energies.isEmpty() && count>0)energies.add(sum/count);
        double absolute=0;int accepted=0;
        for(double e:energies)if(loudness(e)>=-70){absolute+=e;accepted++;}
        if(accepted==0)return -100;
        double relative=loudness(absolute/accepted)-10,total=0;accepted=0;
        for(double e:energies)if(loudness(e)>=-70 && loudness(e)>=relative){total+=e;accepted++;}
        return accepted>0?loudness(total/accepted):-100;
    }
    private static double loudness(double energy){return energy>0?-.691+10*Math.log10(energy):-100;}
}
