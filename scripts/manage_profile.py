"""Import/export profile JSON without editing application source or putting secrets in it."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.settings import Settings, Profile
from backend.storage.store import Store

p=argparse.ArgumentParser()
p.add_argument('operation', choices=['import','export','validate'])
p.add_argument('file')
p.add_argument('--runtime',default='.runtime')
a=p.parse_args()
if a.operation=='validate':
    Profile.model_validate_json(Path(a.file).read_text())
    print('Configuration valid')
else:
    settings=Settings(Store(Path(a.runtime)/'dashboard.db'))
    current=settings.get()
    if a.operation=='import':
        settings.save(current['version'],json.loads(Path(a.file).read_text()))
        print('Configuration imported for new jobs')
    else:
        Path(a.file).write_text(json.dumps(current['profile'],ensure_ascii=False,indent=2)+'\n')
        print('Configuration exported (credential references only)')
