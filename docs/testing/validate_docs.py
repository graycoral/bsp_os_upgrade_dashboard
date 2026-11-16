from pathlib import Path
import re,csv,hashlib,json
r=Path(__file__).resolve().parents[2]
errors=[];links=0
for p in [r/'README.md', r/'AGENTS.md', r/'CLAUDE.md', *sorted((r/'.claude/agents').glob('*.md')), *sorted((r/'docs').rglob('*.md'))]:
 s=p.read_text()
 for target in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)',s):
  if '://' in target or target.startswith('#'):continue
  target=target.split('#')[0].strip('<>')
  if not target:continue
  links+=1
  if not (p.parent/target).exists():errors.append(f'broken link {p.relative_to(r)}: {target}')
req=set(re.findall(r'^\| (RQ-\d+) \|',(r/'docs/requirements/REQUIREMENTS.md').read_text(),re.M))
cat=(r/'docs/testing/TEST_CATALOG.md').read_text()
tids=re.findall(r'^\| (T-\d+) \|',cat,re.M)
covered=set(re.findall(r'RQ-\d+',cat))
if not tids or len(set(tids))!=len(tids):errors.append('test IDs not unique')
if not req or req!=covered:errors.append('requirement coverage mismatch')
results=list(csv.DictReader((r/'docs/testing/TEST_RESULTS.csv').open()))
if [x['test_id'] for x in results]!=tids:errors.append('results/catalog mismatch')
allowed={'NOT_RUN','PASS','FAIL','BLOCKED','SKIPPED','INVALIDATED'}
for x in results:
 if x['status'] not in allowed:errors.append('invalid status '+x['test_id'])
 if x['status'] in {'PASS','FAIL'} and any(not x[k] for k in ['run_id','code_revision','test_revision','environment','executed_at','executor','evidence']):errors.append('missing evidence '+x['test_id'])
if not (r/'AGENTS.md').exists() or not (r/'CLAUDE.md').exists():errors.append('instructions missing')
report={'status':'FAIL' if errors else 'PASS','relative_links_checked':links,'requirements':len(req),'test_cases':len(tids),'not_run':sum(x['status']=='NOT_RUN' for x in results),'errors':errors}
print(json.dumps(report,ensure_ascii=False,indent=2))
if errors:raise SystemExit(1)
