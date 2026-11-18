package havelblick;
import havelblick.core.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.concurrent.*;
/** The forgotten batch consumer: a real scheduled HTTP reader with a file-output seam. */
public final class ReportJob {
  public interface ExportSink {
    void write(String csv)throws Exception;
  }
  public static void main(String[]args)throws Exception{
    String backend=args.length>0?args[0]:"legacy";
    Path path=Path.of(args.length>1?args[1]:"/tmp/havelblick-export.csv");
    int cycles=args.length>2?Integer.parseInt(args[2]):1;
    if(!Set.of("legacy","modern").contains(backend)||cycles<1||cycles>10)throw new IllegalArgumentException("report job args");
    ExportSink sink=csv->Files.writeString(path,csv);
    var executor=Executors.newSingleThreadScheduledExecutor();
    List<Map<String,Object>>runs=Collections.synchronizedList(new ArrayList<>());
    var latch=new CountDownLatch(cycles);
    var task=new Runnable(){
      public void run(){
        if(latch.getCount()==0)return;
        try{
          String route=backend.equals("legacy")?"/legacy/report":"/report";
          var reply=new Remote().send("http://127.0.0.1:8080"+route+"?consumer=nightly-export",null);
          if(reply.status()!=200)throw new IllegalStateException("report HTTP "+reply.status());
          String csv=Json.string(reply.body(),"csv");
          sink.write(csv);
          runs.add(Map.of("backend",backend,"bytes",csv.getBytes(java.nio.charset.StandardCharsets.UTF_8).length,"sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(csv.getBytes(java.nio.charset.StandardCharsets.UTF_8)))));
        }
        catch(Exception e){
          runs.add(Map.of("error",e.toString()));
        }
        finally{
          latch.countDown();
        }
      }
    }
    ;
    executor.scheduleAtFixedRate(task,0,100,TimeUnit.MILLISECONDS);
    if(!latch.await(15,TimeUnit.SECONDS))throw new IllegalStateException("job timeout");
    executor.shutdownNow();
    System.out.println(Json.text(Map.of("schedule_period_ms",100,"cycles",cycles,"file",path.toString(),"runs",runs)));
    if(runs.stream().anyMatch(r->r.containsKey("error")))System.exit(1);
  }
}
