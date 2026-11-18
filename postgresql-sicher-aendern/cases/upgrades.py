"""CH20–24: real 17.12→18.7 copy upgrade, dump/restore and logical migration.

All paths, cluster names, databases and commands are fixed to the owned lab.
"""
import json
import shlex
import time
import uuid
from lib import *

STATE=ROOT/'outputs/upgrade-state.json'
LOGICAL_STATE=ROOT/'outputs/logical-state.json'
UPGRADE_IMAGE=PROJECT+'_upgrade:17.12-18.7'

def upgrade_container():
    name=NAMES['upgrade']
    obj=inspect('container',name)
    if obj:
        assert_owned(name)
        if not obj['State']['Running']:run(['docker','start',name])
        image=inspect('image',obj['Image'])
        (ROOT/'upgrade-image.lock.json').write_text(json.dumps({'image_id':image['Id'],'architecture':image['Architecture'],
          'dockerfile_sha256':hashlib.sha256((ROOT/'Dockerfile.upgrade').read_bytes()).hexdigest(),
          'sources':'Digest-pinned official postgres 17.12 and 18.7 images, Debian 13 arm64'},indent=2)+'\n')
        return name
    ensure_network()
    image=inspect('image',UPGRADE_IMAGE)
    if not image:
        run(['docker','build','--network','none','--label',f'{LABEL}={PROJECT}',
             '-f',str(ROOT/'Dockerfile.upgrade'),'-t',UPGRADE_IMAGE,str(ROOT)],timeout=300)
        image=inspect('image',UPGRADE_IMAGE)
    require(image['Config'].get('Labels',{}).get(LABEL)==PROJECT,'Custom image ownership mismatch')
    (ROOT/'upgrade-image.lock.json').write_text(json.dumps({'image_id':image['Id'],'architecture':image['Architecture'],
      'dockerfile_sha256':hashlib.sha256((ROOT/'Dockerfile.upgrade').read_bytes()).hexdigest(),
      'sources':'Digest-pinned official postgres 17.12 and 18.7 images, Debian 13 arm64'},indent=2)+'\n')
    vol=name+'_data'
    existing=inspect('volume',vol)
    if existing:require(existing.get('Labels',{}).get(LABEL)==PROJECT,'Upgrade volume collision')
    else:run(['docker','volume','create','--label',f'{LABEL}={PROJECT}',vol])
    run(['docker','run','-d','--name',name,'--label',f'{LABEL}={PROJECT}','--network',NETWORK,
         '--memory','2g','--cpus','2','--pids-limit','256','--mount',f'type=volume,source={vol},target=/var/lib/postgresql',
         '--entrypoint','bash',image['Id'],'-c','sleep infinity'])
    # The official image's mounted data root is initially root-owned.
    run(['docker','exec',name,'install','-d','-o','postgres','-g','postgres','/var/lib/postgresql/lfb_pg_book_20261118_upgrade_work'])
    return name

def ushell(name,script,check=True,timeout=120,input=None):
    assert_owned(name)
    require(name==NAMES['upgrade'],'Upgrade shell outside allowlist')
    return run(['docker','exec','-i','-u','postgres',name,'bash','-ceu',script],check=check,timeout=timeout,input=input,binary=isinstance(input,bytes))

def uquery(name,query,port=55418):
    require(port in (55417,55418),'Upgrade port outside allowlist')
    return ushell(name,f'/usr/lib/postgresql/{17 if port==55417 else 18}/bin/psql -X -q -v ON_ERROR_STOP=1 -A -t -h /tmp -p {port} -d lfb_book_upgrade',input=query).stdout.strip()

def preflight(n,e):
    src=start('pg17');f=seed(src)
    source_manifest=environment(src)
    source_manifest['extensions']=scalar_json(src,'SELECT json_agg(row_to_json(x)) FROM (SELECT extname,extversion FROM pg_extension ORDER BY extname) x;')
    source_manifest['collations']=scalar_json(src,"SELECT json_agg(row_to_json(x)) FROM (SELECT datname,datlocprovider,datcollversion FROM pg_database WHERE datname=current_database()) x;")
    e.save('CH20/source-manifest.json',source_manifest)
    name=upgrade_container()
    # No previous cluster is removed. A unique child directory bounds each attempt.
    token='run_'+uuid.uuid4().hex[:12]
    work='/var/lib/postgresql/lfb_pg_book_20261118_upgrade_work/'+token
    script=f"""
mkdir -m 700 {work}
cd {work}
/usr/lib/postgresql/17/bin/initdb -D old --data-checksums --locale=C.UTF-8 > init17.log
/usr/lib/postgresql/18/bin/initdb -D new --data-checksums --locale=C.UTF-8 > init18.log
/usr/lib/postgresql/17/bin/pg_ctl -D old -l old-server.log -o '-p 55417 -k /tmp -c listen_addresses= -c shared_buffers=64MB -c max_wal_size=128MB' -w start
/usr/lib/postgresql/17/bin/createdb -h /tmp -p 55417 lfb_book_upgrade
/usr/lib/postgresql/17/bin/postgres --version
/usr/lib/postgresql/18/bin/postgres --version
"""
    init=ushell(name,script)
    e.save('CH20/cluster-init.txt',init.stdout+init.stderr)
    fixture=(ROOT/'sql/fixture.sql').read_text()
    ushell(name,'/usr/lib/postgresql/17/bin/psql -X -q -v ON_ERROR_STOP=1 -v order_count=24000 -h /tmp -p 55417 -d lfb_book_upgrade',input=fixture)
    oldfp=json.loads(uquery(name,(ROOT/'sql/fingerprint.sql').read_text(),55417))
    require(oldfp==f,'pg_upgrade source fixture differs from logical source fixture')
    ushell(name,f'/usr/lib/postgresql/17/bin/pg_ctl -D {work}/old -m fast -w stop')
    check_cmd=f"cd {work}; /usr/lib/postgresql/18/bin/pg_upgrade --check --old-bindir=/usr/lib/postgresql/17/bin --new-bindir=/usr/lib/postgresql/18/bin --old-datadir={work}/old --new-datadir={work}/new --old-port=55417 --new-port=55418 --socketdir=/tmp"
    checked=ushell(name,check_cmd)
    e.save('CH20/pg-upgrade-check.txt',checked.stdout+checked.stderr)
    require('Clusters are compatible' in checked.stdout,'pg_upgrade check compatibility verdict absent')
    state={'container':name,'work':work,'old_fingerprint':oldfp,'source17':src,'check_passed':True,'upgraded':False,
       'image_id':inspect('container',name)['Image'],'source_version':'17.12','target_version':'18.7','mode':'copy'}
    STATE.write_text(json.dumps(state,indent=2)+'\n')
    e.save('CH20/preflight-state.json',state)
    return {'source':source_manifest,'pg_upgrade_check':'actually executed, compatible','upgrade_container':name,'work':work,'fingerprint':oldfp,'no_pg19':True}

def upgrade(n,e):
    if not STATE.exists():preflight(n,e)
    state=json.loads(STATE.read_text())
    if state.get('upgraded'):
        preflight(n,e);state=json.loads(STATE.read_text())
    name=state['container'];work=state['work']
    require(name==NAMES['upgrade'] and work.startswith('/var/lib/postgresql/lfb_pg_book_20261118_upgrade_work/run_'),'Unsafe upgrade state')
    started=time.monotonic()
    command=f"cd {work}; /usr/lib/postgresql/18/bin/pg_upgrade --copy --old-bindir=/usr/lib/postgresql/17/bin --new-bindir=/usr/lib/postgresql/18/bin --old-datadir={work}/old --new-datadir={work}/new --old-port=55417 --new-port=55418 --socketdir=/tmp"
    result=ushell(name,command,timeout=180)
    elapsed=time.monotonic()-started
    e.save('CH21/pg-upgrade-copy.txt',result.stdout+result.stderr)
    require('Upgrade Complete' in result.stdout,'Actual upgrade completion verdict absent')
    ushell(name,f"/usr/lib/postgresql/18/bin/pg_ctl -D {work}/new -l {work}/new-server.log -o '-p 55418 -k /tmp -c listen_addresses= -c shared_buffers=64MB -c max_wal_size=128MB' -w start")
    newfp=json.loads(uquery(name,(ROOT/'sql/fingerprint.sql').read_text()))
    require(newfp==state['old_fingerprint'],'pg_upgrade business fingerprint mismatch')
    require(uquery(name,'SHOW server_version;').startswith('18.7'),'Wrong upgraded runtime version')
    # Independent dump/restore major-version path, separate running 17.12 source and 18.7 target.
    src=state['source17'];dst=start('restore18')
    sql(dst,'DROP SCHEMA IF EXISTS shop CASCADE;')
    dump=run(['docker','exec',src,'pg_dump','-U','postgres','-d',DATABASE,'--schema=shop','--format=custom','--no-owner','--no-acl'],binary=True).stdout
    e.save('CH21/source17.dump',dump)
    started_dump=time.monotonic()
    restored=run(['docker','exec','-i',dst,'pg_restore','-U','postgres','-d',DATABASE,'--exit-on-error','--no-owner','--no-acl'],input=dump,binary=True)
    dump_elapsed=time.monotonic()-started_dump
    dumpfp=fingerprint(dst)
    require(dumpfp==newfp,'Dump/restore and pg_upgrade differ')
    # Starting old COPY source proves it remains physically startable; NOT that it contains new target writes.
    uquery(name,"UPDATE shop.inventory SET reserved=reserved+1 WHERE product_id=1;")
    require(uquery(name,'SELECT reserved FROM shop.inventory WHERE product_id=1;')=='1','Target write not executed')
    ushell(name,f'/usr/lib/postgresql/18/bin/pg_ctl -D {work}/new -m fast -w stop')
    ushell(name,f"/usr/lib/postgresql/17/bin/pg_ctl -D {work}/old -l {work}/old-return.log -o '-p 55417 -k /tmp -c listen_addresses= -c shared_buffers=64MB' -w start")
    old_inventory=uquery(name,'SELECT reserved FROM shop.inventory WHERE product_id=1;',55417)
    require(old_inventory=='0','COPY source unexpectedly contains target-only write')
    ushell(name,f'/usr/lib/postgresql/17/bin/pg_ctl -D {work}/old -m fast -w stop')
    state['upgraded']=True;STATE.write_text(json.dumps(state,indent=2)+'\n')
    capacity=ushell(name,f'du -sb {work}/old {work}/new').stdout
    e.save('CH21/cluster-capacity.txt',capacity)
    return {'actual_pg_upgrade_copy':True,'copy_elapsed_seconds':elapsed,'actual_dump_restore_17_to18':True,
      'restore_elapsed_seconds_excludes_dump':dump_elapsed,'fingerprint_pg_upgrade':newfp,'fingerprint_dump_restore':dumpfp,
      'target_only_inventory_reservation':1,'old_copy_reservation_after_target_write':int(old_inventory),
      'return_limit':'Old COPY cluster starts, but target-only data is absent. A routing rollback would lose it without explicit reconciliation. Link mode not executed.',
      'capacity_du_bytes':capacity,'local_timings_only':True}

def wait_replication(src,dst,expected=None,timeout=30):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        ready=sql(dst,"SELECT count(*) FROM pg_subscription_rel WHERE srsubstate<>'r';")=='0'
        if ready and (expected is None or fingerprint(dst)==expected):return
        time.sleep(.1)
    raise LabError('Replication did not reach expected fingerprint within bounded wait')

def drop_subscription(dst):
    present=sql(dst,"SELECT count(*) FROM pg_subscription WHERE subname='lfb_book_sub';")
    if present=='1':sql(dst,'DROP SUBSCRIPTION lfb_book_sub;')

def logical(n,e):
    src=start('pg17');dst=start('restore18')
    drop_subscription(dst)
    sql(src,'DROP PUBLICATION IF EXISTS lfb_book_pub;')
    baseline=seed(src)
    sql(dst,'DROP SCHEMA IF EXISTS shop CASCADE;')
    ddl=run(['docker','exec',src,'pg_dump','-U','postgres','-d',DATABASE,'--schema=shop','--schema-only','--no-owner','--no-acl']).stdout
    raw_sql(dst,ddl)
    sql(src,"DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='lfb_repl') THEN CREATE ROLE lfb_repl LOGIN REPLICATION PASSWORD 'lfb_synthetic_repl_only'; END IF; END $$; GRANT CONNECT ON DATABASE lfb_book TO lfb_repl; GRANT USAGE ON SCHEMA shop TO lfb_repl; GRANT SELECT ON ALL TABLES IN SCHEMA shop TO lfb_repl; CREATE PUBLICATION lfb_book_pub FOR TABLE shop.customers,shop.products,shop.orders,shop.order_items,shop.payments,shop.inventory,shop.schema_versions,shop.migration_checkpoints;")
    # Fixed internal container hostname, fixed lab credential, never a production connection string.
    connection=f'host={src} port=5432 user=lfb_repl password=lfb_synthetic_repl_only dbname={DATABASE}'
    started=time.monotonic()
    sql(dst,f"CREATE SUBSCRIPTION lfb_book_sub CONNECTION '{connection}' PUBLICATION lfb_book_pub WITH (copy_data=true,create_slot=true,enabled=true);")
    wait_replication(src,dst,baseline)
    initial_elapsed=time.monotonic()-started
    # Delta consists of coherent order + item + payment change in one transaction.
    sql(src,"BEGIN; UPDATE shop.order_items SET unit_price_cents=unit_price_cents+10 WHERE order_id=1 AND line_no=1; UPDATE shop.orders SET total_cents=(SELECT sum(quantity::bigint*unit_price_cents) FROM shop.order_items WHERE order_id=1) WHERE id=1; UPDATE shop.payments SET amount_cents=(SELECT total_cents FROM shop.orders WHERE id=1) WHERE order_id=1; COMMIT;")
    delta=fingerprint(src);wait_replication(src,dst,delta)
    seq=sql(dst,"SELECT last_value FROM shop.orders_id_seq;")
    require(int(seq)<delta['orders'],'Expected sequence state not automatically replicated')
    sql(src,'ALTER TABLE shop.orders ADD COLUMN upgrade_note text;')
    ddl_count=sql(dst,"SELECT count(*) FROM information_schema.columns WHERE table_schema='shop' AND table_name='orders' AND column_name='upgrade_note';")
    require(ddl_count=='0','DDL unexpectedly replicated')
    # Explicit schema synchronization before publishing any non-null new-column values.
    sql(dst,'ALTER TABLE shop.orders ADD COLUMN upgrade_note text;')
    sql(src,"UPDATE shop.orders SET upgrade_note='nachgefuehrt' WHERE id=1;")
    deadline=time.monotonic()+20
    while sql(dst,'SELECT upgrade_note FROM shop.orders WHERE id=1;')!='nachgefuehrt':
        require(time.monotonic()<deadline,'New column delta did not apply');time.sleep(.1)
    tables=scalar_json(dst,"SELECT json_agg(row_to_json(x)) FROM (SELECT srrelid::regclass::text relation,srsubstate state FROM pg_subscription_rel ORDER BY srrelid) x;")
    state={'source':src,'target':dst,'baseline':baseline,'current':delta,'subscription':'lfb_book_sub','publication':'lfb_book_pub','initial_copy_seconds':initial_elapsed}
    LOGICAL_STATE.write_text(json.dumps(state,indent=2)+'\n')
    e.save('CH22/table-sync-state.json',tables)
    return {'source_version':sql(src,'SHOW server_version;'),'target_version':sql(dst,'SHOW server_version;'),
      'baseline':baseline,'after_delta':delta,'target_after_delta':fingerprint(dst),'initial_copy_seconds':initial_elapsed,
      'sequence_before_manual_sync':int(seq),'source_max_id':delta['orders'],'ddl_missing_until_manual_sync':True,
      'replica_identity':'primary keys on all published mutable relations; inventory uses product_id','tables':tables,
      'caveat':'Logical replication does not copy sequence state or execute DDL; neither is considered complete by row counts alone'}

def cutover(n,e):
    if not LOGICAL_STATE.exists():logical(n,e)
    s=json.loads(LOGICAL_STATE.read_text());src=s['source'];dst=s['target']
    assert_owned(src);assert_owned(dst)
    # Dedicated app login can mutate business data but cannot change its own grants.
    for server in (src,dst):
        sql(server,"DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='lfb_app') THEN CREATE ROLE lfb_app LOGIN; END IF; END $$; GRANT USAGE ON SCHEMA shop TO lfb_app; GRANT SELECT ON ALL TABLES IN SCHEMA shop TO lfb_app; REVOKE INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA shop FROM lfb_app;")
    sql(src,'GRANT INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA shop TO lfb_app;')
    denied=raw_sql(dst,'UPDATE shop.inventory SET reserved=reserved+1 WHERE product_id=1;',user='lfb_app',check=False)
    require('42501' in denied.stderr,'Target write gate open before cutover')
    # Deliberate no-go while source still writes: target money is temporarily changed with subscription paused.
    sql(dst,'ALTER SUBSCRIPTION lfb_book_sub DISABLE;')
    sql(dst,'UPDATE shop.orders SET total_cents=total_cents+1 WHERE id=2;')
    wrong=fingerprint(dst);source=fingerprint(src)
    require(wrong!=source,'Expected acceptance mismatch absent')
    e.save('CH23/aborted-cutover.json',{'decision':'no-go','source':source,'target':wrong,'source_kept_writer':True})
    sql(dst,'UPDATE shop.orders SET total_cents=total_cents-1 WHERE id=2; ALTER SUBSCRIPTION lfb_book_sub ENABLE;')
    wait_replication(src,dst,source)
    # Fence source app role before last equality check, then disable subscription and synchronize sequences.
    sql(src,'REVOKE INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA shop FROM lfb_app;')
    source_denied=raw_sql(src,'UPDATE shop.inventory SET reserved=reserved+1 WHERE product_id=1;',user='lfb_app',check=False)
    require('42501' in source_denied.stderr,'Source fence failed')
    wait_replication(src,dst,fingerprint(src))
    sql(dst,'ALTER SUBSCRIPTION lfb_book_sub DISABLE;')
    sql(dst,"SELECT setval(pg_get_serial_sequence('shop.orders','id'),(SELECT max(id) FROM shop.orders)); SELECT setval(pg_get_serial_sequence('shop.customers','id'),(SELECT max(id) FROM shop.customers)); SELECT setval(pg_get_serial_sequence('shop.products','id'),(SELECT max(id) FROM shop.products)); SELECT setval(pg_get_serial_sequence('shop.payments','id'),(SELECT max(id) FROM shop.payments));")
    require(fingerprint(src)==fingerprint(dst),'Final cutover fingerprint mismatch')
    sql(dst,'GRANT INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA shop TO lfb_app;')
    raw_sql(dst,'UPDATE shop.inventory SET reserved=reserved+1 WHERE product_id=1;',user='lfb_app')
    new_reserved=sql(dst,'SELECT reserved FROM shop.inventory WHERE product_id=1;')
    old_reserved=sql(src,'SELECT reserved FROM shop.inventory WHERE product_id=1;')
    require(int(new_reserved)==int(old_reserved)+1,'Target-only write not proved')
    # Real, deliberately narrow return reconciliation: fence target; bring target-only reservation back.
    sql(dst,'REVOKE INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA shop FROM lfb_app;')
    sql(src,'UPDATE shop.inventory SET reserved=reserved+1 WHERE product_id=1;')
    require(sql(src,'SELECT reserved FROM shop.inventory WHERE product_id=1;')==new_reserved,'Explicit reverse delta lost target data')
    sql(src,'GRANT INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA shop TO lfb_app;')
    # Both gates are checked using the actual restricted role.
    final_target_denied=raw_sql(dst,'UPDATE shop.inventory SET reserved=reserved+1 WHERE product_id=1;',user='lfb_app',check=False)
    require('42501' in final_target_denied.stderr,'Both writers allowed after return')
    drop_subscription(dst);sql(src,'DROP PUBLICATION lfb_book_pub;')
    LOGICAL_STATE.unlink(missing_ok=True)
    return {'no_go_reproduced':True,'source_fence_sqlstate':'42501','target_before_cutover_sqlstate':'42501',
      'target_only_reservation':int(new_reserved),'old_before_reconciliation':int(old_reserved),'returned_reservation':int(new_reserved),
      'sequence_order_last_value_after_sync':sql(dst,"SELECT last_value FROM shop.orders_id_seq;"),'final_single_writer':'source17 app role; target18 denied',
      'routing':'explicit app-role gates simulate routing decision; no real production router or DNS switch',
      'return_scope':'Only one recorded inventory delta explicitly reconciled. Arbitrary target writes require designed reverse migration; blind routing return is unsafe.'}

def dossier(n,e):
    started=time.monotonic()
    result=logical(n,e)
    before={'source':fingerprint(NAMES['pg17']),'target':fingerprint(NAMES['restore18'])}
    require(before['source']==before['target'],'E2E initial copy failed')
    changed=cutover(n,e)
    end={'source':fingerprint(NAMES['pg17']),'target':fingerprint(NAMES['restore18'])}
    require(end['source']==end['target'],'E2E end business fingerprint mismatch')
    return {'fresh_logical_run':True,'start_fingerprints':before,'end_fingerprints':end,'failed_acceptance_repaired':changed['no_go_reproduced'],
       'single_writer':changed['final_single_writer'],'elapsed_seconds':time.monotonic()-started,
       'decision':'go for bounded lab workflow after repair; no production readiness claim','limits':['small local fixture','no managed failover','no arbitrary reverse replication','no PITR rehearsal'],'logical':result,'cutover':changed}
