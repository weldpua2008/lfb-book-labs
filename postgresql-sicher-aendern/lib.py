"""Safety-bounded Docker/psql primitives; Python standard library only."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import queue
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parent
PROJECT = 'lfb_pg_book_20261118'
LABEL = 'de.lfb.lab'
DATABASE = 'lfb_book'
NAMES = {k: f'{PROJECT}_{k}' for k in ('pg18','pg17','restore18','upgrade')}
NETWORK = PROJECT + '_net'
SIZES = {'small':2400,'standard':24000,'large':120000}
TRACE = None
TRACE_COUNTER = 0

class LabError(RuntimeError):
    pass

class SkipCase(Exception):
    pass

def require(condition, message):
    if not condition:
        raise LabError(message)

def run(args, *, input=None, timeout=120, check=True, binary=False):
    p = subprocess.run(args, input=input, capture_output=True, text=not binary, timeout=timeout)
    if check and p.returncode:
        err=p.stderr.decode(errors='replace') if binary else p.stderr
        raise LabError(f'command failed ({p.returncode}): {args[:5]}\n{err}')
    return p

def inspect(kind, name):
    p=run(['docker',kind,'inspect',name],check=False)
    return json.loads(p.stdout)[0] if p.returncode==0 else None

def assert_owned(name):
    require(name in NAMES.values(), 'Container name is outside the lab allowlist')
    obj=inspect('container',name)
    require(obj is not None, f'Missing lab container: {name}')
    require(obj['Config'].get('Labels',{}).get(LABEL)==PROJECT, 'Refusing container without exact ownership label')
    require(not obj['HostConfig'].get('PortBindings'), 'Lab must not publish host ports')
    return obj

def image_ref(version):
    lockpath=ROOT/'images.lock.json'
    lock=json.loads(lockpath.read_text()) if lockpath.exists() else {}
    tag=f'postgres:{version}'
    obj=inspect('image',tag)
    if obj is None:
        run(['docker','pull',tag],timeout=300)
        obj=inspect('image',tag)
    require(obj is not None and obj.get('Architecture')=='arm64', 'Expected observed arm64 official PostgreSQL image')
    digest=obj['RepoDigests'][0]
    if version in lock:
        require(lock[version]['repo_digest']==digest, 'Tag digest changed: review images.lock.json explicitly')
    else:
        lock[version]={'tag':tag,'repo_digest':digest,'image_id':obj['Id'],'architecture':obj['Architecture'],'size_bytes':obj['Size']}
        lockpath.write_text(json.dumps(lock,indent=2)+'\n')
    return digest

def ensure_network():
    obj=inspect('network',NETWORK)
    if obj:
        require(obj.get('Labels',{}).get(LABEL)==PROJECT and obj['Internal'], 'Network collision or non-internal network')
    else:
        run(['docker','network','create','--internal','--label',f'{LABEL}={PROJECT}',NETWORK])

def start(kind='pg18'):
    require(kind in ('pg18','pg17','restore18'), 'Not a server kind')
    ensure_network()
    name=NAMES[kind]
    obj=inspect('container',name)
    if obj:
        assert_owned(name)
        if not obj['State']['Running']:
            run(['docker','start',name])
    else:
        version='17.12' if kind=='pg17' else '18.7'
        image=image_ref(version)
        vol=name+'_data'
        existing=inspect('volume',vol)
        if existing:
            require(existing.get('Labels',{}).get(LABEL)==PROJECT,'Volume collision')
        else:
            run(['docker','volume','create','--label',f'{LABEL}={PROJECT}',vol])
        major=version.split('.')[0]
        run(['docker','run','-d','--name',name,'--label',f'{LABEL}={PROJECT}',
             '--network',NETWORK,'--memory','1g','--cpus','2','--pids-limit','256',
             '--mount',f'type=volume,source={vol},target=/var/lib/postgresql',
             *(['--tmpfs','/var/lib/postgresql/data:rw,size=1048576'] if kind=='pg17' else []),
             '-e','POSTGRES_PASSWORD=lfb_synthetic_lab_only','-e',f'POSTGRES_DB={DATABASE}',
             '-e',f'PGDATA=/var/lib/postgresql/{major}/data',
             image,'postgres','-c','wal_level=logical','-c','max_replication_slots=6',
             '-c','max_wal_senders=6','-c','shared_buffers=128MB','-c','max_connections=40',
             '-c','max_wal_size=256MB','-c','logging_collector=off'])
    for _ in range(120):
        ready=run(['docker','exec',name,'pg_isready','-U','postgres','-d',DATABASE],check=False)
        # The official entrypoint starts a temporary initialization server first.
        # It can answer pg_isready immediately before shutdown: wait for PID 1's final postgres.
        final_server=run(['docker','exec',name,'cat','/proc/1/comm'],check=False)
        if ready.returncode==0 and final_server.stdout.strip()=='postgres':
            break
        time.sleep(.1)
    else:
        raise LabError('PostgreSQL did not become ready')
    # Marker is in the dedicated database and never taken from user input.
    raw_sql(name,"CREATE TABLE IF NOT EXISTS public.lfb_lab_identity(id text PRIMARY KEY); "
             f"INSERT INTO public.lfb_lab_identity VALUES('{PROJECT}') ON CONFLICT DO NOTHING;")
    require(sql(name,'SELECT id FROM public.lfb_lab_identity;').strip()==PROJECT,'Database marker mismatch')
    expected='17.12' if kind=='pg17' else '18.7'
    require(sql(name,'SHOW server_version;').strip().startswith(expected),'Unexpected PostgreSQL runtime version')
    return name

def raw_sql(name, query, *, database=DATABASE, check=True, timeout=60, extra=None, app=None, user='postgres'):
    assert_owned(name)
    require(database in (DATABASE,'postgres','lfb_book_restore','lfb_book_upgrade'), 'Database outside allowlist')
    require(user in ('postgres','lfb_reader','lfb_app','lfb_repl','lfb_money_old','lfb_money_backfill','lfb_money_target'), 'Role outside allowlist')
    cmd=['docker','exec','-i']
    if app:
        cmd += ['-e',f'PGAPPNAME={app}']
    cmd += [name,'psql','-X','-q','-v','ON_ERROR_STOP=1','-v','VERBOSITY=verbose','-A','-t','-U',user,'-d',database]
    for key,value in (extra or {}).items():
        cmd += ['-v',f'{key}={value}']
    p=run(cmd,input=query,check=False,timeout=timeout)
    global TRACE_COUNTER
    if TRACE:
        TRACE_COUNTER+=1
        stem=TRACE/f'{TRACE_COUNTER:04d}'
        stem.with_suffix('.sql').write_text(query)
        stem.with_suffix('.json').write_text(json.dumps({'container':name,'database':database,'role':user,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr},indent=2)+'\n')
    if check and p.returncode:
        raise LabError(f'psql failed ({p.returncode}): {p.stderr}')
    return p

def sql(name,query,**kwargs):
    require(sql_marker(name),'Missing dedicated database marker')
    return raw_sql(name,query,**kwargs).stdout.strip()

def sql_marker(name):
    p=raw_sql(name,'SELECT id FROM public.lfb_lab_identity;',check=False)
    return p.returncode==0 and p.stdout.strip()==PROJECT

def scalar_json(name,query,**kwargs):
    return json.loads(sql(name,query,**kwargs))

def seed(name,size='standard'):
    require(size in SIZES,'Unknown fixture size')
    require(sql_marker(name),'Reset refused: marker mismatch')
    sql(name,(ROOT/'sql/fixture.sql').read_text(),extra={'order_count':SIZES[size]},timeout=120)
    return fingerprint(name)

def fingerprint(name,**kwargs):
    return scalar_json(name,(ROOT/'sql/fingerprint.sql').read_text(),**kwargs)

def spawn_sql(name,query,app,*,database=DATABASE):
    require(sql_marker(name),'Missing marker')
    cmd=['docker','exec','-i','-e',f'PGAPPNAME={app}',name,'psql','-X','-q','-v','ON_ERROR_STOP=1',
         '-v','VERBOSITY=verbose','-A','-t','-U','postgres','-d',database]
    p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    p.stdin.write(query)
    p.stdin.close()
    p.stdin=None
    p.lfb_query=query
    p.lfb_app=app
    return p

def wait_activity(name,app,*,wait=None,state=None,timeout=10):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        rows=scalar_json(name,"SELECT coalesce(json_agg(json_build_object('pid',pid,'state',state,'wait_event_type',wait_event_type,'wait_event',wait_event,'blockers',pg_blocking_pids(pid))),'[]'::json) FROM pg_stat_activity WHERE application_name='"+app+"';")
        if rows and (wait is None or rows[0]['wait_event_type']==wait) and (state is None or rows[0]['state']==state):
            return rows[0]
        time.sleep(.05)
    raise LabError(f'Session did not reach expected activity: {app}, {wait}, {state}')

def finish(p,timeout=20):
    out,err=p.communicate(timeout=timeout)
    result={'returncode':p.returncode,'stdout':out,'stderr':err}
    if TRACE:
        stem=TRACE/('session-'+p.lfb_app)
        stem.with_suffix('.sql').write_text(p.lfb_query)
        stem.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def terminate_app(name,app):
    # Exact, fixed prefix; never terminate arbitrary sessions.
    require(app.startswith('lfb_'),'Application name outside allowlist')
    return sql(name,"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='"+app+"';")

class PsqlSession:
    """A real persistent DB connection, controlled over psql stdin/stdout."""
    def __init__(self,name,app):
        require(sql_marker(name),'Missing database marker')
        self.app=app
        self.process=subprocess.Popen(['docker','exec','-i','-e',f'PGAPPNAME={app}',name,'psql','-X','-q','-A','-t','-v','VERBOSITY=verbose','-U','postgres','-d',DATABASE],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        self.lines=queue.Queue();self.errors=[]
        def reader():
            for line in self.process.stdout:self.lines.put(line.rstrip('\n'))
        def errors():
            for line in self.process.stderr:self.errors.append(line)
        threading.Thread(target=reader,daemon=True).start()
        threading.Thread(target=errors,daemon=True).start()
    def query(self,query,timeout=20):
        marker='lfb_end_'+uuid.uuid4().hex
        self.process.stdin.write(query+'\n\\echo '+marker+' :SQLSTATE\n')
        self.process.stdin.flush()
        lines=[];deadline=time.monotonic()+timeout
        while True:
            try:line=self.lines.get(timeout=max(.01,deadline-time.monotonic()))
            except queue.Empty:raise LabError('Persistent psql session query timed out')
            if line.startswith(marker):
                state=line.split()[-1]
                result={'stdout':'\n'.join(lines),'sqlstate':state,'stderr_so_far':''.join(self.errors)}
                if TRACE:
                    (TRACE/f'{self.app}-{marker}.json').write_text(json.dumps({'sql':query,**result},indent=2)+'\n')
                return result
            lines.append(line)
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.write('ROLLBACK;\n\\q\n');self.process.stdin.flush()
            self.process.wait(timeout=10)

class Evidence:
    def __init__(self,folder=None):
        stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:6]
        self.path=folder or ROOT/'outputs'/stamp
        self.path.mkdir(parents=True,exist_ok=True)
        self.results=[]
        self.source_hashes={}
        for p in ROOT.rglob('*'):
            if not p.is_file() or 'outputs' in p.relative_to(ROOT).parts or '__pycache__' in p.parts:
                continue
            if p.suffix in ('.py','.sql','.md','.json') or p.name.startswith('Dockerfile') or p.name in ('.gitignore','.dockerignore'):
                relative=str(p.relative_to(ROOT))
                self.save('source/'+relative,p.read_bytes())
                self.source_hashes[relative]=hashlib.sha256(p.read_bytes()).hexdigest()
        self.save('source-manifest.json',{'captured':'before case execution','sha256':self.source_hashes})
    def save(self,name,value):
        path=self.path/name
        path.parent.mkdir(parents=True,exist_ok=True)
        if isinstance(value,bytes): path.write_bytes(value)
        elif isinstance(value,str): path.write_text(value)
        else: path.write_text(json.dumps(value,indent=2,ensure_ascii=False,default=str)+'\n')
        return path
    def case(self,identifier,title,fn):
        global TRACE, TRACE_COUNTER
        TRACE=self.path/identifier/'trace'
        TRACE.mkdir(parents=True,exist_ok=True)
        TRACE_COUNTER=0
        t=time.monotonic()
        try:
            details=fn()
            status='pass'
        except SkipCase as e:
            details={'reason':str(e)};status='skip'
        except Exception as e:
            details={'error':str(e),'type':type(e).__name__};status='fail'
        row={'id':identifier,'title':title,'status':status,'elapsed_seconds':round(time.monotonic()-t,6),'details':details}
        TRACE=None
        self.results.append(row)
        self.save(identifier+'/result.json',row)
        print(f'{identifier}: {status} ({row["elapsed_seconds"]:.3f}s)',flush=True)
        self.write_summary()
        return row
    def write_summary(self):
        summary={'project':PROJECT,'captured_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                 'illustrative_local_timings_only':True,
                 'source_drift':[name for name,digest in self.source_hashes.items() if not (ROOT/name).exists() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest],
                 'results':self.results}
        self.save('summary.json',summary)
        self.save('SUMMARY.md','# Tatsächlich ausgeführte Laborfälle\n\nLokale Messungen, keine Produktionsgarantie.\n\n| Fall | Ergebnis | Sekunden |\n|---|---|---:|\n'+''.join(f'| {r["id"]} {r["title"]} | {r["status"]} | {r["elapsed_seconds"]} |\n' for r in self.results))
        by_id={r['id']:r for r in self.results if r['status']=='pass'}
        report='# Lesbare Messwerte dieses Laufs\n\nLokales Docker-Labor; keine Produktionsprognose. Rohdaten und exakte SQL stehen neben den Kapitelresultaten.\n'
        if 'CH03' in by_id:
            report+='\n## CH03 – zwei Clients, fester Mix\n\n| Lauf | Samples | Median ms | p95 ms | Maximum ms | Fehler |\n|---|---:|---:|---:|---:|---:|\n'
            for r in by_id['CH03']['details']['runs']:
                report+=f'| {r["trial"]} | {r["psql_statement_samples"]} | {r["median_ms"]:.3f} | {r["p95_ms"]:.3f} | {r["max_ms"]:.3f} | {r["error_count"]} |\n'
        if 'CH13' in by_id:
            r=by_id['CH13']['details']
            report+=f'\n## CH13 – konkrete Query, Kunde 1700\n\nVorher: {r["before_nodes"]}, {r["before_execution_ms"]} ms. Nachher: {r["after_nodes"]}, {r["after_execution_ms"]} ms. Ein Parameter und Datenzustand, kein allgemeiner Beschleunigungsfaktor.\n'
        if 'CH19' in by_id:
            r=by_id['CH19']['details'];report+=f'\n## CH19 – drei Wiederholungen\n\nVorher (ms): {r["before_ms"]}. Nachher (ms): {r["after_ms"]}. Die falsche Statusindex-Hypothese wurde separat widerlegt; Rücknahme reproduzierte den ursprünglichen Plan.\n'
        if 'CH21' in by_id:
            r=by_id['CH21']['details'];report+=f'\n## CH21 – echte Upgradewege\n\npg_upgrade --copy: {r["copy_elapsed_seconds"]:.3f} s. Separater Restore (Dump-Erstellung nicht enthalten): {r["restore_elapsed_seconds_excludes_dump"]:.3f} s. Beide Fachfingerabdrücke gleich. Nach Zielschreibvorgang Reservierung {r["target_only_inventory_reservation"]}; alter COPY-Cluster weiterhin {r["old_copy_reservation_after_target_write"]}.\n'
        self.save('MEASUREMENTS.md',report)
        (ROOT/'outputs/latest.json').write_text(json.dumps({'directory':str(self.path.relative_to(ROOT))})+'\n')
    def accept_complete_run(self):
        summary=json.loads((self.path/'summary.json').read_text())
        if {r['id'] for r in self.results}!={f'CH{i:02d}' for i in range(1,25)}:return False
        if any(r['status']!='pass' for r in self.results) or summary['source_drift']:return False
        require((self.path/'end-environment.json').exists(),'Cannot accept without end manifest')
        pointer={'directory':str(self.path.relative_to(ROOT)),'all_24_cases':'pass','source_drift':[],
          'summary_sha256':hashlib.sha256((self.path/'summary.json').read_bytes()).hexdigest(),
          'source_manifest_sha256':hashlib.sha256((self.path/'source-manifest.json').read_bytes()).hexdigest()}
        (ROOT/'outputs/accepted-run.json').write_text(json.dumps(pointer,indent=2)+'\n')
        return True

def environment(name):
    obj=assert_owned(name)
    return {'project':PROJECT,'python':platform.python_version(),'host':platform.platform(),
      'docker':json.loads(run(['docker','version','--format','{{json .Server}}']).stdout),
      'container':name,'image_id':obj['Image'],'image_reference':obj['Config']['Image'],
      'memory_limit_bytes':obj['HostConfig']['Memory'],'cpu_nano':obj['HostConfig']['NanoCpus'],
      'network':NETWORK,'published_ports':obj['HostConfig'].get('PortBindings'),
      'postgres_version':sql(name,'SELECT version();'),'server_settings':scalar_json(name,"SELECT json_object_agg(name,setting) FROM pg_settings WHERE name IN ('wal_level','shared_buffers','max_connections','max_wal_size','server_encoding','lc_collate','lc_ctype');"),
      'db_size_bytes':int(sql(name,'SELECT pg_database_size(current_database());')),
      'lab_output_bytes':sum(p.stat().st_size for p in (ROOT/'outputs').rglob('*') if p.is_file()),
      'resource_budget':resource_budget()}

def resource_budget():
    """Conservative sum of owned data + full image sizes (shared layers count twice)."""
    containers=[];images={}
    names=run(['docker','ps','-a','--filter',f'label={LABEL}={PROJECT}','--format','{{.Names}}']).stdout.splitlines()
    for name in names:
        obj=assert_owned(name)
        data=0
        if obj['State']['Running']:
            p=run(['docker','exec',name,'du','-sb','/var/lib/postgresql'],check=False)
            if p.returncode==0:data=int(p.stdout.split()[0])
        containers.append({'name':name,'memory_limit_bytes':obj['HostConfig']['Memory'],'data_bytes':data})
        im=inspect('image',obj['Image'])
        if im:images[obj['Image']]=im['Size']
    output_bytes=sum(p.stat().st_size for p in (ROOT/'outputs').rglob('*') if p.is_file())
    estimated=sum(c['data_bytes'] for c in containers)+sum(images.values())+output_bytes
    memory=sum(c['memory_limit_bytes'] for c in containers)
    require(memory<=6*1024**3,'PG lab exceeds its 6 GiB declared memory envelope')
    require(estimated<=25*1024**3,'Lab data/image/output estimate exceeds initial 25 GiB cap')
    return {'containers':containers,'memory_limit_sum_bytes':memory,'memory_cap_bytes':6*1024**3,
      'full_image_sizes_bytes':images,'output_bytes':output_bytes,'conservative_working_disk_bytes':estimated,
      'disk_cap_bytes':25*1024**3,'scope':'Owned active data directories, full referenced image sizes, output artifacts. Shared image layers double-counted; not host-wide Docker usage.'}
