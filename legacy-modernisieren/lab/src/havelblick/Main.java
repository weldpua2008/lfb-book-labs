package havelblick;
import com.sun.net.httpserver.*;
import java.net.*;
import java.io.*;
import java.util.*;
import java.sql.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import havelblick.core.*;
import havelblick.modern.*;
import static havelblick.core.Remote.Failure;
public final class Main {
  static final String STAGE=System.getenv().getOrDefault("STAGE","00-legacy");
  static Map<String,String> query(String raw){
    Map<String,String>m=new HashMap<>();
    if(raw!=null)for(String pair:raw.split("&")){
      var p=pair.split("=",2);
      m.put(URLDecoder.decode(p[0],StandardCharsets.UTF_8),p.length==2?URLDecoder.decode(p[1],StandardCharsets.UTF_8):"");
    }
    return m;
  }
  static void json(HttpExchange x,int code,Object value)throws IOException{
    byte[]b=Json.text(value).getBytes(StandardCharsets.UTF_8);
    x.getResponseHeaders().set("Content-Type","application/json; charset=utf-8");
    x.sendResponseHeaders(code,b.length);
    x.getResponseBody().write(b);
    x.close();
  }
  static Map<String,Object> body(HttpExchange x)throws IOException{
    return Json.object(new String(x.getRequestBody().readNBytes(16384),StandardCharsets.UTF_8));
  }
  public static void main(String[]args)throws Exception{
    String role=args.length==0?"app":args[0];
    int port=role.equals("payment")?8081:role.equals("shipping")?8082:8080;
    var server=HttpServer.create(new InetSocketAddress("0.0.0.0",port),0);
    server.setExecutor(Executors.newFixedThreadPool(8));
    server.createContext("/",x->{
      try{
        if(x.getRequestURI().getPath().equals("/health")){
          json(x,200,Map.of("role",role,"stage",STAGE,"java",System.getProperty("java.runtime.version")));return;
        }
        if(role.equals("payment"))payment(x);else if(role.equals("shipping"))shipping(x);else app(x);
      }
      catch(Failure f){
        json(x,f.status,Map.of("error",f.code));
      }
      catch(IllegalArgumentException e){
        json(x,422,Map.of("error","INVALID_INPUT","detail",Objects.toString(e.getMessage(),"")));
      }
      catch(Exception e){
        e.printStackTrace();json(x,500,Map.of("error","INTERNAL","type",e.getClass().getSimpleName()));
      }
    }
    );
    server.start();
    System.out.println("Havelblick fictional lab role="+role+" stage="+STAGE+" port="+port);
  }
  static void payment(HttpExchange x)throws Exception{
    String path=x.getRequestURI().getPath();
    try(var c=Db.open()){
      if(path.equals("/authorization")&&x.getRequestMethod().equals("GET")){
        String key=query(x.getRequestURI().getRawQuery()).get("key");
        var r=Db.rows(c,"SELECT * FROM payment.authorizations WHERE key=?",key);
        if(r.isEmpty())throw new Failure(404,"UNKNOWN_KEY");
        var m=new LinkedHashMap<>(r.getFirst());
        m.put("outcome",m.remove("status"));
        json(x,200,m);
        return;
      }
      if(!path.equals("/authorize")||!x.getRequestMethod().equals("POST"))throw new Failure(404,"NOT_FOUND");
      var b=body(x);
      String key=Json.string(b,"key"),order=Json.string(b,"order_id"),mode=Json.string(b,"mode");
      long amount=Json.number(b,"amount_cents");
      if(amount<0)throw new Failure(422,"AMOUNT");
      c.setAutoCommit(false);
      Db.rows(c,"SELECT pg_advisory_xact_lock(hashtext(?))",key);
      var existing=Db.rows(c,"SELECT * FROM payment.authorizations WHERE key=?",key);
      if(!existing.isEmpty()){
        var o=existing.getFirst();
        if(((Number)o.get("amount_cents")).longValue()!=amount||!o.get("order_id").equals(order))throw new Failure(409,"KEY_CONFLICT");
        c.commit();
        json(x,200,Map.of("outcome",o.get("status"),"amount_cents",amount,"provider_ref",o.get("provider_ref")));
        return;
      }
      if(mode.equals("weird")){
        c.rollback();
        json(x,200,Map.of("outcome","QUEUED_ELSEWHERE"));
        return;
      }
      String status=mode.equals("decline")?"DECLINED":"AUTHORIZED",ref="AUTH-"+key;
      Db.exec(c,"INSERT INTO payment.authorizations VALUES(?,?,?,?,?)",key,order,amount,ref,status);
      c.commit();
      if(mode.equals("slow_ok"))Thread.sleep(600);
      if(mode.equals("drop_after_commit")){
        x.close();
        return;
      }
      if(mode.equals("unknown_once")){
        json(x,503,Map.of("outcome","UNKNOWN"));
        return;
      }
      json(x,200,Map.of("outcome",status,"amount_cents",amount,"provider_ref",ref));
    }
  }
  static void shipping(HttpExchange x)throws Exception{
    if(!x.getRequestURI().getPath().equals("/dispatch")||!x.getRequestMethod().equals("POST"))throw new Failure(404,"NOT_FOUND");
    var b=body(x);
    String event=Json.string(b,"event_id"),order=Json.string(b,"order_id");
    long amount=Json.number(b,"total_cents");
    try(var c=Db.open()){
      c.setAutoCommit(false);
      Db.rows(c,"SELECT pg_advisory_xact_lock(hashtext(?))",order);
      var rows=Db.rows(c,"SELECT * FROM shipping.dispatches WHERE event_id=? OR order_id=?",event,order);
      boolean duplicate=!rows.isEmpty();
      if(duplicate){
        var old=rows.getFirst();
        if(!old.get("event_id").equals(event)||!old.get("order_id").equals(order)||((Number)old.get("total_cents")).longValue()!=amount)throw new Failure(409,"EVENT_CONFLICT");
      }
      else Db.exec(c,"INSERT INTO shipping.dispatches(event_id,order_id,total_cents) VALUES(?,?,?)",event,order,amount);
      c.commit();
      json(x,200,Map.of("accepted",true,"duplicate",duplicate,"event_id",event));
    }
  }
  static void app(HttpExchange x)throws Exception{
    String path=x.getRequestURI().getPath(),method=x.getRequestMethod();
    var q=query(x.getRequestURI().getRawQuery());
    var service=new OrderService(STAGE,Ports.clock(),new Remote(),Db::open);
    if(path.equals("/v1/orders")&&method.equals("POST")){
      var b=body(x);
      json(x,200,service.create(b,service.route(Json.string(b,"request_id"))));
      return;
    }
    if(path.equals("/v2/orders")&&method.equals("POST")){
      if(!STAGE.equals("03-replacement"))throw new Failure(404,"NOT_AVAILABLE");
      json(x,200,CompatibilityAdapter.toV2(service.create(CompatibilityAdapter.fromV2(body(x)),"modern")));
      return;
    }
    if(path.startsWith("/v1/orders/")){
      String suffix=path.substring(11);
      boolean cancel=suffix.endsWith("/cancel");
      String allowed=cancel?"POST":"GET";
      if(!method.equals(allowed)){
        x.getResponseHeaders().set("Allow",allowed);
        throw new Failure(405,"METHOD_NOT_ALLOWED");
      }
      String id=cancel?suffix.substring(0,suffix.length()-7):suffix;
      String key=id.startsWith("HB-")?id.substring(3):id;
      String backend=service.route(key);
      json(x,200,cancel?service.cancel(id,backend):service.get(id,backend));
      return;
    }
    if(path.equals("/v2/quote")){
      json(x,200,service.quote(q.get("sku"),Integer.parseInt(q.getOrDefault("quantity","0")),q.get("customer_group")));
      return;
    }
    if(path.equals("/admin/shadow")){
      var b=body(x);
      boolean unsafe=q.getOrDefault("unsafe","false").equals("true");
      if(unsafe){
        var input=new LinkedHashMap<>(b);
        input.put("request_id","SHADOW-"+Json.string(b,"request_id"));
        json(x,200,service.create(input,"modern"));
      }
      else json(x,200,service.shadow(b));
      return;
    }
    if(path.equals("/legacy/report")||path.equals("/report")){
      try(var c=Db.open()){
        boolean old=path.equals("/legacy/report");
        if(old&&Db.control(c,"retired").equals("true"))throw new Failure(410,"LEGACY_RETIRED");
        String backend=old?"legacy":"modern",name=q.getOrDefault("consumer","nightly-export");
        Db.exec(c,"INSERT INTO ops.consumers(name,backend,calls) VALUES(?,?,1) ON CONFLICT(name) DO UPDATE SET backend=excluded.backend,calls=ops.consumers.calls+1",name,backend);
        Db.audit(c,old?"old-read":"new-read",name);
        var rows=Db.rows(c,"SELECT order_id,status,total_cents FROM "+backend+".orders ORDER BY order_id");
        StringBuilder csv=new StringBuilder("order_id,status,total_cents\n");
        for(var r:rows)csv.append(r.get("order_id")).append(',').append(r.get("status")).append(',').append(r.get("total_cents")).append('\n');
        json(x,200,Map.of("csv",csv.toString(),"backend",backend));
        return;
      }
    }
    if(path.startsWith("/admin/")){
      try(var c=Db.open()){
        String op=path.substring(7);
        var b=method.equals("POST")?body(x):new HashMap<String,Object>();
        switch(op){
          case "control"->{
            String key=Json.string(b,"key"),value=Json.string(b,"value");
            if(!Set.of("route_percent","writes_frozen","shadow").contains(key))throw new Failure(422,"CONTROL_KEY");
            if(key.equals("route_percent")&&(Integer.parseInt(value)<0||Integer.parseInt(value)>100))throw new Failure(422,"PERCENT");
            if(key.equals("writes_frozen")){c.setAutoCommit(false);Db.rows(c,"SELECT pg_advisory_xact_lock(20261118)");}
            Db.exec(c,"UPDATE ops.control SET value=? WHERE key=?",value,key);
            if(key.equals("writes_frozen"))c.commit();
            json(x,200,Map.of("key",key,"value",value));
          }
          case "migrate"->{
            int n=Db.exec(c,"INSERT INTO modern.orders SELECT * FROM legacy.orders ON CONFLICT(order_id) DO NOTHING");
            Db.audit(c,"backfill",Integer.toString(n));
            json(x,200,Map.of("copied",n));
          }
          case "reconcile"->{
            var diff=Db.rows(c,"SELECT coalesce(l.order_id,m.order_id) AS order_id FROM legacy.orders l FULL JOIN modern.orders m USING(order_id) WHERE l.order_id IS NULL OR m.order_id IS NULL OR (l.subtotal_cents,l.discount_cents,l.net_cents,l.tax_cents,l.total_cents,l.status,l.sku,l.quantity,l.customer_group,l.request_id,l.fingerprint,l.provider_ref) IS DISTINCT FROM (m.subtotal_cents,m.discount_cents,m.net_cents,m.tax_cents,m.total_cents,m.status,m.sku,m.quantity,m.customer_group,m.request_id,m.fingerprint,m.provider_ref)");
            json(x,200,Map.of("differences",diff,"equal",diff.isEmpty()));
          }
          case "rollback"->{
            if(!Db.control(c,"writes_frozen").equals("true"))throw new Failure(409,"FREEZE_REQUIRED");
            if(!Db.rows(c,"SELECT 1 FROM ops.outbox WHERE state='PENDING'").isEmpty())throw new Failure(409,"PENDING_DELIVERIES");
            c.setAutoCommit(false);
            Db.exec(c,"INSERT INTO legacy.orders SELECT * FROM modern.orders ON CONFLICT(order_id) DO UPDATE SET status=excluded.status,total_cents=excluded.total_cents,subtotal_cents=excluded.subtotal_cents,discount_cents=excluded.discount_cents,net_cents=excluded.net_cents,tax_cents=excluded.tax_cents,provider_ref=excluded.provider_ref");
            Db.exec(c,"UPDATE ops.control SET value='0' WHERE key='route_percent'");
            Db.audit(c,"rollback-reconciled","modern to legacy under freeze");
            c.commit();
            json(x,200,Map.of("route_percent",0,"target_writes_preserved",true));
          }
          case "consumer"->{
            String name=Json.string(b,"name"),backend=Json.string(b,"backend");
            if(!Set.of("legacy","modern").contains(backend))throw new Failure(422,"BACKEND");
            Db.exec(c,"UPDATE ops.consumers SET backend=? WHERE name=?",backend,name);
            json(x,200,Map.of("consumer",name,"backend",backend));
          }
          case "retire"->{
            if(!Db.rows(c,"SELECT 1 FROM ops.consumers WHERE backend='legacy'").isEmpty())throw new Failure(409,"LEGACY_CONSUMER");
            if(!Db.control(c,"route_percent").equals("100"))throw new Failure(409,"ROUTE_NOT_MIGRATED");
            Db.exec(c,"UPDATE ops.control SET value='true' WHERE key='retired'");
            Db.audit(c,"retired","known consumer inventory clear");
            json(x,200,Map.of("retired",true));
          }
          case "stats"->{
            Map<String,Object>out=new LinkedHashMap<>();
            for(String t:List.of("legacy.orders","modern.orders","ops.outbox","payment.authorizations","shipping.dispatches"))out.put(t,Db.rows(c,"SELECT count(*) AS n FROM "+t).getFirst().get("n"));
            out.put("stock",Db.rows(c,"SELECT * FROM legacy.stock ORDER BY sku"));
            out.put("control",Db.rows(c,"SELECT * FROM ops.control ORDER BY key"));
            out.put("consumers",Db.rows(c,"SELECT * FROM ops.consumers ORDER BY name"));
            json(x,200,out);
          }
          default->throw new Failure(404,"NOT_FOUND");
        }
        return;
      }
    }
    throw new Failure(404,"NOT_FOUND");
  }
}
