package havelblick.shipping;
import havelblick.core.*;
import java.util.*;
/** One event per process, a real exit after remote commit is the crash seam.
* Holding the row lock through delivery is deliberately simple and limits throughput. */
public final class OutboxWorker {
  public static void main(String[]args)throws Exception{
    boolean crash=Arrays.asList(args).contains("--crash-after-send");
    try(var c=Db.open()){
      c.setAutoCommit(false);
      var events=Db.rows(c,"SELECT * FROM ops.outbox WHERE state='PENDING' ORDER BY created_at,event_id LIMIT 1");
      if(events.isEmpty()){
        c.commit();
        System.out.println(Json.text(Map.of("state","IDLE")));
        return;
      }
      var e=events.getFirst();
      String id=e.get("event_id").toString();
      String owner=e.get("backend").toString();
      if(!Set.of("legacy","modern").contains(owner))throw new IllegalStateException("backend");
      // Same order->outbox lock ordering as cancellation; re-read after obtaining locks.
      var orders=Db.rows(c,"SELECT status FROM "+owner+".orders WHERE order_id=? FOR UPDATE",e.get("order_id"));
      var locked=Db.rows(c,"SELECT * FROM ops.outbox WHERE event_id=? AND state='PENDING' FOR UPDATE SKIP LOCKED",id);
      if(locked.isEmpty()){
        c.commit();
        System.out.println(Json.text(Map.of("state","IDLE")));
        return;
      }
      if(!orders.isEmpty()&&orders.getFirst().get("status").equals("CANCELLED")){
        Db.exec(c,"UPDATE ops.outbox SET state='CANCELLED' WHERE event_id=?",id);
        c.commit();
        return;
      }
      Db.exec(c,"UPDATE ops.outbox SET attempts=attempts+1 WHERE event_id=?",id);
      if(!e.get("kind").equals("ORDER_READY")){
        Db.exec(c,"UPDATE ops.outbox SET state='POISON',last_error='UNSUPPORTED_KIND' WHERE event_id=?",id);
        c.commit();
        System.out.println(Json.text(Map.of("state","POISON","event_id",id)));
        return;
      }
      var reply=new Remote().dispatch(id,e.get("order_id").toString(),((Number)e.get("total_cents")).longValue());
      if(reply.status()!=200){
        Db.exec(c,"UPDATE ops.outbox SET last_error='REMOTE_CONFLICT' WHERE event_id=?",id);
        c.commit();
        System.out.println(Json.text(Map.of("state","RETRY","http",reply.status())));
        return;
      }
      if(crash){
        System.out.flush();
        System.err.println("INTENTIONAL_PROCESS_EXIT_AFTER_REMOTE_COMMIT");
        System.exit(70);
      }
      String backend=e.get("backend").toString();
      if(!Set.of("legacy","modern").contains(backend))throw new IllegalStateException("backend");
      Db.exec(c,"UPDATE "+backend+".orders SET status='SHIPPED' WHERE order_id=? AND status='AUTHORIZED'",e.get("order_id"));
      Db.exec(c,"UPDATE ops.outbox SET state='DELIVERED',delivered_at=now(),last_error=NULL WHERE event_id=?",id);
      c.commit();
      System.out.println(Json.text(Map.of("state","DELIVERED","event_id",id,"remote_duplicate",reply.body().get("duplicate"))));
    }
  }
}
