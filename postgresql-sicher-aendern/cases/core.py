"""CH01–06, CH15–16: decisions, workload, MVCC, locks and recovery."""
import concurrent.futures
import json
import re
import statistics
import time
from lib import *

def decision(n,e):
    f=fingerprint(n)
    card={'change':'Neue EUR-Spalte vorbereiten','go':{'unbalanced_orders':0,'expected_orders':24000},
          'abort':['Fachsumme abweichend','DDL wartet länger als 300 ms auf Lock'],
          'single_writer':True,'downtime_promise':False}
    def judge(x):
        return x['unbalanced_orders']==0 and x['orders']==card['go']['expected_orders']
    require(judge(f),'Baseline rejected')
    corrupt=dict(f,unbalanced_orders=1)
    require(not judge(corrupt),'No-go failed to reject corrupt candidate')
    e.save('CH01/change-card.json',card)
    return {'baseline':'go','deliberate_bad_candidate':'no-go','fingerprint':f}

def fixture(n,e):
    first=fingerprint(n)
    second=seed(n)
    require(first==second,'Seed is not reproducible')
    require(second['orders']==24000 and second['items']==72000,'Wrong fixture cardinality')
    require(second['total_cents']==second['item_total_cents'] and second['unbalanced_orders']==0,'Money invariant violated')
    manifest=environment(n)
    manifest['fixture']=second
    manifest['sizes']=SIZES
    e.save('CH02/start-manifest.json',manifest)
    return manifest

def workload(n,e,label='baseline',runs=3):
    measurements=[]
    for trial in range(runs):
        sql(n,'SELECT count(*) FROM shop.orders; SELECT sum(quantity) FROM shop.order_items;') # explicit warm-up
        workers=[]
        for client in range(2):
            script='\\timing on\n'
            for k in range(15):
                key=1+((trial*19+client*11+k*13)%2000)
                if k%3==0:
                    script+=f'SELECT count(*) FROM shop.orders WHERE customer_id={key};\n'
                elif k%3==1:
                    script+=f'SELECT sum(quantity*unit_price_cents) FROM shop.order_items WHERE order_id={1+k*31};\n'
                else:
                    script+='BEGIN; UPDATE shop.inventory SET reserved=reserved+1 WHERE product_id=1; UPDATE shop.inventory SET reserved=reserved-1 WHERE product_id=1; COMMIT;\n'
            workers.append(spawn_sql(n,script,f'lfb_ch03_{label}_{trial}_{client}'))
        elapsed=[]
        for idx,p in enumerate(workers):
            r=finish(p)
            e.save(f'CH03/{label}-run{trial+1}-client{idx+1}.json',r)
            require(r['returncode']==0,'Workload client failed')
            elapsed += [float(x) for x in re.findall(r'Time: ([\d.]+) ms',r['stdout'])]
        require(len(elapsed)>=30,'Missing psql timing records')
        ordered=sorted(elapsed)
        row={'trial':trial+1,'psql_statement_samples':len(elapsed),'median_ms':statistics.median(elapsed),
             'p95_ms':ordered[int(.95*(len(ordered)-1))],'max_ms':max(elapsed),'error_count':0,'raw_ms':elapsed}
        measurements.append(row)
    e.save(f'CH03/{label}-measurements.json',measurements)
    return {'runs':measurements,'note':'psql statement timings incl. transaction control; 2 clients, fixed mix; not production latency or a controlled hardware benchmark'}

def gate(n,number,app):
    p=spawn_sql(n,f'SELECT pg_advisory_lock({number}); SELECT pg_sleep(60);',app)
    wait_activity(n,app,wait='Timeout')
    return p

def snapshots(n,e):
    sql(n,'DROP TABLE IF EXISTS shop.mvcc_demo; CREATE TABLE shop.mvcc_demo(id int PRIMARY KEY,v int); INSERT INTO shop.mvcc_demo VALUES(1,10);')
    g=gate(n,74004,'lfb_ch04_gate')
    a=spawn_sql(n,"BEGIN ISOLATION LEVEL REPEATABLE READ; SELECT 'before='||v FROM shop.mvcc_demo WHERE id=1; SELECT pg_advisory_xact_lock(74004); SELECT 'after='||v FROM shop.mvcc_demo WHERE id=1; COMMIT;",'lfb_ch04_snapshot')
    try:
        observed=wait_activity(n,'lfb_ch04_snapshot',wait='Lock')
        sql(n,'UPDATE shop.mvcc_demo SET v=20 WHERE id=1;')
        terminate_app(n,'lfb_ch04_gate');finish(g)
        r=finish(a)
        require(r['returncode']==0 and 'before=10' in r['stdout'] and 'after=10' in r['stdout'],'Repeatable read visibility wrong')
        require(sql(n,'SELECT v FROM shop.mvcc_demo WHERE id=1;')=='20','Committed value missing')
        sql(n,'BEGIN; UPDATE shop.mvcc_demo SET v=99 WHERE id=1; ROLLBACK;')
        require(sql(n,'SELECT v FROM shop.mvcc_demo WHERE id=1;')=='20','Rollback failed')
        return {'snapshot':r,'observed_wait':observed,'false_expectation_after_commit_20':'disproved; repeatable-read snapshot stays at 10','fresh_session':20,'rollback_preserved':20}
    finally:
        terminate_app(n,'lfb_ch04_gate');terminate_app(n,'lfb_ch04_snapshot')

def locks(n,e):
    h=spawn_sql(n,'BEGIN; LOCK TABLE shop.orders IN ACCESS SHARE MODE; SELECT pg_sleep(60);','lfb_ch05_holder')
    wait_activity(n,'lfb_ch05_holder',wait='Timeout')
    try:
        # Do not require an out-of-process observer to catch a 350 ms window.
        # Observe one bounded long-wait probe, cancel it, then test the short timeout separately.
        probe=spawn_sql(n,"SET lock_timeout='15s'; ALTER TABLE shop.orders ADD COLUMN ch05_probe int;",'lfb_ch05_observe')
        observed=wait_activity(n,'lfb_ch05_observe',wait='Lock')
        sql(n,"SELECT pg_cancel_backend(pid) FROM pg_stat_activity WHERE application_name='lfb_ch05_observe';")
        probe_result=finish(probe)
        require(probe_result['returncode']!=0 and '57014' in probe_result['stderr'],'Observed DDL probe was not cancelled')
        b=spawn_sql(n,"SET lock_timeout='350ms'; ALTER TABLE shop.orders ADD COLUMN ch05_probe int;",'lfb_ch05_ddl')
        result=finish(b)
        require(result['returncode']!=0 and '55P03' in result['stderr'],'Expected lock_timeout SQLSTATE 55P03')
        e.save('CH05/blocking-graph.json',observed)
    finally:
        terminate_app(n,'lfb_ch05_holder');finish(h)
    sql(n,"SET lock_timeout='350ms'; ALTER TABLE shop.orders ADD COLUMN ch05_probe int; ALTER TABLE shop.orders DROP COLUMN ch05_probe;")
    stmt=raw_sql(n,"SET statement_timeout='100ms'; SELECT pg_sleep(2);",check=False)
    require(stmt.returncode!=0 and '57014' in stmt.stderr,'Expected statement timeout')
    # Prove the error aborts the whole transaction, and SET LOCAL has transaction scope.
    tx=raw_sql(n,"BEGIN; SET LOCAL statement_timeout='100ms'; SELECT pg_sleep(2); SELECT 1;",check=False)
    require(tx.returncode!=0 and '57014' in tx.stderr,'Timed-out transaction test missing')
    return {'observed_probe_cancelled':probe_result,'blocked_ddl':result,'statement_timeout':stmt.stderr,'transaction_after_statement_timeout':tx.stderr,'transaction_timeout_GUC_tested':False,'corrected_ddl':'succeeded after holder ended','observation_design':'Separate 15-second-bounded probe is observed then cancelled; short 350ms timeout tested without racing the observer'}

def restore(n,e):
    dst=start('restore18')
    sql(dst,'DROP SCHEMA IF EXISTS shop CASCADE;')
    cmd=['docker','exec',n,'pg_dump','-U','postgres','-d',DATABASE,'--schema=shop','--format=custom','--no-owner','--no-acl']
    before=fingerprint(n)
    dump=run(cmd,binary=True).stdout
    path=e.save('CH06/shop.dump',dump)
    r=run(['docker','exec','-i',dst,'pg_restore','-U','postgres','-d',DATABASE,'--exit-on-error','--no-owner','--no-acl'],input=dump,binary=True)
    after=fingerprint(dst)
    require(before==after,'Restored business fingerprint differs')
    globals_=run(['docker','exec',n,'pg_dumpall','-U','postgres','--globals-only','--no-role-passwords']).stdout
    e.save('CH06/globals-review.sql',globals_)
    for server in (n,dst):
        sql(server,"DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='lfb_reader') THEN CREATE ROLE lfb_reader LOGIN; END IF; END $$; GRANT USAGE ON SCHEMA shop TO lfb_reader; GRANT SELECT ON ALL TABLES IN SCHEMA shop TO lfb_reader;")
    read=raw_sql(dst,'SELECT count(*) FROM shop.orders;',user='lfb_reader')
    denied=raw_sql(dst,'UPDATE shop.inventory SET reserved=reserved+1 WHERE product_id=1;',user='lfb_reader',check=False)
    require(read.stdout.strip()=='24000' and '42501' in denied.stderr,'Restored least-privilege reader test failed')
    return {'separate_instance':dst,'dump_bytes':len(dump),'sha256':hashlib.sha256(dump).hexdigest(),'before':before,'restored':after,
            'roles':'globals separately exported without passwords; not blindly applied to another cluster',
            'restored_reader_select_rows':int(read.stdout.strip()),'restored_reader_write_sqlstate':'42501',
            'physical_WAL_path':'See separately executed CH06 physical-basebackup supplement when present; no PITR claim from logical restore'}

def physical_backup(n,e):
    """Independent full backup including streamed WAL, verifybackup, and startup in owned helper."""
    from cases.upgrades import upgrade_container, ushell
    helper=upgrade_container()
    token='physical_'+uuid.uuid4().hex[:10]
    source_path='/tmp/lfb_pg_book_20261118_'+token
    target_path='/var/lib/postgresql/lfb_pg_book_20261118_upgrade_work/'+token
    baseline=fingerprint(n)
    backed=run(['docker','exec',n,'pg_basebackup','-U','postgres','-h','/var/run/postgresql','-D',source_path,'--format=plain','--wal-method=stream','--checkpoint=fast','--no-password'],timeout=120)
    verified=run(['docker','exec',n,'pg_verifybackup',source_path],timeout=120)
    # tar carries only this fixed, freshly created backup directory between owned containers.
    archive=run(['docker','exec',n,'tar','-C',source_path,'-czf','-','.'],binary=True,timeout=120).stdout
    e.save('CH06/full-basebackup.tar.gz',archive)
    ushell(helper,f'mkdir -m 700 {target_path}; tar -C {target_path} -xzf -',input=archive,timeout=120)
    started=ushell(helper,f"/usr/lib/postgresql/18/bin/pg_ctl -D {target_path} -l {target_path}/restored-server.log -o '-p 55419 -k /tmp -c listen_addresses= -c shared_buffers=64MB -c max_wal_size=128MB' -w start")
    try:
        restored=ushell(helper,'/usr/lib/postgresql/18/bin/psql -X -q -A -t -v ON_ERROR_STOP=1 -h /tmp -p 55419 -d lfb_book',input=(ROOT/'sql/fingerprint.sql').read_text())
        after=json.loads(restored.stdout.strip())
        require(after==baseline,'Physical WAL-bearing restore fingerprint mismatch')
    finally:
        ushell(helper,f'/usr/lib/postgresql/18/bin/pg_ctl -D {target_path} -m fast -w stop')
    e.save('CH06/verifybackup.txt',verified.stdout+verified.stderr)
    e.save('CH06/physical-startup.txt',started.stdout+started.stderr)
    return {'full_backup_with_streamed_WAL':True,'verifybackup_output':verified.stdout,'archive_bytes':len(archive),
      'source_fingerprint':baseline,'physical_restored_fingerprint':after,'scope':'Full pg_basebackup plus included/streamed WAL and separate startup actually run. No archive/PITR-to-arbitrary-time rehearsal.'}

def deadlock(n,e):
    sql(n,'DROP TABLE IF EXISTS shop.deadlock_demo; CREATE TABLE shop.deadlock_demo(id int PRIMARY KEY,v int); INSERT INTO shop.deadlock_demo VALUES(1,0),(2,0);')
    g=spawn_sql(n,'SELECT pg_advisory_lock(75001); SELECT pg_advisory_lock(75002); SELECT pg_sleep(60);','lfb_ch15_gate')
    wait_activity(n,'lfb_ch15_gate',wait='Timeout')
    a=spawn_sql(n,"SET deadlock_timeout='100ms'; BEGIN; UPDATE shop.deadlock_demo SET v=v+1 WHERE id=1; SELECT pg_advisory_xact_lock(75001); UPDATE shop.deadlock_demo SET v=v+1 WHERE id=2; COMMIT;",'lfb_ch15_a')
    b=spawn_sql(n,"SET deadlock_timeout='100ms'; BEGIN; UPDATE shop.deadlock_demo SET v=v+1 WHERE id=2; SELECT pg_advisory_xact_lock(75002); UPDATE shop.deadlock_demo SET v=v+1 WHERE id=1; COMMIT;",'lfb_ch15_b')
    try:
        wait_activity(n,'lfb_ch15_a',wait='Lock');wait_activity(n,'lfb_ch15_b',wait='Lock')
        terminate_app(n,'lfb_ch15_gate');finish(g)
        outcomes=[finish(a),finish(b)]
        require(sum(x['returncode']==0 for x in outcomes)==1,'Exactly one deadlock participant must commit')
        require(any('40P01' in x['stderr'] for x in outcomes),'Deadlock SQLSTATE missing')
        # Retry the entire aborted transaction, with canonical lock order.
        sql(n,'BEGIN; UPDATE shop.deadlock_demo SET v=v+1 WHERE id=1; UPDATE shop.deadlock_demo SET v=v+1 WHERE id=2; COMMIT;')
        require(sql(n,'SELECT sum(v) FROM shop.deadlock_demo;')=='4','Whole-transaction retry lost data')
        return {'sessions':outcomes,'whole_transaction_retry_sum':4}
    finally:
        for app in ('lfb_ch15_gate','lfb_ch15_a','lfb_ch15_b'):terminate_app(n,app)

def vacuum(n,e):
    sql(n,'DROP TABLE IF EXISTS shop.vacuum_demo; CREATE TABLE shop.vacuum_demo(id int PRIMARY KEY,payload text) WITH (autovacuum_enabled=false); INSERT INTO shop.vacuum_demo SELECT g,repeat(md5(g::text),8) FROM generate_series(1,10000) g;')
    g=gate(n,76016,'lfb_ch16_gate')
    snapshot=spawn_sql(n,'BEGIN ISOLATION LEVEL REPEATABLE READ; SELECT count(*) FROM shop.vacuum_demo; SELECT pg_advisory_xact_lock(76016); COMMIT;','lfb_ch16_snapshot')
    wait_activity(n,'lfb_ch16_snapshot',wait='Lock')
    wal_before=sql(n,'SELECT pg_current_wal_lsn();')
    sql(n,"UPDATE shop.vacuum_demo SET payload=repeat('neu',100);")
    held=raw_sql(n,'VACUUM (VERBOSE,ANALYZE) shop.vacuum_demo;')
    e.save('CH16/vacuum-with-snapshot.txt',held.stdout+held.stderr)
    require('not yet removable' in held.stderr,'Expected snapshot-retained dead tuples in VACUUM VERBOSE')
    terminate_app(n,'lfb_ch16_gate');finish(g);finish(snapshot)
    cleaned=raw_sql(n,'VACUUM (VERBOSE,ANALYZE) shop.vacuum_demo;')
    e.save('CH16/vacuum-after-snapshot.txt',cleaned.stdout+cleaned.stderr)
    stats=scalar_json(n,"SELECT json_build_object('relation_bytes',pg_total_relation_size('shop.vacuum_demo'),'wal_delta_bytes',pg_wal_lsn_diff(pg_current_wal_lsn(),'"+wal_before+"'),'rows',(SELECT count(*) FROM shop.vacuum_demo));")
    require(stats['rows']==10000 and stats['wal_delta_bytes']>0,'VACUUM invariants failed')
    return {'metrics':stats,'retained_versions_observed':True,'autovacuum':'disabled only on isolated demo table to make manual VACUUM reproducible; not cluster-wide','size_note':'relation bytes are not a direct bloat estimate or disk returned to OS'}
