package havelblick.core;
import java.sql.*;
import java.util.*;
public final class Db {
  public static Connection open()throws SQLException{
    return DriverManager.getConnection(System.getenv("DB_URL"),System.getenv("DB_USER"),System.getenv("DB_PASSWORD"));
  }
  public static PreparedStatement prepare(Connection c,String q,Object...args)throws SQLException{
    var p=c.prepareStatement(q);
    for(int i=0;i<args.length;i++)p.setObject(i+1,args[i]);
    return p;
  }
  public static int exec(Connection c,String q,Object...a)throws SQLException{
    try(var p=prepare(c,q,a)){
      return p.executeUpdate();
    }
  }
  public static List<Map<String,Object>> rows(Connection c,String q,Object...a)throws SQLException{
    try(var p=prepare(c,q,a);var rs=p.executeQuery()){
      List<Map<String,Object>>out=new ArrayList<>();
      while(rs.next()){
        Map<String,Object>m=new LinkedHashMap<>();
        for(int j=1;j<=rs.getMetaData().getColumnCount();j++){
          Object v=rs.getObject(j);
          m.put(rs.getMetaData().getColumnLabel(j),v instanceof java.time.temporal.TemporalAccessor||v instanceof java.util.Date?v.toString():v);
        }
        out.add(m);
      }
      return out;
    }
  }
  public static String control(Connection c,String key)throws SQLException{
    return rows(c,"SELECT value FROM ops.control WHERE key=?",key).getFirst().get("value").toString();
  }
  public static void audit(Connection c,String a,String d)throws SQLException{
    exec(c,"INSERT INTO ops.audit(action,detail) VALUES (?,?)",a,d);
  }
}
