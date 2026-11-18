package havelblick.modern;
import java.util.*;
import havelblick.core.*;
/** Boundary translation is explicit; neither protocol silently accepts the other's field names. */
public final class CompatibilityAdapter {
  public static Map<String,Object> fromV2(Map<String,Object>v){
    Map<String,Object>m=new LinkedHashMap<>();
    m.put("request_id",Json.string(v,"idempotency_key"));
    m.put("sku",Json.string(v,"product_code"));
    m.put("quantity",Json.number(v,"units"));
    m.put("customer_group",Json.string(v,"segment"));
    if(v.containsKey("payment_mode"))m.put("payment_mode",v.get("payment_mode"));
    return m;
  }
  public static Map<String,Object> toV2(Map<String,Object>v){
    return Map.of("id",v.get("order_id"),"state",v.get("status"),"amount",Map.of("currency","EUR","minor_units",v.get("total_cents")),"created_at",v.get("created_at"));
  }
}
