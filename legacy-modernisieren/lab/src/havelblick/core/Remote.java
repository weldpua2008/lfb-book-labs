package havelblick.core;
import java.net.*;
import java.net.http.*;
import java.time.*;
import java.util.*;
public final class Remote implements Ports.Payment {
  private final HttpClient client=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
  public record Reply(int status,Map<String,Object> body){
  }
  public Reply send(String url,Map<String,Object>body)throws Exception{
    var b=HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(3));
    if(body==null)b.GET();
    else b.header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString(Json.text(body)));
    var r=client.send(b.build(),HttpResponse.BodyHandlers.ofString());
    return new Reply(r.statusCode(),Json.object(r.body()));
  }
  public String authorize(String key,String order,long amount,String mode,boolean reconcile)throws Exception{
    String base=System.getenv().getOrDefault("PAYMENT_URL","http://payment:8081");
    Reply r;
    try{
      r=send(base+"/authorize",Map.of("key",key,"order_id",order,"amount_cents",amount,"mode",mode));
    }
    catch(java.io.IOException e){
      if(!reconcile)throw e;
      r=send(base+"/authorization?key="+URLEncoder.encode(key,java.nio.charset.StandardCharsets.UTF_8),null);
    }
    String outcome=Objects.toString(r.body().get("outcome"),"");
    if(outcome.equals("UNKNOWN")){
      if(reconcile)r=send(base+"/authorization?key="+URLEncoder.encode(key,java.nio.charset.StandardCharsets.UTF_8),null);
      else r=send(base+"/authorize",Map.of("key",key+"-retry","order_id",order,"amount_cents",amount,"mode","ok"));
      outcome=Objects.toString(r.body().get("outcome"),"");
    }
    if(outcome.equals("DECLINED"))throw new Failure(402,"PAYMENT_DECLINED");
    return PaymentResponseContract.reference(r.status(),r.body(),amount);
  }
  public Reply dispatch(String event,String order,long amount)throws Exception{
    return send(System.getenv().getOrDefault("SHIPPING_URL","http://shipping:8082")+"/dispatch",Map.of("event_id",event,"order_id",order,"total_cents",amount));
  }
  public static final class Failure extends RuntimeException{
    public final int status;
    public final String code;
    public Failure(int s,String c){
      super(c);
      status=s;
      code=c;
    }
  }
}
