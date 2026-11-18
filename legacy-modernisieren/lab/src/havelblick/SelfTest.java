package havelblick;
import havelblick.core.*;
import havelblick.legacy.*;
import havelblick.pricing.*;
import java.math.*;
import java.time.*;
import java.sql.*;
import java.util.*;
public final class SelfTest {
  public static void main(String[]args)throws Exception{
    int checked=0,wrong=0;
    for(String unit:List.of("19.995","7.125","49.995"))for(int q=1;q<=20;q++)for(String group:List.of("STANDARD","TREUE","PARTNER")){
      var u=new BigDecimal(unit);
      var old=LegacyPrice.quote(u,q,group);
      var good=PriceRules.quote(u,q,group);
      if(!old.equals(good))throw new AssertionError("characterization mismatch");
      if(!old.equals(PriceRules.failedEarlyRounding(u,q,group)))wrong++;
      checked++;
    }
    var p=PriceRules.quote(new BigDecimal("19.995"),3,"TREUE");
    if(p.total_cents()!=6782||p.subtotal_cents()!=5999||p.discount_cents()!=300)throw new AssertionError("golden");
    Ports.TimeSource fixed=()->Instant.parse("2026-01-15T09:30:00Z"),real=Instant::now;
    if(!fixed.now().toString().equals("2026-01-15T09:30:00Z")||Duration.between(real.now(),Instant.now()).abs().getSeconds()>1)throw new AssertionError("clock seam");
    int[] calls={
      0
    }
    ;
    Ports.Store observing=()->{
      calls[0]++;
      return Db.open();
    }
    ;
    Ports.Payment never=(k,o,a,m,r)->{
      throw new AssertionError("quote must not call payment");
    }
    ;
    var service=new OrderService("01-price",fixed,never,observing);
    var quote=service.quote("WARTUNG",3,"TREUE");
    if(!quote.get("total_cents").equals(6782L)||calls[0]!=1)throw new AssertionError("persistence seam");
    boolean storeFailure=false;
    Ports.Store failed=()->{
      throw new SQLException("deliberate persistence seam");
    }
    ;
    try{
      new OrderService("01-price",fixed,never,failed).quote("WARTUNG",3,"TREUE");
    }
    catch(SQLException e){
      storeFailure=true;
    }
    if(!storeFailure)throw new AssertionError("store failure hidden");
    var narrowA=new HashMap<String,Object>(quote);
    var narrowB=new HashMap<String,Object>(quote);
    narrowB.put("total_cents",6783L);
    boolean narrowDetects=!narrowA.equals(narrowB);
    narrowA.keySet().removeIf(k->k.endsWith("_cents"));
    narrowB.keySet().removeIf(k->k.endsWith("_cents"));
    boolean broadHides=narrowA.equals(narrowB);
    if(!narrowDetects||!broadHides||wrong==0)throw new AssertionError("counterexample");
    boolean badDoubleRejected=false;
    try{
      PaymentResponseContract.reference(200,Map.of("outcome","SUCCESS","id","dummy"),6782);
    }
    catch(Remote.Failure e){
      badDoubleRejected=e.status==502;
    }
    if(!badDoubleRejected)throw new AssertionError("unrealistic payment double");
    System.out.println(Json.text(Map.of("unrealistic_payment_double_rejected",badDoubleRejected,"characterization_cases",checked,"failed_extraction_divergences",wrong,"golden_total_cents",p.total_cents(),"fixed_clock",fixed.now().toString(),"real_clock_checked",true,"real_persistence_seam_calls",calls[0],"injected_store_failure_detected",storeFailure,"narrow_normalizer_detects_money_change",narrowDetects,"broad_normalizer_hides_money_change",broadHides)));
  }
}
