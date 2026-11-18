#!/usr/bin/env python3
import datetime,hashlib,json,pathlib,platform,subprocess
r=pathlib.Path(__file__).resolve().parents[1]
def command(*a):
 p=subprocess.run(a,cwd=r,text=True,capture_output=True,check=True)
 return (p.stdout+p.stderr).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
sources={str(p.relative_to(r)):sha(p) for folder in ['src','sql','versions'] for p in sorted((r/folder).rglob('*')) if p.is_file()}
for n in ['Dockerfile','compose.yaml','lab.sh','scripts/run_scenarios.py','scripts/fetch_dependencies.py','scripts/verify_price_boundaries.py']:
 sources[n]=sha(r/n)
jar=command('docker','compose','exec','-T','app','sha256sum','havelblick.jar').split()[0]
java=command('docker','compose','exec','-T','app','java','-version')
pg=command('docker','compose','exec','-T','db','psql','-X','-U','hb_admin','-d','havelblick','-Atc','SELECT version()')
ids=command('docker','compose','ps','-q').splitlines()
containers=json.loads(command('docker','inspect',*ids))
runtime={'executed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'python':platform.python_version(),'java':java,'postgres':pg,'jar_sha256':jar,'source_sha256':sources,'source_set_sha256':hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest(),'container_memory_limit_bytes':sum(c['HostConfig']['Memory'] for c in containers),'containers':[{'name':c['Name'],'memory_limit':c['HostConfig']['Memory'],'image_id':c['Image'],'oom_killed':c['State']['OOMKilled'],'ports':c['NetworkSettings']['Ports']} for c in containers],'scope':'local private execution manifest, excluded from public source export'}
(r/'evidence/runtime-manifest.json').write_text(json.dumps(runtime,ensure_ascii=False,indent=2)+'\n')
public={'as_of':'2026-11-18','company':'Havelblick Technikservice; entirely fictional','original_code_license':'0BSD','stack':[
 {'component':'Eclipse Temurin JDK','version':'21.0.13+9-LTS','image':'eclipse-temurin:21.0.13_9-jdk-noble@sha256:06c1f157dacf6b68198bd9a4186dd4c34ef24e65d7bbbe2a0cf8e62571ad38c9','origin':'https://hub.docker.com/_/eclipse-temurin','primary_version_source':'https://adoptium.net/news/2026/10/eclipse-temurin-17021-21013-2505-2701-available','support_source':'https://adoptium.net/support','license':'GPL-2.0-with-classpath-exception plus included notices','redistributed':False,'acquisition':'official container pull, digest pinned','observed_runtime':java},
 {'component':'PostgreSQL','version':'18.7','image':'postgres:18.7@sha256:2ea8630df176ad090ec92136dee850397c5af8781e4bcf2e4162593691c61bbc','origin':'https://hub.docker.com/_/postgres','primary_version_source':'https://www.postgresql.org/docs/18/release-18-7.html','license':'PostgreSQL License plus image base notices','license_source':'https://www.postgresql.org/about/licence/','redistributed':False,'acquisition':'official container pull, digest pinned; tested arm64 digest','observed_runtime':pg},
 {'component':'pgJDBC','version':'42.7.14','origin':'https://jdbc.postgresql.org/download/postgresql-42.7.14.jar','primary_version_source':'https://jdbc.postgresql.org/download/','sha256':sha(r/'lib/postgresql-42.7.14.jar'),'license':'BSD-2-Clause','license_source':'https://github.com/pgjdbc/pgjdbc/blob/REL42.7.14/LICENSE','redistributed':False,'acquisition':'official download at build time; fixed SHA-256 enforced'},
 {'component':'OnGres SCRAM client/common','version':'3.2','origin':'embedded in original pgJDBC42.7.14 jar','license':'original BSD license files extracted under lab/licenses','redistributed':'license texts only; no binaries'},
 {'component':'OnGres SASLprep/Stringprep','version':'2.2','origin':'embedded in original pgJDBC42.7.14 jar','license':'original BSD license files extracted under lab/licenses','redistributed':'license texts only; no binaries'},
 {'component':'Python','version_observed':platform.python_version(),'origin':'https://www.python.org/','license':'PSF and bundled notices','redistributed':False,'third_party_packages':[]},
 {'component':'Build tools','version':'javac and jar from the same pinned JDK21.0.13+9 image','redistributed':False,'maven_gradle_used':False}],
 'primary_api_sources':[
 {'url':'https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html','section':'class contract, rounding, scale','supports':'decimal arithmetic and explicit rounding; Havelblick rounding order is our synthetic rule'},
 {'url':'https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html','section':'class contract and request handlers','supports':'bounded local JDK HTTP fixture, not production server certification'},
 {'url':'https://www.postgresql.org/docs/18/sql-select.html','section':'locking clause','supports':'row-lock and SKIP LOCKED syntax; not an exactly-once guarantee'},
 {'url':'https://www.postgresql.org/docs/18/explicit-locking.html','section':'advisory and row/table locks','supports':'explicit locking boundaries used in local fixture'},
 {'url':'https://www.postgresql.org/docs/18/transaction-iso.html','section':'READ COMMITTED and transaction visibility','supports':'transactional visibility context; concurrent protocols still need tests'},
 {'url':'https://spdx.org/licenses/0BSD.html','section':'license text','supports':'user-selected original-code license'}],
 'verification_boundary':'Versions checked against targeted official sections and observed containers. Not every upstream page was read fully; no production deployment or blanket security audit is claimed.',
 'platform_tested':'Docker Desktop / Linux aarch64 containers on macOS','resource_limit_bytes':runtime['container_memory_limit_bytes'],'original_source_set_sha256':runtime['source_set_sha256'],'jar_rebuild_sha256':jar,'runtime_binaries_in_public_release':False}
(r.parent/'research/lab-versions-and-sources.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n')
results=json.loads((r/'evidence/results.json').read_text());results['source_set_sha256']=runtime['source_set_sha256'];results['jar_sha256']=jar;(r/'evidence/results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'java':java,'postgres':pg,'source_set_sha256':runtime['source_set_sha256'],'jar_sha256':jar,'container_memory_limit_bytes':runtime['container_memory_limit_bytes']},ensure_ascii=False))
