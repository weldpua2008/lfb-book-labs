package havelblick.pricing;
import java.math.*;
/** Pure extracted module: no SQL, clock, network or filesystem dependency. */
public final class PriceRules {
  public record Price(long subtotal_cents,long discount_cents,long net_cents,long tax_cents,long total_cents){
  }
  public static Price quote(BigDecimal unit,int quantity,String group){
    return calculate(unit,quantity,group,false);
  }
  public static Price failedEarlyRounding(BigDecimal unit,int quantity,String group){
    return calculate(unit,quantity,group,true);
  }
  private static Price calculate(BigDecimal unit,int q,String group,boolean early){
    if(q<1||q>20)throw new IllegalArgumentException("quantity");
    if(!java.util.Set.of("STANDARD","TREUE","PARTNER").contains(group))throw new IllegalArgumentException("customer_group");
    BigDecimal sub=(early?unit.setScale(2,RoundingMode.HALF_UP):unit).multiply(BigDecimal.valueOf(q)).setScale(2,RoundingMode.HALF_UP);
    BigDecimal rate=group.equals("TREUE")&&q>=3?new BigDecimal("0.05"):group.equals("PARTNER")&&sub.compareTo(new BigDecimal("100"))>=0?new BigDecimal("0.10"):BigDecimal.ZERO;
    BigDecimal discount=sub.multiply(rate).setScale(2,RoundingMode.HALF_UP),net=sub.subtract(discount),tax=net.multiply(new BigDecimal("0.19")).setScale(2,RoundingMode.HALF_UP);
    return new Price(cents(sub),cents(discount),cents(net),cents(tax),cents(net.add(tax)));
  }
  private static long cents(BigDecimal v){
    return PriceInternals.cents(v);
  }
}
