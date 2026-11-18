package havelblick.core;
import java.util.Map;
/** Applied both to actual provider replies and deliberately wrong test-double replies. */
public final class PaymentResponseContract {
  public static String reference(int status,Map<String,Object>body,long amount){
    if(status!=200||!"AUTHORIZED".equals(body.get("outcome"))||Json.number(body,"amount_cents")!=amount)throw new Remote.Failure(502,"PAYMENT_CONTRACT");
    return Json.string(body,"provider_ref");
  }
}
