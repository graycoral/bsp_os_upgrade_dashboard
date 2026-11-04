"""Run packaged checks, isolating each independent SVG coordinate space."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PLUGIN = Path('C:/Users/grayc/.codex/plugins/cache/diagram-design/diagram-design/2.6.139')
CHECKS = ROOT / 'verification'
CHECKS.mkdir(exist_ok=True)
records = []
for file in sorted(ROOT.glob('bsp-system-*.html')):
    source = file.read_text(encoding='utf-8')
    result = subprocess.run([sys.executable, str(PLUGIN/'skills/diagram-design/scripts/self_check.py'), str(file)], capture_output=True, text=True)
    records.append(dict(file=file.name, check='self_check', exit_code=result.returncode, output=result.stdout+result.stderr))
    # verify-geometry.py treats every SVG in a document as one coordinate space.
    # Preserve each SVG unchanged and inspect separately to avoid cross-figure false positives.
    for i, svg in enumerate(re.findall(r'<svg\b[\s\S]*?</svg>', source)):
        part = CHECKS / f'{file.stem}-figure-{i+1}.html'
        part.write_text('<!doctype html><html><body>'+svg+'</body></html>',encoding='utf-8')
        result = subprocess.run([sys.executable, str(PLUGIN/'scripts/verify-geometry.py'), str(part)],capture_output=True,text=True)
        records.append(dict(file=file.name,figure=i+1,check='geometry',exit_code=result.returncode,output=result.stdout+result.stderr,svg_sha256=hashlib.sha256(svg.encode()).hexdigest()))
    records.append(dict(file=file.name,sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
(CHECKS/'checks.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
for r in records:
    if 'check' in r: print(r['file'],r.get('figure',''),r['check'],r['exit_code'],r['output'].strip())
sys.exit(int(any(r.get('exit_code',0) for r in records)))
