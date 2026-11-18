"""CH07–12, CH17–18: executable migration units and failure paths."""
from lib import *

def expand(n):
    sql(n,(ROOT/'sql/expand.sql').read_text())
    sql(n,(ROOT/'sql/money_batch_function.sql').read_text())

def batch(n,size=1000):
    return scalar_json(n,(ROOT/'sql/backfill_batch.sql').read_text(),extra={'batch_size':size})

def fill(n):
    for _ in range(500):
        try:
            state=batch(n)
        except LabError as error:
            # Connection closes on error, rolling the whole attempt back.
            # Only bounded local timeout conflicts are retryable here.
            if '55P03' not in str(error) and '57014' not in str(error):raise
            time.sleep(.05)
            continue
        if state['finished']:return state
    raise LabError('Bounded backfill exceeded 500 batches')

def compatibility(n,e):
    seed(n)
    old="SELECT count(*) FROM shop.orders WHERE total_cents>=0;"
    new="SELECT count(*) FROM shop.orders WHERE coalesce(total_eur,total_cents::numeric/100)>=0;"
    v1old=raw_sql(n,old);v1new=raw_sql(n,new,check=False)
    require(v1old.returncode==0 and v1new.returncode!=0 and '42703' in v1new.stderr,'v1 compatibility expectation wrong')
    expand(n)
    v2old=raw_sql(n,old);v2new=raw_sql(n,new)
    require(v2old.stdout.strip()==v2new.stdout.strip()=='24000','v2 app results disagree')
    sql(n,'CREATE TABLE shop.active_app_versions(version int PRIMARY KEY); INSERT INTO shop.active_app_versions VALUES(1),(2);')
    guard="DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM shop.active_app_versions WHERE version=3) OR EXISTS(SELECT 1 FROM shop.active_app_versions WHERE version<>3) THEN RAISE EXCEPTION 'old or bridge client still active, or target absent'; END IF; END $$;"
    denied=raw_sql(n,guard,check=False)
    require(denied.returncode!=0 and 'old or bridge client still active' in denied.stderr,'Premature contract not rejected')
    fill(n)
    sql(n,'DELETE FROM shop.active_app_versions WHERE version=1;')
    bridge_denied=raw_sql(n,guard,check=False)
    require(bridge_denied.returncode!=0,'Contract must reject the remaining fallback/bridge client too')
    sql(n,'DELETE FROM shop.active_app_versions WHERE version=2; INSERT INTO shop.active_app_versions VALUES(3);')
    sql(n,guard)
    sql(n,(ROOT/'sql/money_roles.sql').read_text())
    sql(n,'GRANT USAGE ON SCHEMA shop TO lfb_money_old,lfb_money_backfill,lfb_money_target; GRANT SELECT ON shop.orders TO lfb_money_old,lfb_money_backfill,lfb_money_target; GRANT UPDATE(total_cents) ON shop.orders TO lfb_money_old; GRANT UPDATE(total_eur) ON shop.orders TO lfb_money_backfill;')
    raw_sql(n,'BEGIN; UPDATE shop.orders SET total_cents=total_cents WHERE id=1; ROLLBACK;',user='lfb_money_old')
    # Long scans are separate from the final ACCESS EXCLUSIVE cutover.
    sql(n,"ALTER TABLE shop.orders ADD CONSTRAINT final_total_eur_nonnegative CHECK(total_eur>=0 AND total_eur<>'NaN'::numeric) NOT VALID; ALTER TABLE shop.orders ADD CONSTRAINT final_total_eur_nn NOT NULL total_eur NOT VALID;")
    sql(n,'ALTER TABLE shop.orders VALIDATE CONSTRAINT final_total_eur_nonnegative;')
    sql(n,'ALTER TABLE shop.orders VALIDATE CONSTRAINT final_total_eur_nn;')
    sql(n,'REVOKE INSERT,UPDATE,DELETE ON shop.orders FROM lfb_money_old,lfb_money_backfill;')
    fenced=raw_sql(n,'UPDATE shop.orders SET total_cents=total_cents WHERE id=1;',user='lfb_money_old',check=False)
    require('42501' in fenced.stderr,'Old writer not fenced')
    sql(n,(ROOT/'sql/money_acceptance.sql').read_text())
    sql(n,"BEGIN ISOLATION LEVEL READ COMMITTED; SET LOCAL lock_timeout='500ms'; SET LOCAL statement_timeout='5s'; LOCK TABLE shop.active_app_versions IN SHARE MODE; LOCK TABLE shop.orders IN ACCESS EXCLUSIVE MODE;"+guard+" DO $$ BEGIN IF (SELECT count(*) FROM pg_constraint WHERE conrelid='shop.orders'::regclass AND conname IN ('final_total_eur_nonnegative','final_total_eur_nn') AND convalidated)<>2 THEN RAISE EXCEPTION 'target constraints not valid'; END IF; END $$; DROP TRIGGER sync_order_money ON shop.orders; ALTER TABLE shop.orders DROP COLUMN total_cents; INSERT INTO shop.schema_versions VALUES(3,'Contract nach Rollenfence und validiertem Zielvertrag'); COMMIT;")
    sql(n,'GRANT UPDATE(total_eur) ON shop.orders TO lfb_money_target;')
    require(sql(n,'SELECT count(*) FROM shop.orders WHERE total_eur IS NULL;')=='0','Contract lost prices')
    bridge_after=raw_sql(n,new,check=False)
    require('42703' in bridge_after.stderr,'Bridge query should no longer parse after old column removal')
    final_reader=sql(n,'SELECT count(*) FROM shop.orders WHERE total_eur>=0;')
    require(final_reader=='24000','Final EUR-only reader failed')
    previous=sql(n,'SELECT total_eur FROM shop.orders WHERE id=1;')
    written=sql(n,'BEGIN; UPDATE shop.orders SET total_eur=1.23 WHERE id=1; SELECT total_eur FROM shop.orders WHERE id=1; ROLLBACK;')
    require(written=='1.23' and sql(n,'SELECT total_eur FROM shop.orders WHERE id=1;')==previous,'Final EUR-only writer/rollback failed')
    invalid_final=raw_sql(n,'UPDATE shop.orders SET total_eur=-1 WHERE id=1;',check=False)
    require('23514' in invalid_final.stderr,'Final EUR amount constraint not enforced')
    nan_final=raw_sql(n,"UPDATE shop.orders SET total_eur='NaN' WHERE id=1;",check=False)
    require('23514' in nan_final.stderr,'Final NaN amount not rejected')
    null_final=raw_sql(n,'UPDATE shop.orders SET total_eur=NULL WHERE id=1;',check=False)
    require('23502' in null_final.stderr,'Final NULL amount not rejected')
    return {'matrix':[{'schema':1,'app':'old','expected':'works','actual_rc':v1old.returncode},{'schema':1,'app':'new','expected':'unsupported (undefined column)','actual_rc':v1new.returncode},{'schema':2,'app':'old','expected':'works','actual_rc':v2old.returncode},{'schema':2,'app':'new','expected':'works','actual_rc':v2new.returncode}],
            'premature_contract_error':denied.stderr,'bridge_still_active_refusal':bridge_denied.stderr,'bridge_after_contract_sqlstate':'42703',
            'final_app_version':3,'final_reader_rows':int(final_reader),'final_writer_temporary_value':written,'final_writer_rolled_back_to':previous,
            'final_negative_amount_sqlstate':'23514','final_nan_amount_sqlstate':'23514','final_null_amount_sqlstate':'23502','old_writer_fence_sqlstate':'42501','validation':'NOT VALID CHECK and named NOT NULL, separately validated before Contract',
            'contract_after_retirement':'succeeded after BOTH old and bridge clients retired','app_version_tracking':'explicit simulation; real deployment inventory must be supplied by production orchestration'}

def columns(n,e):
    seed(n)
    sql(n,'DROP TABLE IF EXISTS shop.ddl_demo; CREATE TABLE shop.ddl_demo(id int PRIMARY KEY,v integer); INSERT INTO shop.ddl_demo SELECT g,g FROM generate_series(1,10000) g;')
    before=sql(n,"SELECT pg_relation_filenode('shop.ddl_demo');")
    sql(n,'ALTER TABLE shop.ddl_demo ADD COLUMN country text NOT NULL DEFAULT \'DE\';')
    fast=sql(n,"SELECT pg_relation_filenode('shop.ddl_demo');")
    require(before==fast,'Constant default unexpectedly rewrote heap')
    sql(n,'CREATE VIEW shop.ddl_dependant AS SELECT v FROM shop.ddl_demo;')
    denied=raw_sql(n,'ALTER TABLE shop.ddl_demo DROP COLUMN v;',check=False)
    require(denied.returncode!=0 and '2BP01' in denied.stderr,'Expected dependency refusal')
    sql(n,"BEGIN; SET LOCAL lock_timeout='500ms'; SET LOCAL statement_timeout='10s'; DROP VIEW shop.ddl_dependant; ALTER TABLE shop.ddl_demo ALTER COLUMN v TYPE bigint; COMMIT;")
    rewritten=sql(n,"SELECT pg_relation_filenode('shop.ddl_demo');")
    require(rewritten!=fast,'integer to bigint rewrite not observed')
    require(sql(n,"SELECT count(*) FROM shop.ddl_demo WHERE country='DE' AND v=id;")=='10000','DDL corrupted values')
    return {'constant_default_heap_before':before,'constant_default_heap_after':fast,'type_change_heap_after':rewritten,'dependency_failure':denied.stderr,'source':'https://www.postgresql.org/docs/18/ddl-alter.html','limit':'Observed constant text default and int4→int8 only; volatile defaults and other conversions need separate tests'}

def backfill(n,e):
    seed(n);expand(n)
    first=batch(n,1000)
    require(first['last_id']==1000,'Unexpected first checkpoint')
    crash=raw_sql(n,"BEGIN; UPDATE shop.orders SET total_eur=total_cents::numeric/100 WHERE id BETWEEN 1001 AND 2000; UPDATE shop.migration_checkpoints SET last_id=2000 WHERE migration_id='money_v2'; SELECT 1/0; COMMIT;",check=False)
    require(crash.returncode!=0 and '22012' in crash.stderr,'Expected interrupted transaction')
    require(sql(n,"SELECT last_id FROM shop.migration_checkpoints WHERE migration_id='money_v2';")=='1000','Checkpoint escaped aborted transaction')
    sql(n,"CREATE FUNCTION shop.review_suppress_money() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.id=1001 THEN RETURN NULL; END IF; RETURN NEW; END $$; CREATE TRIGGER review_suppress_money BEFORE UPDATE ON shop.orders FOR EACH ROW EXECUTE FUNCTION shop.review_suppress_money();")
    suppressed=raw_sql(n,(ROOT/'sql/backfill_batch.sql').read_text(),extra={'batch_size':1000},check=False)
    require('P0001' in suppressed.stderr and 'incomplete batch RETURNING' in suppressed.stderr,'Suppressed update was not detected')
    require(sql(n,"SELECT last_id FROM shop.migration_checkpoints WHERE migration_id='money_v2';")=='1000','Suppressed update advanced checkpoint')
    require(sql(n,'SELECT count(*) FROM shop.orders WHERE id BETWEEN 1001 AND 2000 AND total_eur IS NOT NULL;')=='0','Suppression failure did not roll whole batch back')
    sql(n,'DROP TRIGGER review_suppress_money ON shop.orders; DROP FUNCTION shop.review_suppress_money();')
    missing=raw_sql(n,"BEGIN; DELETE FROM shop.migration_checkpoints WHERE migration_id='money_v2'; SELECT shop.money_v2_batch(1000); COMMIT;",check=False)
    require('P0002' in missing.stderr,'Missing checkpoint did not fail closed')
    before_total=int(sql(n,'SELECT sum(total_cents) FROM shop.orders;'))
    writer=spawn_sql(n,"DO $$ DECLARE k bigint; BEGIN FOR i IN 1..40 LOOP k:=1+((i*607)%24000); UPDATE shop.order_items SET unit_price_cents=unit_price_cents+1 WHERE order_id=k AND line_no=1; UPDATE shop.orders SET total_cents=(SELECT sum(quantity::bigint*unit_price_cents) FROM shop.order_items WHERE order_id=k),updated_at='2026-11-18T00:00:00Z' WHERE id=k; UPDATE shop.payments SET amount_cents=(SELECT total_cents FROM shop.orders WHERE id=k) WHERE order_id=k; PERFORM pg_sleep(0.05); END LOOP; END $$;",'lfb_ch09_writer')
    writer_observed=wait_activity(n,'lfb_ch09_writer',wait='Timeout')
    state=fill(n)
    wr=finish(writer)
    require(wr['returncode']==0,'Concurrent writer failed')
    mismatch=sql(n,'SELECT count(*) FROM shop.orders WHERE total_eur IS DISTINCT FROM total_cents::numeric/100;')
    require(mismatch=='0','Backfill left inconsistent money')
    again=batch(n)
    require(again==state,'Completed backfill is not idempotent')
    require(sql(n,"SELECT count(*) FROM shop.orders WHERE updated_at='2026-11-18T00:00:00Z';")=='40','Writer coverage lost')
    fp=fingerprint(n)
    require(fp['unbalanced_orders']==0 and fp['unbalanced_payments']==0 and fp['total_cents']>before_total,'Coherent monetary writes not reconciled')
    return {'first_checkpoint':first,'interruption_error':crash.stderr,'suppressed_update_sqlstate':'P0001','missing_checkpoint_sqlstate':'P0002','batch_timeout_policy':'500ms lock / 5s statement; bounded whole-transaction retry (max500 attempts) on55P03/57014 only','final_checkpoint':state,'money_mismatches':0,'concurrent_writer_rows':40,'writer_observed':writer_observed,
      'monetary_delta_cents':fp['total_cents']-before_total,'business_fingerprint_after_writes':fp,'rerun_unchanged':True,'limit':'Existing rows updated coherently; new inserts beyond a captured frontier are not exercised'}

def constraints(n,e):
    sql(n,'DROP TABLE IF EXISTS shop.constraint_demo; CREATE TABLE shop.constraint_demo(id int PRIMARY KEY,customer_id bigint,amount int); INSERT INTO shop.constraint_demo VALUES(1,1,10),(2,999999,-5);')
    sql(n,'ALTER TABLE shop.constraint_demo ADD CONSTRAINT positive_amount CHECK(amount>=0) NOT VALID; ALTER TABLE shop.constraint_demo ADD CONSTRAINT known_customer FOREIGN KEY(customer_id) REFERENCES shop.customers(id) NOT VALID;')
    new_bad=raw_sql(n,'INSERT INTO shop.constraint_demo VALUES(3,1,-1);',check=False)
    require('23514' in new_bad.stderr,'NOT VALID must still reject new bad rows')
    existing=raw_sql(n,'ALTER TABLE shop.constraint_demo VALIDATE CONSTRAINT positive_amount;',check=False)
    require('23514' in existing.stderr,'Existing bad data should block validation')
    sql(n,'UPDATE shop.constraint_demo SET amount=5,customer_id=2 WHERE id=2; ALTER TABLE shop.constraint_demo VALIDATE CONSTRAINT positive_amount; ALTER TABLE shop.constraint_demo VALIDATE CONSTRAINT known_customer;')
    valid=scalar_json(n,"SELECT json_object_agg(conname,convalidated) FROM pg_constraint WHERE conrelid='shop.constraint_demo'::regclass;")
    require(all(valid.values()),'Constraint validation incomplete')
    return {'new_write_rejected':new_bad.stderr,'old_data_validation_failed':existing.stderr,'repaired_constraints':valid,'scope':'CHECK and FK demonstrated; no claim that PostgreSQL 18 limits NOT VALID to these types'}

def indexes(n,e):
    sql(n,'DROP TABLE IF EXISTS shop.index_demo; CREATE TABLE shop.index_demo(id int PRIMARY KEY,business_key text NOT NULL); INSERT INTO shop.index_demo SELECT g,\'key-\'||g FROM generate_series(1,10000) g; INSERT INTO shop.index_demo VALUES(10001,\'key-1\');')
    failure=raw_sql(n,'CREATE UNIQUE INDEX CONCURRENTLY index_demo_key_unique ON shop.index_demo(business_key);',check=False)
    require(failure.returncode!=0 and '23505' in failure.stderr,'Unique CIC did not fail on duplicate')
    invalid=scalar_json(n,"SELECT json_build_object('valid',indisvalid,'ready',indisready,'unique',indisunique) FROM pg_index WHERE indexrelid='shop.index_demo_key_unique'::regclass;")
    require(invalid['valid'] is False,'Expected catalog-visible invalid index')
    # An invalid UNIQUE index can still enforce uniqueness: inspect, never infer safety from invalid alone.
    post_failure=raw_sql(n,"INSERT INTO shop.index_demo VALUES(10002,'key-2');",check=False)
    e.save('CH11/invalid-unique-write-probe.json',{'rc':post_failure.returncode,'stderr':post_failure.stderr})
    sql(n,'DROP INDEX CONCURRENTLY shop.index_demo_key_unique; DELETE FROM shop.index_demo WHERE id>=10001;')
    writer=spawn_sql(n,"DO $$ BEGIN FOR i IN 1..25 LOOP INSERT INTO shop.index_demo VALUES(20000+i,'writer-'||i); PERFORM pg_sleep(.01); END LOOP; END $$;",'lfb_ch11_writer')
    sql(n,'CREATE UNIQUE INDEX CONCURRENTLY index_demo_key_unique ON shop.index_demo(business_key);')
    require(finish(writer)['returncode']==0,'CIC write traffic failed')
    sql(n,'ALTER TABLE shop.index_demo ADD CONSTRAINT index_demo_key_constraint UNIQUE USING INDEX index_demo_key_unique;')
    duplicate=raw_sql(n,"INSERT INTO shop.index_demo VALUES(30000,'key-1');",check=False)
    require('23505' in duplicate.stderr,'Validated uniqueness not enforced')
    # A second, distinct failure occurs AFTER the index becomes ready for writes.
    # An old RR snapshot holds validation at its documented old-snapshot wait.
    from cases.core import gate
    sql(n,'DROP TABLE IF EXISTS shop.index_phase2; CREATE TABLE shop.index_phase2(id int PRIMARY KEY,business_key text); INSERT INTO shop.index_phase2 SELECT g,\'key-\'||g FROM generate_series(1,10000) g;')
    g=gate(n,71199,'lfb_ch11_phase2_gate')
    snapshot=spawn_sql(n,'BEGIN ISOLATION LEVEL REPEATABLE READ; SELECT count(*) FROM shop.index_phase2; SELECT pg_advisory_xact_lock(71199); COMMIT;','lfb_ch11_phase2_snapshot')
    wait_activity(n,'lfb_ch11_phase2_snapshot',wait='Lock')
    builder=spawn_sql(n,'CREATE UNIQUE INDEX CONCURRENTLY index_phase2_unique ON shop.index_phase2(business_key);','lfb_ch11_phase2_builder')
    try:
        deadline=time.monotonic()+20
        while True:
            phase=sql(n,"SELECT phase FROM pg_stat_progress_create_index p JOIN pg_stat_activity a USING(pid) WHERE a.application_name='lfb_ch11_phase2_builder';")
            if phase=='waiting for old snapshots':break
            require(time.monotonic()<deadline,'CIC did not reach old-snapshot wait');time.sleep(.05)
        sql(n,"SELECT pg_cancel_backend(pid) FROM pg_stat_activity WHERE application_name='lfb_ch11_phase2_builder';")
        cancelled=finish(builder)
        require(cancelled['returncode']!=0 and '57014' in cancelled['stderr'],'Expected phase-2 cancellation')
        phase2=scalar_json(n,"SELECT json_build_object('valid',indisvalid,'ready',indisready,'unique',indisunique) FROM pg_index WHERE indexrelid='shop.index_phase2_unique'::regclass;")
        require(phase2['ready'] is True and phase2['valid'] is False,'Expected ready-but-invalid unique index')
        enforced=raw_sql(n,"INSERT INTO shop.index_phase2 VALUES(20001,'key-1');",check=False)
        require('23505' in enforced.stderr,'Ready-but-invalid unique index did not enforce uniqueness')
    finally:
        terminate_app(n,'lfb_ch11_phase2_gate');finish(g);finish(snapshot)
        terminate_app(n,'lfb_ch11_phase2_builder')
    sql(n,'DROP INDEX CONCURRENTLY shop.index_phase2_unique;')
    return {'failure':failure.stderr,'invalid_catalog_state':invalid,'invalid_index_probe_sqlstate':'23505' if '23505' in post_failure.stderr else 'insert accepted','rebuild':'valid and attached to constraint','writer_rows':25,'duplicate_after_rebuild':duplicate.stderr,
       'cancelled_phase':phase,'phase2_catalog_state':phase2,'phase2_cancel':cancelled,'invalid_but_still_unique_sqlstate':'23505','phase2_cleanup':'DROP INDEX CONCURRENTLY after ending snapshot'}

def price_dossier(n,e):
    seed(n);baseline=fingerprint(n);expand(n)
    batch(n,500)
    no_go=int(sql(n,'SELECT count(*) FROM shop.orders WHERE total_eur IS NULL;'))
    require(no_go>0,'Aborted rollout must detect incomplete backfill')
    e.save('CH12/aborted-run.json',{'go':False,'reason':'unfilled new price field','missing_rows':no_go,'old_app_remains_readable':True})
    fill(n)
    require(sql(n,'SELECT sum(total_eur)*100 FROM shop.orders;')==str(baseline['total_cents'])+'.00','Price reconciliation failed')
    sql(n,'ALTER TABLE shop.orders ADD CONSTRAINT money_consistent CHECK(total_eur=total_cents::numeric/100) NOT VALID; ALTER TABLE shop.orders VALIDATE CONSTRAINT money_consistent;')
    wrong=raw_sql(n,'UPDATE shop.orders SET total_eur=0 WHERE id=1;',check=False)
    require('23514' in wrong.stderr,'Mismatch write not stopped')
    require(fingerprint(n)==baseline,'Money migration changed original business data')
    return {'aborted_at_missing':no_go,'resume':'completed','baseline_fingerprint':baseline,'after_fingerprint':fingerprint(n),'bad_new_price_rejected':wrong.stderr,'decision':'go for expanded read path; old column retained until actual client retirement'}

def partitions(n,e):
    sql(n,"DROP TABLE IF EXISTS shop.events_demo CASCADE; CREATE TABLE shop.events_demo(id bigint,occurred date NOT NULL,amount int NOT NULL CHECK(amount>=0)) PARTITION BY RANGE(occurred); CREATE TABLE shop.events_jan PARTITION OF shop.events_demo FOR VALUES FROM ('2026-01-01') TO ('2026-02-01'); CREATE TABLE shop.events_feb PARTITION OF shop.events_demo FOR VALUES FROM ('2026-02-01') TO ('2026-03-01'); CREATE TABLE shop.events_default PARTITION OF shop.events_demo DEFAULT; INSERT INTO shop.events_demo VALUES(1,'2025-12-31',10),(2,'2026-01-01',20),(3,'2026-01-31',30),(4,'2026-02-01',40),(5,'2026-03-01',50);")
    routes=scalar_json(n,"SELECT json_object_agg(id,tableoid::regclass::text) FROM shop.events_demo;")
    require(routes['2']=='shop.events_jan' and routes['4']=='shop.events_feb' and routes['5']=='shop.events_default','Partition boundary wrong')
    total=sql(n,'SELECT sum(amount) FROM shop.events_demo;')
    sql(n,'ALTER TABLE shop.events_demo DETACH PARTITION shop.events_jan;')
    detached=sql(n,'SELECT sum(amount) FROM shop.events_jan;')
    require(int(sql(n,'SELECT sum(amount) FROM shop.events_demo;'))+int(detached)==int(total),'Detach lost data')
    sql(n,"ALTER TABLE shop.events_demo ATTACH PARTITION shop.events_jan FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');")
    require(sql(n,'SELECT sum(amount) FROM shop.events_demo;')==total,'Reattach lost data')
    return {'routes':routes,'total_before_after':int(total),'detached_amount':int(detached),'note':'Boundary/default/detach/attach proved; no online repartitioning of existing orders or free conversion claim'}

def automated(n,e):
    sql(n,'CREATE TABLE IF NOT EXISTS shop.release_units(id text PRIMARY KEY,checksum text NOT NULL);')
    migration="ALTER TABLE shop.inventory ADD COLUMN IF NOT EXISTS last_counted date;"
    checksum=hashlib.sha256(migration.encode()).hexdigest()
    sql(n,migration+f"INSERT INTO shop.release_units VALUES('inventory_date','{checksum}') ON CONFLICT DO NOTHING;")
    sql(n,migration)
    require(sql(n,"SELECT checksum FROM shop.release_units WHERE id='inventory_date';")==checksum,'Migration receipt changed')
    failure=raw_sql(n,"BEGIN; ALTER TABLE shop.inventory ADD COLUMN should_rollback int; INSERT INTO shop.release_units VALUES('should_rollback','x'); SELECT 1/0; COMMIT;",check=False)
    require('22012' in failure.stderr,'Expected migration interruption')
    require(sql(n,"SELECT count(*) FROM information_schema.columns WHERE table_schema='shop' AND table_name='inventory' AND column_name='should_rollback';")=='0','DDL was not rolled back')
    require(sql(n,"SELECT count(*) FROM shop.release_units WHERE id='should_rollback';")=='0','Receipt escaped rollback')
    # Drift detection is separate from idempotent IF NOT EXISTS.
    expected_type='date'
    sql(n,'ALTER TABLE shop.inventory ALTER COLUMN last_counted TYPE text USING last_counted::text;')
    actual=sql(n,"SELECT data_type FROM information_schema.columns WHERE table_schema='shop' AND table_name='inventory' AND column_name='last_counted';")
    require(actual!=expected_type,'Drift injection not detected')
    sql(n,'ALTER TABLE shop.inventory ALTER COLUMN last_counted TYPE date USING last_counted::date;')
    return {'migration_checksum':checksum,'rerun':'safe','interrupted_transaction':'all DDL+receipt rolled back','drift_expected':expected_type,'drift_observed':actual,'drift_action':'stop, repair explicitly; not pretend IF NOT EXISTS is validation'}
