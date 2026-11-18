#!/usr/bin/env python3
"""Kanonische Offline-Labor-CLI. Siehe README.md für Grenzen und Besitzprüfung."""
from __future__ import annotations
import argparse
import sys
import zipfile
from lib import *
from cases import core, migrations, performance

CHAPTERS=[
 ('CH01','Änderungskarte: Go und absichtliches No-go',core.decision),
 ('CH02','Deterministischer Seed und Manifest',core.fixture),
 ('CH03','Drei Ausgangsläufe mit zwei Clients',core.workload),
 ('CH04','Snapshots und Transaktionsrollback',core.snapshots),
 ('CH05','Lockgraph und zwei Timeout-Arten',core.locks),
 ('CH06','Dump/Restore in getrennte Instanz',core.restore),
 ('CH07','App-/Schema-Kompatibilität und Contract-Sperre',migrations.compatibility),
 ('CH08','Konstanter Default, Rewrite und Abhängigkeit',migrations.columns),
 ('CH09','Abgebrochener und fortgesetzter Backfill',migrations.backfill),
 ('CH10','NOT VALID: neue Schreibvorgänge und Altbestand',migrations.constraints),
 ('CH11','CIC-Fehler, ungültiger Index und Reparatur',migrations.indexes),
 ('CH12','Preismodell: No-go, Wiederaufnahme, Abnahme',migrations.price_dossier),
 ('CH13','Reale Query-Pläne vor/nach Indexänderung',performance.plans),
 ('CH14','Falscher Index und erweiterte Statistiken',performance.statistics_case),
 ('CH15','Deadlock und persistenter Zweier-Verbindungspool',performance.pool_case),
 ('CH16','VACUUM mit festgehaltenem Snapshot',core.vacuum),
 ('CH17','Partitionsgrenzen, Default und An-/Abhängen',migrations.partitions),
 ('CH18','Migrationseinheit, Fehlerrollback und Drift',migrations.automated),
 ('CH19','Regressionsdossier mit drei Nachmessungen',performance.regression),
]

def upgrade_case(which):
    def invoke(n,e):
        from cases import upgrades
        return getattr(upgrades,which)(n,e)
    return invoke

def restore_with_physical(n,e):
    result=core.restore(n,e)
    result['physical_full_backup']=core.physical_backup(n,e)
    return result

CHAPTERS=[(i,t,restore_with_physical if i=='CH06' else fn) for i,t,fn in CHAPTERS]

CHAPTERS += [
 ('CH20','17→18-Vorabprüfung und Erweiterungsinventar',upgrade_case('preflight')),
 ('CH21','Tatsächlicher pg_upgrade-Kopierlauf und Dump/Restore',upgrade_case('upgrade')),
 ('CH22','Logische Replikation mit DDL-/Sequenzgrenzen',upgrade_case('logical')),
 ('CH23','Single Writer, Umschaltung und kontrollierter Abbruch',upgrade_case('cutover')),
 ('CH24','End-to-End-Migrationsnachweis mit absichtlichem No-go',upgrade_case('dossier')),
]

def export():
    latest=json.loads((ROOT/'outputs/latest.json').read_text())
    folder=ROOT/latest['directory']
    require(folder.resolve().is_relative_to((ROOT/'outputs').resolve()),'Unsafe evidence path')
    sums={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file() and p.name!='checksums.json'}
    (folder/'checksums.json').write_text(json.dumps(sums,indent=2)+'\n')
    target=ROOT/'outputs'/(folder.name+'.zip')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():z.write(p,str(p.relative_to(folder)))
    print(target)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['preflight','fixture','reset','run-suite','export','status'])
    parser.add_argument('--size',choices=SIZES,default='standard')
    parser.add_argument('--only',help='Kommagetrennte IDs CH01..CH24')
    parser.add_argument('--include-upgrades',action='store_true',help='Zusätzliche eigene Container für CH20..24 tatsächlich ausführen')
    args=parser.parse_args()
    if args.command=='export':export();return
    if args.command=='status':
        print(run(['docker','ps','-a','--filter',f'label={LABEL}={PROJECT}','--format','{{.Names}}\t{{.Status}}']).stdout)
        return
    n=start()
    if args.command=='preflight':
        print(json.dumps(environment(n),indent=2));return
    e=Evidence()
    initial=seed(n,args.size)
    e.save('initial-fingerprint.json',initial)
    e.save('environment.json',environment(n))
    if args.command in ('fixture','reset'):
        print(json.dumps(initial,indent=2));e.write_summary();return
    require(args.size=='standard','Chapter acceptance currently fixed to standard size; use fixture for size experiments')
    selected=set(args.only.upper().split(',')) if args.only else {x[0] for x in CHAPTERS}
    require(selected<={x[0] for x in CHAPTERS},'Unknown chapter identifier')
    for identifier,title,fn in CHAPTERS:
        if identifier not in selected:continue
        if int(identifier[2:])>=20 and not args.include_upgrades:
            def skip():raise SkipCase('Not run: pass --include-upgrades for isolated additional containers')
            e.case(identifier,title,skip)
        else:e.case(identifier,title,lambda fn=fn:fn(n,e))
    e.save('end-environment.json',environment(n))
    e.write_summary()
    if e.accept_complete_run():print('Accepted: all 24 cases passed with unchanged source snapshot.')
    print(e.path)
    if any(r['status']=='fail' for r in e.results):sys.exit(1)

if __name__=='__main__':
    main()
