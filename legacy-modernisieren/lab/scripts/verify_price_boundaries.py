#!/usr/bin/env python3
"""Independent Decimal reference and actual HTTP quote boundary observations."""
import sys
if sys.flags.optimize:
 raise SystemExit('Price checks require Python without -O/-OO or PYTHONOPTIMIZE; no HTTP request was started.')
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
import urllib.request,json
root=Path(__file__).resolve().parents[1]
prices={'WARTUNG':'19.995','SENSOR':'7.125','PUMPE':'49.995'}
cases=[('WARTUNG',2,'TREUE'),('WARTUNG',3,'TREUE'),('PUMPE',2,'PARTNER'),('PUMPE',3,'PARTNER'),('WARTUNG',5,'PARTNER'),('WARTUNG',6,'PARTNER'),('SENSOR',3,'STANDARD')]
rows=[]
for n,(sku,q,g) in enumerate(cases,1):
 sub=(Decimal(prices[sku])*q).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
 rate=Decimal('.05') if g=='TREUE' and q>=3 else Decimal('.10') if g=='PARTNER' and sub>=100 else Decimal(0)
 disc=(sub*rate).quantize(Decimal('.01'),rounding=ROUND_HALF_UP);net=sub-disc;tax=(net*Decimal('.19')).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
 expected={k:int(v*100) for k,v in dict(subtotal_cents=sub,discount_cents=disc,net_cents=net,tax_cents=tax,total_cents=net+tax).items()}
 with urllib.request.urlopen(f'http://127.0.0.1:18890/v2/quote?sku={sku}&quantity={q}&customer_group={g}',timeout=5) as r: observed=json.load(r)
 assert observed==expected,(expected,observed)
 rows.append({'id':f'P{n}','sku':sku,'quantity':q,'customer_group':g,'expected_independent_decimal':expected,'observed_http':observed,'passed':True})
(root/'evidence/price-boundaries.json').write_text(json.dumps({'synthetic':True,'reference':'independent Python Decimal, not old Java implementation','observations':rows},ensure_ascii=False,indent=2)+'\n')
print(f'{len(rows)} independent price boundaries passed')
