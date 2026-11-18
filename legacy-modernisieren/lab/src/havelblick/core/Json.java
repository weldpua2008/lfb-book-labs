package havelblick.core;
import java.util.*;
/** Small strict JSON codec for the bounded lab contract, not a production framework. */
public final class Json {
  private final String s;
  private int i;
  private Json(String s){
    this.s=s;
  }
  public static Object parse(String s){
    var p=new Json(s);
    Object o=p.value();
    p.ws();
    if(p.i!=s.length())throw new IllegalArgumentException("trailing JSON");
    return o;
  }
  @SuppressWarnings("unchecked") public static Map<String,Object> object(String s){
    Object o=parse(s);
    if(!(o instanceof Map))throw new IllegalArgumentException("object required");
    return (Map<String,Object>)o;
  }
  private void ws(){
    while(i<s.length()&&Character.isWhitespace(s.charAt(i)))i++;
  }
  private Object value(){
    ws();
    if(i>=s.length())throw new IllegalArgumentException("JSON EOF");
    char c=s.charAt(i);
    if(c=='"')return str();
    if(c=='{'){
      i++;
      Map<String,Object>m=new LinkedHashMap<>();
      ws();
      if(s.charAt(i)=='}'){
        i++;
        return m;
      }
      while(true){
        ws();
        String k=str();
        ws();
        take(':');
        if(m.containsKey(k))throw new IllegalArgumentException("duplicate key");
        m.put(k,value());
        ws();
        if(s.charAt(i)=='}'){
          i++;
          return m;
        }
        take(',');
      }
    }
    if(c=='['){
      i++;
      List<Object>a=new ArrayList<>();
      ws();
      if(s.charAt(i)==']'){
        i++;
        return a;
      }
      while(true){
        a.add(value());
        ws();
        if(s.charAt(i)==']'){
          i++;
          return a;
        }
        take(',');
      }
    }
    for(String l:List.of("true","false","null"))if(s.startsWith(l,i)){
      i+=l.length();
      return l.equals("null")?null:l.equals("true");
    }
    int b=i;
    if(c=='-')i++;
    while(i<s.length()&&Character.isDigit(s.charAt(i)))i++;
    if(b==i)throw new IllegalArgumentException("JSON token");
    return Long.parseLong(s.substring(b,i));
  }
  private void take(char c){
    if(i>=s.length()||s.charAt(i++)!=c)throw new IllegalArgumentException("expected "+c);
  }
  private String str(){
    take('"');
    StringBuilder b=new StringBuilder();
    while(i<s.length()){
      char c=s.charAt(i++);
      if(c=='"')return b.toString();
      if(c=='\\'){
        c=s.charAt(i++);
        switch(c){
          case '"','\\','/'->b.append(c);
          case 'n'->b.append('\n');
          case 'r'->b.append('\r');
          case 't'->b.append('\t');
          case 'b'->b.append('\b');
          case 'f'->b.append('\f');
          case 'u'->{
            b.append((char)Integer.parseInt(s.substring(i,i+4),16));
            i+=4;
          }
          default->throw new IllegalArgumentException("escape");
        }
      }
      else{
        if(c<32)throw new IllegalArgumentException("control character");
        b.append(c);
      }
    }
    throw new IllegalArgumentException("unterminated JSON");
  }
  public static String text(Object o){
    if(o==null)return "null";
    if(o instanceof Number||o instanceof Boolean)return o.toString();
    if(o instanceof Map<?,?>m){
      List<String>a=new ArrayList<>();
      m.forEach((k,v)->a.add(text(k.toString())+":"+text(v)));
      return "{"+String.join(",",a)+"}";
    }
    if(o instanceof Iterable<?>it){
      List<String>a=new ArrayList<>();
      it.forEach(v->a.add(text(v)));
      return "["+String.join(",",a)+"]";
    }
    String s=o.toString();
    StringBuilder b=new StringBuilder("\"");
    for(char c:s.toCharArray())switch(c){
      case '"'->b.append("\\\"");
      case '\\'->b.append("\\\\");
      case '\n'->b.append("\\n");
      case '\r'->b.append("\\r");
      case '\t'->b.append("\\t");
      default->{
        if(c<32)b.append(String.format("\\u%04x",(int)c));
        else b.append(c);
      }
    }
    return b.append('"').toString();
  }
  public static String string(Map<String,Object>m,String k){
    Object v=m.get(k);
    if(!(v instanceof String)||((String)v).isBlank())throw new IllegalArgumentException("string required: "+k);
    return (String)v;
  }
  public static long number(Map<String,Object>m,String k){
    Object v=m.get(k);
    if(!(v instanceof Number))throw new IllegalArgumentException("integer required: "+k);
    return ((Number)v).longValue();
  }
}
