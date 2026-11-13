package edu.cs663.labellens.project2.pipeline;

import android.content.Context;
import android.graphics.Bitmap;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

/** Persist reproducible per-scan images/records and share an actual result archive. */
public final class ScanStore {
    public static File save(Context context,String id,JSONObject record,Map<String,Bitmap> images)throws Exception{
        File dir=createRecord(context,id,record);
        for(Map.Entry<String,Bitmap> image:images.entrySet())try(OutputStream out=new FileOutputStream(new File(dir,image.getKey()+".png"))){
            if(!image.getValue().compress(Bitmap.CompressFormat.PNG,100,out))throw new IOException("Cannot save scan image");
        }
        record.put("images_saved",true);writeRecord(dir,record);return dir;
    }
    public static File createRecord(Context context,String id,JSONObject record)throws Exception{
        File dir=new File(context.getFilesDir(),"scans/"+id);
        if(!dir.mkdirs()&&!dir.isDirectory())throw new IOException("Cannot create scan record");
        writeRecord(dir,record);return dir;
    }
    public static void writeRecord(File dir,JSONObject record)throws Exception{
        try(OutputStream out=new FileOutputStream(new File(dir,"scan.json"))){out.write(record.toString(2).getBytes(StandardCharsets.UTF_8));}
    }
    public static File export(Context context,File dir)throws IOException{
        File folder=new File(context.getCacheDir(),"exports");if(!folder.mkdirs()&&!folder.isDirectory())throw new IOException("Cannot create export");
        File zip=new File(folder,dir.getName()+".zip");
        try(ZipOutputStream out=new ZipOutputStream(new FileOutputStream(zip))){
            File[] files=dir.listFiles();if(files==null)throw new IOException("Scan record missing");
            for(File file:files){if(!file.isFile())continue;out.putNextEntry(new ZipEntry(file.getName()));try(InputStream in=new FileInputStream(file)){byte[] buffer=new byte[65536];int n;while((n=in.read(buffer))!=-1)out.write(buffer,0,n);}out.closeEntry();}
        }return zip;
    }
}
