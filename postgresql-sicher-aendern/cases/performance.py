"""CH13–15 and CH19: actual plans, false hypotheses and bounded connection pool."""
import concurrent.futures
import statistics
from lib import *
from cases.core import deadlock

def explain(n,query):
    return scalar_json(n,'EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+query)[0]

def nodes(plan):
    result=[plan['Node Type']]
    for p in plan.get('Plans',[]):result+=nodes(p)
    return result

def plans(n,e):
    seed(n)
    query='SELECT id,placed_at,total_cents FROM shop.orders WHERE customer_id=1700 ORDER BY placed_at DESC LIMIT 10;'
    before=explain(n,query)
    sql(n,'CREATE INDEX CONCURRENTLY orders_customer_placed_idx ON shop.orders(customer_id,placed_at DESC); ANALYZE shop.orders;')
    after=explain(n,query)
    e.save('CH13/before-plan.json',before);e.save('CH13/after-plan.json',after)
    require('Seq Scan' in nodes(before['Plan']),'Expected baseline heap scan')
    require(any('Index' in x for x in nodes(after['Plan'])),'Expected index access after change')
    sql(n,'PREPARE customer_orders(bigint) AS SELECT id FROM shop.orders WHERE customer_id=$1;') # per-connection example only
    # Safe write-plan demonstration: actual side effect stays in rolled-back transaction.
    old=sql(n,'SELECT reserved FROM shop.inventory WHERE product_id=1;')
    raw_sql(n,'BEGIN; EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) UPDATE shop.inventory SET reserved=reserved+1 WHERE product_id=1; ROLLBACK;')
    require(sql(n,'SELECT reserved FROM shop.inventory WHERE product_id=1;')==old,'EXPLAIN ANALYZE write escaped rollback')
    return {'query':query,'parameter':1700,'before_nodes':nodes(before['Plan']),'after_nodes':nodes(after['Plan']),
       'before_actual_rows':before['Plan']['Actual Rows'],'after_actual_rows':after['Plan']['Actual Rows'],
       'before_execution_ms':before['Execution Time'],'after_execution_ms':after['Execution Time'],
       'write_explain':'executed but rolled back; same final business state','scope':'One data state and parameter; no general index speedup promise'}

def statistics_case(n,e):
    sql(n,'CREATE INDEX IF NOT EXISTS orders_status_naive ON shop.orders(status); ANALYZE shop.orders;')
    counter=explain(n,"SELECT * FROM shop.orders WHERE status='bezahlt';")
    require('Seq Scan' in nodes(counter['Plan']),'Common-value counterexample did not use expected sequential scan')
    sql(n,'DROP TABLE IF EXISTS shop.stats_demo; CREATE TABLE shop.stats_demo(a int,b int,payload text); INSERT INTO shop.stats_demo SELECT g%100,g%100,repeat(\'x\',80) FROM generate_series(1,50000) g; ANALYZE shop.stats_demo;')
    q='SELECT * FROM shop.stats_demo WHERE a=42 AND b=42;'
    before=explain(n,q)
    sql(n,'CREATE STATISTICS shop.stats_demo_dependencies(dependencies,mcv) ON a,b FROM shop.stats_demo; ANALYZE shop.stats_demo;')
    after=explain(n,q)
    b=before['Plan'];a=after['Plan']
    require(abs(a['Plan Rows']-a['Actual Rows'])<abs(b['Plan Rows']-b['Actual Rows']),'Extended stats did not improve correlated estimate')
    sql(n,"CREATE INDEX IF NOT EXISTS orders_open_cover ON shop.orders(placed_at DESC) INCLUDE(total_cents) WHERE status='offen';")
    rare=explain(n,"SELECT placed_at,total_cents FROM shop.orders WHERE status='offen' ORDER BY placed_at DESC LIMIT 10;")
    # Write costs measured separately; rollback leaves no business change.
    write=raw_sql(n,"BEGIN; EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) UPDATE shop.orders SET status='offen' WHERE id=1; ROLLBACK;")
    e.save('CH14/common-value-counterexample.json',counter);e.save('CH14/stats-before.json',before);e.save('CH14/stats-after.json',after);e.save('CH14/partial-index-plan.json',rare);e.save('CH14/write-plan.txt',write.stdout)
    return {'false_hypothesis':'An index on status makes a query returning nearly all paid rows use index access','observed_nodes':nodes(counter['Plan']),
        'correlated_estimate_before':b['Plan Rows'],'correlated_estimate_after':a['Plan Rows'],'actual_rows':a['Actual Rows'],
        'partial_index_nodes':nodes(rare['Plan']),'write_cost':'separate raw EXPLAIN captured; no universal amplification ratio inferred'}

def pool_case(n,e):
    dl=deadlock(n,e)
    sessions=[PsqlSession(n,'lfb_ch15_pool_'+str(i)) for i in range(2)]
    available=queue.Queue()
    for s in sessions:available.put(s)
    timings=[]
    def task(i):
        started=time.monotonic();s=available.get();admitted=time.monotonic()
        try:
            r=s.query('SELECT pg_sleep(0.04); SELECT pg_backend_pid();')
            require(r['sqlstate']=='00000','Pooled query failed')
            return {'task':i,'queue_ms':(admitted-started)*1000,'execution_ms':(time.monotonic()-admitted)*1000,'output':r['stdout']}
        finally:
            s.query('ROLLBACK; RESET ALL; DEALLOCATE ALL;')
            available.put(s)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            timings=list(pool.map(task,range(8)))
        require(max(x['queue_ms'] for x in timings)>20,'Queue saturation not observed')
        # Session state leakage and reset on a persistent connection, not a new process.
        s=sessions[0]
        s.query("SET application_name='lfb_state_probe'; SET statement_timeout='1234ms'; PREPARE lfb_stmt AS SELECT 1;")
        dirty=s.query("SELECT current_setting('statement_timeout');")
        require(dirty['stdout']=='1234ms','Session state not retained')
        s.query('RESET ALL; DEALLOCATE ALL;')
        clean=s.query("SELECT current_setting('statement_timeout'); SELECT count(*) FROM pg_prepared_statements;")
        require(clean['stdout']=='0\n0','Pool reset did not clear state')
        # Bounded timeout and explicit rollback restore reusable transaction state.
        err=s.query("BEGIN; SET LOCAL statement_timeout='80ms'; SELECT pg_sleep(.5);")
        require(err['sqlstate']=='57014','Timeout SQLSTATE mismatch')
        aborted=s.query('SELECT 1;')
        require(aborted['sqlstate']=='25P02','Failed transaction did not remain aborted')
        s.query('ROLLBACK;')
        require(s.query('SELECT 1;')['stdout']=='1','Connection not reusable after rollback')
        e.save('CH15/pool-raw.json',timings)
        return {'deadlock':dl,'pool_size':2,'submitted_tasks':8,'persistent_connections':True,'max_queue_ms':max(x['queue_ms'] for x in timings),'raw_tasks':timings,
          'state_leak_before_reset':dirty,'after_reset':clean,'timeout_sqlstate':err['sqlstate'],'aborted_transaction_sqlstate':aborted['sqlstate'],
          'scope':'Minimal application-side persistent psql pool; not PgBouncer or a claim about transaction-pooling mode'}
    finally:
        for s in sessions:s.close()

def regression(n,e):
    seed(n)
    q='SELECT id,placed_at,total_cents FROM shop.orders WHERE customer_id=1700 ORDER BY placed_at DESC LIMIT 10;'
    before=[explain(n,q) for _ in range(3)]
    # A plausible wrong fix: index an unrelated field.
    sql(n,'CREATE INDEX orders_wrong_fix ON shop.orders(status); ANALYZE shop.orders;')
    wrong=explain(n,q)
    require('Seq Scan' in nodes(wrong['Plan']),'Wrong-hypothesis counterexample did not reproduce')
    sql(n,'DROP INDEX shop.orders_wrong_fix;')
    # Concurrent backfill load, observed session start before the accepted index build.
    writer=spawn_sql(n,"DO $$ BEGIN FOR i IN 1..50 LOOP UPDATE shop.orders SET updated_at=updated_at WHERE id BETWEEN i*100 AND i*100+20; PERFORM pg_sleep(.01); END LOOP; END $$;",'lfb_ch19_backfill')
    wait_activity(n,'lfb_ch19_backfill')
    sql(n,'CREATE INDEX CONCURRENTLY orders_customer_placed_idx ON shop.orders(customer_id,placed_at DESC); ANALYZE shop.orders;')
    require(finish(writer)['returncode']==0,'Concurrent maintenance failed')
    after=[explain(n,q) for _ in range(3)]
    require(all(any('Index' in x for x in nodes(p['Plan'])) for p in after),'Accepted fix plan not repeated')
    # Reversible experiment: remove, verify regressed shape, then restore accepted state.
    sql(n,'DROP INDEX CONCURRENTLY shop.orders_customer_placed_idx;')
    reverted=explain(n,q)
    require('Seq Scan' in nodes(reverted['Plan']),'Index rollback not observed')
    sql(n,'CREATE INDEX CONCURRENTLY orders_customer_placed_idx ON shop.orders(customer_id,placed_at DESC);')
    e.save('CH19/three-before-plans.json',before);e.save('CH19/wrong-hypothesis.json',wrong);e.save('CH19/three-after-plans.json',after);e.save('CH19/rollback-plan.json',reverted)
    return {'query':q,'before_ms':[p['Execution Time'] for p in before],'after_ms':[p['Execution Time'] for p in after],
       'false_hypothesis':'status index cannot supply customer filter/order','repeatable_acceptance':'three after plans use customer/order index','revert_test':'seq scan returns','concurrent_backfill':'executed','limit':'Not a production throughput replay; planner shape and local query times only'}
