package havelblick.core;
import java.util.*;
import java.sql.*;
import java.math.*;
import havelblick.pricing.PriceRules;
import havelblick.legacy.LegacyPrice;
import static havelblick.core.Remote.Failure;
/** Transitional application flow. The legacy branch intentionally mixes SQL and remote work.
* New ownership is limited to order data; shared catalog/stock is an explicit remaining debt. */
public final class OrderService {
  private final String stage;
  private final Ports.TimeSource time;
  private final Ports.Payment payment;
  private final Ports.Store store;
  private final Ports.PriceSource prices;
  public OrderService(String stage,Ports.TimeSource time,Ports.Payment payment,Ports.Store store){
    this.stage=stage;
    this.time=stage.equals("00-legacy")?java.time.Instant::now:time;
    this.payment=stage.equals("00-legacy")?new Remote():payment;
    this.store=stage.equals("00-legacy")?Db::open:store;
    prices=stage.equals("00-legacy")?LegacyPrice::quote:stage.equals("01-price-attempt")?PriceRules::failedEarlyRounding:PriceRules::quote;
  }
  public Map<String,Object> quote(String sku,int qty,String group)throws Exception{
    try(var c=store.open()){
      var product=Db.rows(c,"SELECT unit_net FROM legacy.products WHERE sku=?",sku);
      if(product.isEmpty())throw new Failure(422,"UNKNOWN_PRODUCT");
      var p=prices.quote((BigDecimal)product.getFirst().get("unit_net"),qty,group);
      return amounts(p);
    }
  }
  private static Map<String,Object> amounts(PriceRules.Price p){
    return new LinkedHashMap<>(Map.of("subtotal_cents",p.subtotal_cents(),"discount_cents",p.discount_cents(),"net_cents",p.net_cents(),"tax_cents",p.tax_cents(),"total_cents",p.total_cents()));
  }
  public Map<String,Object> create(Map<String,Object> in,String backend)throws Exception{
    String key=Json.string(in,"request_id"),sku=Json.string(in,"sku"),group=Json.string(in,"customer_group");
    long q=Json.number(in,"quantity");
    if(!key.matches("[A-Za-z0-9_-]{1,50}")||q<1||q>20||!Set.of("STANDARD","TREUE","PARTNER").contains(group))throw new Failure(422,"INVALID_ORDER");
    int qty=(int)q;
    String fp=sku+":"+qty+":"+group,id="HB-"+key,table=backend+".orders";
    try(var c=store.open()){
      c.setAutoCommit(false);
      try{
        Db.rows(c,"SELECT pg_advisory_xact_lock_shared(20261118)");
        if(Db.control(c,"writes_frozen").equals("true"))throw new Failure(503,"WRITES_FROZEN");
        Db.rows(c,"SELECT pg_advisory_xact_lock(hashtext(?))",key);
        var existing=Db.rows(c,"SELECT * FROM "+table+" WHERE request_id=?",key);
        if(!existing.isEmpty()){
          if(!existing.getFirst().get("fingerprint").equals(fp))throw new Failure(409,"IDEMPOTENCY_CONFLICT");
          c.commit();
          return response(existing.getFirst(),backend);
        }
        String other=backend.equals("legacy")?"modern":"legacy";
        var across=Db.rows(c,"SELECT * FROM "+other+".orders WHERE request_id=?",key);
        if(!across.isEmpty())throw new Failure(409,"OTHER_OWNER");
        var products=Db.rows(c,"SELECT unit_net FROM legacy.products WHERE sku=?",sku);
        if(products.isEmpty())throw new Failure(422,"UNKNOWN_PRODUCT");
        var stock=Db.rows(c,"SELECT available FROM legacy.stock WHERE sku=? FOR UPDATE",sku);
        if(((Number)stock.getFirst().get("available")).intValue()<qty)throw new Failure(409,"OUT_OF_STOCK");
        var price=prices.quote((BigDecimal)products.getFirst().get("unit_net"),qty,group);
        String mode=Objects.toString(in.getOrDefault("payment_mode","ok"));
        String provider=payment.authorize("pay-"+key,id,price.total_cents(),mode,stage.compareTo("02-shipping")>=0);
        Db.exec(c,"UPDATE legacy.stock SET available=available-? WHERE sku=?",qty,sku);
        Db.exec(c,"INSERT INTO "+table+"(order_id,request_id,fingerprint,sku,quantity,customer_group,subtotal_cents,discount_cents,net_cents,tax_cents,total_cents,status,created_at,provider_ref) VALUES(?,?,?,?,?,?,?,?,?,?,?,'AUTHORIZED',?::timestamptz,?)",id,key,fp,sku,qty,group,price.subtotal_cents(),price.discount_cents(),price.net_cents(),price.tax_cents(),price.total_cents(),time.now().toString(),provider);
        if(stage.compareTo("02-shipping")>=0)Db.exec(c,"INSERT INTO ops.outbox(event_id,order_id,backend,total_cents) VALUES (?,?,?,?)","ship-"+key,id,backend,price.total_cents());
        Db.audit(c,"order-created",backend+":"+id);
        c.commit();
        if(stage.compareTo("02-shipping")<0){
          if(Boolean.TRUE.equals(in.get("fail_after_commit")))throw new Failure(503,"LEGACY_COMMIT_DISPATCH_GAP");
          var r=new Remote().dispatch("ship-"+key,id,price.total_cents());
          if(r.status()!=200)throw new Failure(502,"SHIPPING_CONTRACT");
          Db.exec(c,"UPDATE "+table+" SET status='SHIPPED' WHERE order_id=?",id);
          c.commit();
        }
        return get(id,backend);
      }
      catch(Exception e){
        c.rollback();
        throw e;
      }
    }
  }
  public Map<String,Object> get(String id,String backend)throws Exception{
    try(var c=store.open()){
      var rows=Db.rows(c,"SELECT * FROM "+backend+".orders WHERE order_id=?",id);
      if(rows.isEmpty())throw new Failure(404,"ORDER_NOT_FOUND");
      return response(rows.getFirst(),backend);
    }
  }
  public Map<String,Object> cancel(String id,String backend)throws Exception{
    try(var c=store.open()){
      c.setAutoCommit(false);
      try{
        Db.rows(c,"SELECT pg_advisory_xact_lock_shared(20261118)");
        if(Db.control(c,"writes_frozen").equals("true"))throw new Failure(503,"WRITES_FROZEN");
        var rows=Db.rows(c,"SELECT * FROM "+backend+".orders WHERE order_id=? FOR UPDATE",id);
        if(rows.isEmpty())throw new Failure(404,"ORDER_NOT_FOUND");
        var o=rows.getFirst();
        if(o.get("status").equals("SHIPPED"))throw new Failure(409,"ALREADY_SHIPPED");
        if(!o.get("status").equals("CANCELLED")){
          Db.exec(c,"UPDATE "+backend+".orders SET status='CANCELLED' WHERE order_id=?",id);
          Db.exec(c,"UPDATE legacy.stock SET available=available+? WHERE sku=?",o.get("quantity"),o.get("sku"));
          Db.exec(c,"UPDATE ops.outbox SET state='CANCELLED' WHERE order_id=? AND state='PENDING'",id);
        }
        c.commit();
        return get(id,backend);
      }
      catch(Exception e){
        c.rollback();
        throw e;
      }
    }
  }
  private static Map<String,Object> response(Map<String,Object>o,String backend){
    var m=new LinkedHashMap<>(o);
    m.remove("fingerprint");
    m.put("backend",backend);
    return m;
  }
  public String route(String key)throws Exception{
    if(!stage.equals("03-replacement"))return "legacy";
    try(var c=store.open()){
      if(Db.control(c,"retired").equals("true"))return "modern";
      int percent=Integer.parseInt(Db.control(c,"route_percent"));
      return Math.floorMod(key.hashCode(),100)<percent?"modern":"legacy";
    }
  }
  public Map<String,Object> shadow(Map<String,Object>in)throws Exception{
    var old=quote(Json.string(in,"sku"),(int)Json.number(in,"quantity"),Json.string(in,"customer_group"));
    var modern=PriceRules.quote(new BigDecimal(Json.string(in,"unit_net")),(int)Json.number(in,"quantity"),Json.string(in,"customer_group"));
    return Map.of("old",old,"new",amounts(modern),"equal",old.equals(amounts(modern)));
  }
}
