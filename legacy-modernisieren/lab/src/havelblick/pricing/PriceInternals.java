package havelblick.pricing;
import java.math.BigDecimal;
/** Intentionally package-private; consumers depend only on PriceRules. */
final class PriceInternals {
  static long cents(BigDecimal value){
    return value.movePointRight(2).longValueExact();
  }
}
