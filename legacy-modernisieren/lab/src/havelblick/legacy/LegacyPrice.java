package havelblick.legacy;
import java.math.*;
import havelblick.pricing.PriceRules.Price;
/** Preserved old calculation; deliberately independent implementation for characterization. */
public final class LegacyPrice {
  public static Price quote(BigDecimal unit,int q,String g){
    if(q<1||q>20||!java.util.Set.of("STANDARD","TREUE","PARTNER").contains(g))throw new IllegalArgumentException("input");
    BigDecimal sum=unit.multiply(new BigDecimal(q)).setScale(2,RoundingMode.HALF_UP);
    BigDecimal discount=BigDecimal.ZERO;
    if(g.equals("TREUE")&&q>=3)discount=sum.multiply(new BigDecimal(".05"));
    if(g.equals("PARTNER")&&sum.compareTo(new BigDecimal("100"))>=0)discount=sum.multiply(new BigDecimal(".10"));
    discount=discount.setScale(2,RoundingMode.HALF_UP);
    BigDecimal net=sum.subtract(discount);
    BigDecimal vat=net.multiply(new BigDecimal(".19")).setScale(2,RoundingMode.HALF_UP);
    return new Price(sum.movePointRight(2).longValueExact(),discount.movePointRight(2).longValueExact(),net.movePointRight(2).longValueExact(),vat.movePointRight(2).longValueExact(),net.add(vat).movePointRight(2).longValueExact());
  }
}
