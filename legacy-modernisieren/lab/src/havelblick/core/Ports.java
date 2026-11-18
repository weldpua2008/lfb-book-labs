package havelblick.core;
import java.time.*;
import java.util.*;
import java.sql.*;
import java.math.*;
import havelblick.pricing.PriceRules.Price;
public final class Ports {
  public interface TimeSource {
    Instant now();
  }
  public interface PriceSource {
    Price quote(BigDecimal unit,int quantity,String group);
  }
  public interface Payment {
    String authorize(String key,String order,long amount,String mode,boolean reconcile)throws Exception;
  }
  public interface Store {
    Connection open()throws SQLException;
  }
  public static TimeSource clock(){
    String fixed=System.getenv().getOrDefault("FIXED_TIME","");
    return fixed.isEmpty()?Instant::now:()->Instant.parse(fixed);
  }
}
