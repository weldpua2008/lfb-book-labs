#!/usr/bin/env python3
"""Executed synthetic scenarios, not simulated result fixtures. Requires Python stdlib only."""
import sys
if sys.flags.optimize:
 raise SystemExit('Scenario checks require Python without -O/-OO or PYTHONOPTIMIZE; no fixture action was started.')
import concurrent.futures,datetime,hashlib,json,os,pathlib,subprocess,time,urllib.request,urllib.error
ROOT=pathlib.Path(__file__).resolve().parents[1]
E=ROOT/'evidence';E.mkdir(exist_ok=True)
records=[];raw=[]
def cmd(*args,ok=True,input=None):
 p=subprocess.run(args,cwd=ROOT,text=True,input=input,capture_output=True,timeout=90)
 raw.append({'command':list(args),'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
 if ok and p.returncode: raise AssertionError(f'{args}: exit={p.returncode}: {p.stderr[-1500:]} {p.stdout[-1000:]}')
 return p

def sql(query):
 return cmd('docker','compose','exec','-T','db','psql','-X','-A','-t','-v','ON_ERROR_STOP=1','-U','hb_admin','-d','havelblick','-c',query).stdout.strip()

def api(path,data=None,port=18890,expect=None,method=None,allow=None):
 req=urllib.request.Request(f'http://127.0.0.1:{port}{path}',data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'},method=method)
 try:
  with urllib.request.urlopen(req,timeout=15) as r: code=r.status;value=json.load(r);allowed=r.headers.get("Allow")
 except urllib.error.HTTPError as e: code=e.code;value=json.loads(e.read());allowed=e.headers.get("Allow")
 raw.append({'http':path,'port':port,'method':req.get_method(),'request':data,'status':code,'allow':allowed,'response':value})
 if allow is not None: assert allowed==allow,(path,allowed,allow)
 if expect is not None: assert code==expect,(path,code,value,expect)
 return code,value

def ready(port=18890):
 for _ in range(80):
  try:
   if api('/health',port=port)[0]==200:return
  except (urllib.error.URLError,TimeoutError,ConnectionError):pass
  time.sleep(.15)
 raise AssertionError(f'health timeout:{port}')

def stage(s):
 cmd('./lab.sh','stage',s);ready();assert api('/health')[1]['stage']==s

def reset():cmd('./lab.sh','reset-data')
def ctl(k,v):return api('/admin/control',{'key':k,'value':str(v).lower()},expect=200)[1]
def order(key,sku='WARTUNG',q=3,g='TREUE',**kw):return {'request_id':key,'sku':sku,'quantity':q,'customer_group':g,**kw}
def worker(crash=False):return cmd('./lab.sh','worker',*(['--crash-after-send'] if crash else []),ok=False)
def drain():
 results=[]
 for _ in range(100):
  p=worker();assert p.returncode==0,p.stderr
  v=json.loads(p.stdout);results.append(v)
  if v.get('state')=='IDLE':return results
 raise AssertionError('outbox did not drain')
def report(backend,cycles=2,ok=True):
 return cmd('docker','compose','exec','-T','app','java','-Xmx96m','-cp','havelblick.jar:lib/*','havelblick.ReportJob',backend,'/tmp/havelblick-export.csv',str(cycles),ok=ok)

def check(id,title,chapters,expected,fn):
 start=time.monotonic()
 try:
  observed=fn();status='passed'
 except Exception as e:observed={'error':repr(e)};status='failed'
 rec={'id':id,'title':title,'chapters':chapters,'expected':expected,'observed':observed,'status':status,'elapsed_seconds':round(time.monotonic()-start,3)};records.append(rec)
 print(id,status,title,flush=True);save()
 return status=='passed'
def save():
 data={'executed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'synthetic':True,'company':'Havelblick Technikservice (fiction)','baseline':'Temurin21.0.13+9 / PostgreSQL18.7 / pgJDBC42.7.14','tests':records,'passed':sum(r['status']=='passed' for r in records),'failed':sum(r['status']=='failed' for r in records),'not_implemented':['real tax/payment/carrier integration','multi-line orders','production-scale throughput or availability proof','automatic provider void/refund after failure','multi-host network partitions','automatic discovery of arbitrary unregistered consumers','full Java security/framework validation','all concurrent cancellation/delivery interleavings']}
 (E/'results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');(E/'raw-events.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n')
 lines=['# Ausgeführte Laborproben – Havelblick Technikservice','','Synthetisches Labor; keine reale Kundenmigration. Details, Erwartungen und beobachtete Antworten in `results.json`; Befehle/HTTP in `raw-events.json`. Laufzeiten beschreiben nur diese Ausführung.','','| ID | Probe | Status | Kapitel |','|---|---|---|---|']
 for r in records:lines.append(f'| {r["id"]} | {r["title"]} | {r["status"]} | {", ".join(map(str,r["chapters"]))} |')
 lines += ['',f'Bestanden: {data["passed"]}; fehlgeschlagen: {data["failed"]}. Bekannte Baselinefehler werden als solche erwartet und bewiesen; ein bestandener Gegenbeispieltest macht sie nicht zu freigegebenem Sollverhalten.','','## Nicht implementierter oder nicht nachgewiesener Umfang','']+['- '+s for s in data['not_implemented']]
 (E/'results.md').write_text('\n'.join(lines)+'\n')

def build_repro():
 script="mkdir -p /tmp/rebuild; javac --release 21 -encoding UTF-8 -d /tmp/rebuild @sources.txt; jar --create --file /tmp/rebuild.jar --date=2026-11-18T00:00:00Z -C /tmp/rebuild .; sha256sum havelblick.jar /tmp/rebuild.jar"
 p=cmd('docker','compose','exec','-T','app','sh','-ec',script);lines=p.stdout.strip().splitlines();assert len(lines)==2 and lines[0].split()[0]==lines[1].split()[0],p.stdout
 return {'jar_hashes':lines,'build_tool':'javac/jar pinned in JDK image','host_java_used':False}
def selftest():return json.loads(cmd('docker','compose','exec','-T','app','java','-Xmx128m','-cp','havelblick.jar:lib/*','havelblick.SelfTest').stdout)
def architecture():
 code='import havelblick.pricing.PriceInternals; class BadBoundary { Object x = PriceInternals.class; }'
 p=cmd('docker','compose','exec','-T','app','sh','-ec',"mkdir -p /tmp/pure; javac --release 21 -d /tmp/pure src/havelblick/pricing/*.java; cat > /tmp/BadBoundary.java; javac -cp havelblick.jar /tmp/BadBoundary.java",ok=False,input=code)
 assert p.returncode!=0 and 'not public' in p.stderr,p.stderr
 assert not any(s in (ROOT/'src/havelblick/pricing/PriceRules.java').read_text() for s in ['java.sql','java.net','java.time','havelblick.core'])
 return {'pure_module_compiled_without_other_modules':True,'forbidden_import_compile_error':p.stderr}
def ownership():
 p=cmd('docker','compose','exec','-T','db','psql','-X','-v','ON_ERROR_STOP=1','-U','hb_admin','-d','havelblick','-c',"SET ROLE hb_app; INSERT INTO shipping.dispatches(event_id,order_id,total_cents) VALUES('forbidden','forbidden',1);",ok=False)
 assert p.returncode and 'permission denied' in p.stderr,p.stderr
 return {'forbidden_writer_exit':p.returncode,'error':p.stderr}
def baseline():
 reset();stage('00-legacy');_,o=api('/v1/orders',order('golden'),expect=200);assert o['total_cents']==6782 and o['status']=='SHIPPED',o
 _,again=api('/v1/orders',order('golden'),expect=200);assert o==again
 api('/v1/orders',order('golden',q=2),expect=409)
 for bad in [order('bad-qty',q=0),order('bad-group',g='VIP'),order('bad-sku',sku='NICHTDA')]:api('/v1/orders',bad,expect=422)
 api('/v2/orders',{'idempotency_key':'x','product_code':'WARTUNG','units':1,'segment':'STANDARD'},expect=404)
 return {'golden':o,'same_key_same_response':True,'invalid_variants_rejected':3,'v2_not_yet_deployed':True}
def legacy_defects():
 api('/v1/orders',order('ambiguous',q=1,payment_mode='unknown_once'),expect=200)
 pay=int(sql("SELECT count(*) FROM payment.authorizations WHERE order_id='HB-ambiguous'"));assert pay==2,pay
 api('/v1/orders',order('lost-dispatch',q=1,fail_after_commit=True),expect=503)
 orders=int(sql("SELECT count(*) FROM legacy.orders WHERE order_id='HB-lost-dispatch'"));ship=int(sql("SELECT count(*) FROM shipping.dispatches WHERE order_id='HB-lost-dispatch'"));outbox=int(sql("SELECT count(*) FROM ops.outbox WHERE order_id='HB-lost-dispatch'"));assert (orders,ship,outbox)==(1,0,0)
 job=json.loads(report('legacy').stdout);assert len(job['runs'])==2
 return {'scheduled_export':job,'known_bad_payment_authorizations':pay,'commit_dispatch_gap':{'orders':orders,'shipments':ship,'outbox':outbox},'forgotten_consumer_now_observed':True}
def price_attempt():
 stage('01-price-attempt');_,p=api('/v2/quote?sku=WARTUNG&quantity=3&customer_group=TREUE',expect=200);assert p['total_cents']==6783 and p['total_cents']!=6782,p
 return {'wrong_total':p['total_cents'],'preserved_total':6782,'rejected_as_extraction':True}
def price_finished():
 reset();stage('01-price');_,o=api('/v1/orders',order('golden'),expect=200);assert o['total_cents']==6782 and o['created_at'].startswith('2026-01-15'),o
 baseline=next(r['observed']['golden'] for r in records if r['id']=='T05');assert {k:v for k,v in o.items() if k!='created_at'}=={k:v for k,v in baseline.items() if k!='created_at'}
 return {'golden_response':o,'only_normalized_field':'created_at (real clock before seam, fixed injected clock in test)' ,'fixed_time_seam_observed':True}
def payment_contract():
 b={'key':'contract','order_id':'contract-order','amount_cents':1200,'mode':'ok'};_,a=api('/authorize',b,18891,200);_,again=api('/authorize',b,18891,200);assert a==again
 api('/authorize',{**b,'amount_cents':1201},18891,409);api('/authorization?key=missing',port=18891,expect=404)
 api('/v1/orders',order('weird',q=1,payment_mode='weird'),expect=502)
 assert int(sql("SELECT count(*) FROM legacy.orders WHERE request_id='weird'"))==0
 return {'same_key_reference':a,'amount_conflict_rejected':True,'unknown_provider_enum_rejected':True,'db_order_not_committed':True}
def robust_payment():
 reset();stage('02-shipping');_,o=api('/v1/orders',order('unknown',q=1,payment_mode='unknown_once'),expect=200);assert o['status']=='AUTHORIZED'
 count=int(sql("SELECT count(*) FROM payment.authorizations WHERE order_id='HB-unknown'"));assert count==1
 _,drop=api('/v1/orders',order('drop',q=1,payment_mode='drop_after_commit'),expect=200);assert int(sql("SELECT count(*) FROM payment.authorizations WHERE order_id='HB-drop'"))==1
 api('/v1/orders',order('declined',q=1,payment_mode='decline'),expect=402);assert int(sql("SELECT count(*) FROM legacy.orders WHERE request_id='declined'"))==0
 return {'unknown_reconciled_authorization_count':count,'transport_drop_reconciled':drop['provider_ref'],'decline_not_order':True,'outbox_drain':drain()}
def crash_duplicate():
 _,o=api('/v1/orders',order('crash',q=1),expect=200);assert int(sql("SELECT count(*) FROM ops.outbox WHERE order_id='HB-crash' AND state='PENDING'"))==1
 p=worker(True);assert p.returncode==70,p.stderr
 before={'shipments':int(sql("SELECT count(*) FROM shipping.dispatches WHERE order_id='HB-crash'")),'pending':int(sql("SELECT count(*) FROM ops.outbox WHERE order_id='HB-crash' AND state='PENDING'"))};assert before=={'shipments':1,'pending':1}
 p=worker();v=json.loads(p.stdout);assert v['remote_duplicate'] is True
 count=int(sql("SELECT count(*) FROM shipping.dispatches WHERE order_id='HB-crash'"));assert count==1
 api('/v1/orders/HB-crash/cancel',{},expect=409)
 return {'real_worker_exit':70,'after_crash':before,'retry_result':v,'final_shipments':count}
def cancel_and_stock():
 before=int(sql("SELECT available FROM legacy.stock WHERE sku='SENSOR'"))
 api('/v1/orders',order('cancel','SENSOR',2),expect=200)
 def snapshot():
  return json.loads(sql("""SELECT json_build_object(
    'order',(SELECT row_to_json(o) FROM legacy.orders o WHERE order_id='HB-cancel'),
    'stock',(SELECT available FROM legacy.stock WHERE sku='SENSOR'),
    'outbox',(SELECT json_agg(x ORDER BY event_id) FROM ops.outbox x WHERE order_id='HB-cancel'),
    'provider',(SELECT json_agg(p ORDER BY key) FROM payment.authorizations p WHERE order_id='HB-cancel'),
    'shipping',(SELECT json_agg(s ORDER BY event_id) FROM shipping.dispatches s WHERE order_id='HB-cancel'))"""))
 before_invalid=snapshot()
 api('/v1/orders/HB-cancel/cancel',expect=405,allow='POST')
 api('/v1/orders/HB-cancel/cancel',{},expect=405,method='PUT',allow='POST')
 api('/v1/orders/HB-cancel',{},expect=405,method='POST',allow='GET')
 after_invalid=snapshot()
 assert before_invalid==after_invalid,{'before':before_invalid,'after':after_invalid}
 _,cancelled=api('/v1/orders/HB-cancel/cancel',{},expect=200)
 _,repeated=api('/v1/orders/HB-cancel/cancel',{},expect=200)
 assert cancelled==repeated and cancelled['status']=='CANCELLED'
 after_cancel=snapshot()
 assert after_cancel['stock']==before and after_cancel['provider']==before_invalid['provider']
 assert after_cancel['outbox'][0]['state']=='CANCELLED' and after_cancel['shipping'] is None
 drain();after=int(sql("SELECT available FROM legacy.stock WHERE sku='SENSOR'"));assert before==after
 assert int(sql("SELECT count(*) FROM shipping.dispatches WHERE order_id='HB-cancel'"))==0
 sql("UPDATE legacy.stock SET available=1 WHERE sku='SENSOR'")
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rs=list(pool.map(lambda k:api('/v1/orders',order(k,'SENSOR',1,'STANDARD')),['stock-a','stock-b']))
 assert sorted(r[0] for r in rs)==[200,409],rs;assert sql("SELECT available FROM legacy.stock WHERE sku='SENSOR'")=='0';drain()
 return {'cancel_releases_once':True,'get_cancel_status':405,'get_cancel_allow':'POST','wrong_methods_state_unchanged':True,'method_state_before':before_invalid,'method_state_after':after_invalid,'post_cancel_success':True,'repeat_post_same_response':True,'after_post_cancel':after_cancel,'concurrent_stock_statuses':[r[0] for r in rs],'available':0}
def delivery_retry_poison():
 api('/v1/orders',order('transient',q=1),expect=200);cmd('docker','compose','stop','shipping');p=worker();failure_code=p.returncode;assert p.returncode!=0;assert sql("SELECT state FROM ops.outbox WHERE order_id='HB-transient'")=='PENDING'
 cmd('docker','compose','start','shipping');ready(18892);drain();assert sql("SELECT count(*) FROM shipping.dispatches WHERE order_id='HB-transient'")=='1'
 api('/v1/orders',order('poison',q=1),expect=200);sql("UPDATE ops.outbox SET kind='UNKNOWN_FUTURE' WHERE order_id='HB-poison'");p=worker();assert json.loads(p.stdout)['state']=='POISON'
 assert sql("SELECT count(*) FROM shipping.dispatches WHERE order_id='HB-poison'")=='0'
 sql("UPDATE ops.outbox SET kind='ORDER_READY',state='PENDING' WHERE order_id='HB-poison'");drain()
 return {'temporary_service_failure_worker_exit':failure_code,'retained_pending_during_outage':True,'poison_quarantined_and_repaired':True}
def replacement_backfill():
 stage('03-replacement');_,m=api('/admin/migrate',{},expect=200);assert api('/admin/reconcile',expect=200)[1]['equal']
 sql("UPDATE modern.orders SET total_cents=total_cents+1,tax_cents=tax_cents+1 WHERE request_id='unknown'")
 _,diff=api('/admin/reconcile',expect=200);assert not diff['equal']
 sql("UPDATE modern.orders SET total_cents=total_cents-1,tax_cents=tax_cents-1 WHERE request_id='unknown'");assert api('/admin/reconcile',expect=200)[1]['equal']
 sql("UPDATE modern.orders SET net_cents=net_cents+1,tax_cents=tax_cents-1 WHERE request_id='unknown'");assert not api('/admin/reconcile',expect=200)[1]['equal']
 sql("UPDATE modern.orders SET net_cents=net_cents-1,tax_cents=tax_cents+1 WHERE request_id='unknown'");assert api('/admin/reconcile',expect=200)[1]['equal']
 return {'migration':m,'intentional_divergence':diff,'repaired_equal':True}
def v2_compat():
 ctl('route_percent',100);b={'idempotency_key':'new-api','product_code':'PUMPE','units':3,'segment':'PARTNER'};_,v2=api('/v2/orders',b,expect=200);_,v1=api('/v1/orders/HB-new-api',expect=200);assert v1['total_cents']==v2['amount']['minor_units'] and v1['backend']=='modern'
 _,again=api('/v2/orders',b,expect=200);assert again==v2
 api('/v2/orders',order('wrong-shape'),expect=422);api('/v1/orders',b,expect=422);drain()
 return {'v2':v2,'v1_compatibility':v1,'cross_protocol_shapes_rejected':True}
def shadow():
 _,before=api('/admin/stats',expect=200);b={**order('shadow'), 'unit_net':'19.995'};_,safe=api('/admin/shadow',b,expect=200);assert safe['equal']
 _,after=api('/admin/stats',expect=200);assert before==after
 b['unit_net']='20.005';_,wrong=api('/admin/shadow',b,expect=200);assert not wrong['equal'];assert api('/admin/stats',expect=200)[1]==before
 b['unit_net']='19.995';api('/admin/shadow?unsafe=true',b,expect=200);_,bad=api('/admin/stats',expect=200);assert bad['modern.orders']==before['modern.orders']+1 and bad['payment.authorizations']==before['payment.authorizations']+1
 drain();return {'safe_no_persistent_or_external_effect':True,'price_divergence_visible':wrong,'unsafe_shadow_order_delta':bad['modern.orders']-before['modern.orders'],'unsafe_shadow_payment_delta':bad['payment.authorizations']-before['payment.authorizations']}
def java_hash(s):
 n=0
 for c in s:n=(31*n+ord(c))&0xffffffff
 if n>=2**31:n-=2**32
 return n
def cohorts():
 ctl('route_percent',50);keys=[]
 for want in ['legacy','modern']:
  key=next(f'cohort-{i}' for i in range(1000) if ('modern' if java_hash(f'cohort-{i}')%100<50 else 'legacy')==want)
  _,o=api('/v1/orders',order(key,q=1),expect=200);assert o['backend']==want;keys.append({'key':key,'backend':want})
 drain();ctl('route_percent',100);return {'cohorts':keys,'kill_switch_is_routing_only':True}
def failed_rollback():
 _,target=api('/v1/orders',order('target-write',q=1),expect=200);drain();ctl('route_percent',0);code,missing=api('/v1/orders/HB-target-write',expect=404)
 # The target row still exists: naive route rollback loses visibility, not physical rows.
 assert sql("SELECT count(*) FROM modern.orders WHERE request_id='target-write'")=='1'
 api('/admin/rollback',{},expect=409);ctl('writes_frozen',True);api('/v1/orders',order('frozen'),expect=503)
 _,rolled=api('/admin/rollback',{},expect=200);ctl('writes_frozen',False);_,restored=api('/v1/orders/HB-target-write',expect=200);assert restored['total_cents']==target['total_cents'] and restored['backend']=='legacy'
 return {'naive_route_rollback_response':missing,'target_row_was_retained':True,'unfrozen_reverse_migration_rejected':True,'safe_reverse_migration':rolled,'restored_target_write':restored}
def retirement():
 api('/admin/migrate',{},expect=200);ctl('route_percent',100);legacy_job=json.loads(report('legacy').stdout);api('/admin/retire',{},expect=409)
 modern_job=json.loads(report('modern').stdout);before=int(sql("SELECT count(*) FROM ops.audit WHERE action='old-read'"));_,retired=api('/admin/retire',{},expect=200);api('/legacy/report',expect=410);api('/report?consumer=nightly-export',expect=200);api('/v1/orders/HB-target-write',expect=200);after=int(sql("SELECT count(*) FROM ops.audit WHERE action='old-read'"));assert before==after
 return {'legacy_scheduled_job':legacy_job,'modern_scheduled_job':modern_job,'forgotten_batch_prevented_retirement':True,'retired':retired,'old_reads_before':before,'old_reads_after':after,'scope':'registered synthetic consumer inventory only'}

def ownership_conflict():
 reset();stage('02-shipping');_,old=api('/v1/orders',order('owner',q=1),expect=200);drain();stage('03-replacement');ctl('route_percent',100)
 api('/v1/orders',order('owner',q=1),expect=409)
 assert sql("SELECT count(*) FROM modern.orders WHERE request_id='owner'")=='0'
 assert sql("SELECT count(*) FROM payment.authorizations WHERE order_id='HB-owner'")=='1'
 api('/dispatch',{'event_id':'ship-owner','order_id':'HB-owner','total_cents':old['total_cents']+1},18892,409)
 api('/dispatch',{'event_id':'different-event','order_id':'HB-owner','total_cents':old['total_cents']},18892,409)
 return {'competing_order_owner_rejected':True,'single_authorization_retained':True,'same_event_changed_payload_rejected':True,'new_event_same_order_rejected':True}

def freeze_barrier():
 reset();stage('03-replacement');ctl('route_percent',100)
 with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
  pending=pool.submit(api,'/v1/orders',order('inflight',q=1,payment_mode='slow_ok'))
  found=False
  for _ in range(50):
   if sql("SELECT count(*) FROM payment.authorizations WHERE order_id='HB-inflight'")=='1':found=True;break
   time.sleep(.01)
  assert found
  ctl('writes_frozen',True)
  assert sql("SELECT count(*) FROM modern.orders WHERE order_id='HB-inflight'")=='1'
  result=pending.result();assert result[0]==200,result
 api('/v1/orders',order('post-freeze',q=1),expect=503)
 api('/v1/orders/HB-inflight/cancel',{},expect=503)
 api('/admin/rollback',{},expect=409)
 drain();api('/admin/rollback',{},expect=200);ctl('writes_frozen',False)
 _,o=api('/v1/orders/HB-inflight',expect=200);assert o['status']=='SHIPPED' and o['backend']=='legacy'
 return {'freeze_waited_for_inflight_commit':True,'new_order_and_cancel_blocked':True,'pending_delivery_prevented_reverse_migration':True,'order_preserved_after_reverse':o}

def alternatives():
 observations=[]
 for version in ['01-price','02-shipping']:
  reset();stage(version)
  start=time.monotonic();_,o=api('/v1/orders',order('alternative'),expect=200);elapsed=round(time.monotonic()-start,4)
  initial={'version':version,'response_status':o['status'],'total_cents':o['total_cents'],'request_seconds_local_only':elapsed,'shipments_before_worker':int(sql("SELECT count(*) FROM shipping.dispatches")),'pending_before_worker':int(sql("SELECT count(*) FROM ops.outbox WHERE state='PENDING'"))}
  if version=='02-shipping':drain()
  assert sql("SELECT count(*) FROM shipping.dispatches WHERE order_id='HB-alternative'")=='1'
  cmd('docker','compose','stop','shipping')
  code,response=api('/v1/orders',order('outage',q=1),expect=500 if version=='01-price' else 200)
  initial['outage_response_code']=code;initial['outage_response']=response;initial['outage_order_persisted']=sql("SELECT count(*) FROM legacy.orders WHERE order_id='HB-outage'")
  initial['outage_pending_event']=sql("SELECT count(*) FROM ops.outbox WHERE order_id='HB-outage' AND state='PENDING'")
  cmd('docker','compose','start','shipping');ready(18892)
  if version=='02-shipping':drain()
  observations.append(initial)
 assert [o['total_cents'] for o in observations]==[6782,6782]
 assert observations[0]['response_status']=='SHIPPED' and observations[1]['response_status']=='AUTHORIZED'
 assert observations[0]['outage_pending_event']=='0' and observations[1]['outage_pending_event']=='1'
 return {'same_scenario_alternatives':observations,'tradeoff':'synchronous completion versus durable deferred delivery and extra worker/service operations; local timing is not a capacity result','not_tested_alternative':'an in-process outbox dispatcher without a separate shipping workflow process'}

def main():
 ready();ready(18891);ready(18892)
 check('T01','Sauberer Container-Neubau mit identischem JAR',[2,5], 'Gepinnter javac/jar erzeugt identischen Inhalt.',build_repro)
 check('T02','180 Preisfälle, Rundungs- und Normalisierungsgegenbeispiele, Zeit-/Persistence-Seams',[3,6,7,8,9,12], 'Alt=korrekte Extraktion; Fehlversuch und Übernormalisierung werden erkannt.',selftest)
 check('T03','Echte Paketgrenze und isoliert baubares Preismodul',[9,10], 'Verbotener interner Import kompiliert nicht.',architecture)
 check('T04','Datenbesitz durch Datenbankrecht erzwungen',[10,13], 'Auftragsrolle darf nicht in Versandtabelle schreiben.',ownership)
 check('T05','Alt-API, Golden Master und negative Eingaben',[2,3,6,8,14], '6782Cent, Wiederholung ohne zweite Wirkung, inkompatible Requests abgelehnt.',baseline)
 check('T06','Bewiesene Altfehler und vergessener Bericht',[4,7,15,17], 'Doppelte Freigabe und Versandlücke werden als bekannte Fehler beobachtet.',legacy_defects)
 check('T07','Gescheiterte Preisextraktion',[6,12], 'Frühe Rundung weicht um1Cent ab und wird zurückgewiesen.',price_attempt)
 check('T08','Korrekte Preisextraktion mit unverändertem Altvertrag',[7,10,12], 'Golden-Antwort stimmt bis auf separat geprüfte Uhrzeit mit Baseline überein.',price_finished)
 check('T09','Payment-Vertrag gegen echten HTTP-Simulator',[7,11,14], 'Schlüsselkonflikt und unbekannter Providerzustand werden nicht als Erfolg behandelt.',payment_contract)
 check('T10','UNKNOWN und tatsächlicher Transportabbruch nach Providercommit',[7,8,11,18], 'Neue Verarbeitung erzeugt genau eine Freigabe je Schlüssel.',robust_payment)
 check('T11','Worker-Prozesscrash nach Versandannahme und erneute Zustellung',[15,18], 'Exit70, Outbox bleibt offen, Duplikat erzeugt keinen zweiten Versand.',crash_duplicate)
 check('T12','Storno-Methodengrenze, Wiederholung und konkurrierender letzter Bestand',[8,13,18], 'GET-Storno405/AllowPOST ohne Wirkung; POST-Storno einmalig, kein negativer Bestand.',cancel_and_stock)
 check('T13','Gestoppter Versanddienst und Gift-Nachricht',[15,16,17,18], 'Ereignis bleibt erhalten; Quarantäne und Reparatur sind sichtbar.',delivery_retry_poison)
 check('T14','Backfill und unabhängiger Abgleich einer Abweichung',[13,16,23], 'Absichtliche Betragsabweichung erkannt und repariert.',replacement_backfill)
 check('T15','v2-Vertrag und v1-Kompatibilitätsadapter',[11,14,23], 'Beide Clients sehen gleiche Centbeträge; fremde Feldform wird abgelehnt.',v2_compat)
 check('T16','Sicheres Shadow und absichtlich unsichere Variante',[6,19,23], 'Sicherer Pfad ohne Nebenwirkung; Geldabweichung und unsicheres Shadow bleiben sichtbar.',shadow)
 check('T17','Deterministische Kohorten und Flagwechsel',[20,23], '50Prozent-Routing erreicht beide Implementierungen.',cohorts)
 check('T18','Fehlgeschlagene Routingrücknahme nach Zielschreiben und reparierter Rückweg',[20,21,23], 'Neue Aufträge bleiben erhalten und nach sicherer Rückführung sichtbar.',failed_rollback)
 check('T19','Vergessener Batchjob blockiert Abschaltung',[4,22,23], 'Abschaltung erst nach Verbrauchermigration; Alt-Endpoint danach410.',retirement)
 check('T20','Konkurrierender Datenbesitz und Versand-Vertragskonflikte',[11,13,14,18], 'Zweiter Eigentümer und geänderter Ereignisinhalt werden abgelehnt.',ownership_conflict)
 check('T21','Schreibsperre wartet laufende Auftragstransaktion ab',[20,21,23], 'Providerwirkung vor Sperre, Auftrag vor Sperrbestätigung vollständig; Rückweg erst nach Zustellung.',freeze_barrier)
 check('T22','Modularer Ablauf gegen ausgelagerten Versandworkflow am gleichen Szenario',[9,17,18,24], 'Gleicher Betrag und eine Wirkung; unterschiedliche Abschlusssemantik und Ausfallkopplung ausdrücklich gemessen.',alternatives)
 save();return 1 if any(r['status']=='failed' for r in records) else 0
if __name__=='__main__':raise SystemExit(main())
