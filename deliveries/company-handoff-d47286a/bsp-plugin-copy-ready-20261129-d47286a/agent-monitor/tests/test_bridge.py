import json
import sys
from backend.adapters.bridge import Bridge
from backend.domain.policy import uid

def test_bridge_uses_stdin_without_shell_expansion(tmp_path):
    script=tmp_path/'adapter.py'
    script.write_text('import json,sys\np=json.load(sys.stdin)\nprint(json.dumps({"outcome":"SUCCEEDED","evidence":p["prompt"]}))\n')
    prompt='$(touch should-not-exist); `whoami`'
    result=Bridge().run([sys.executable,str(script)],{'prompt':prompt},str(tmp_path),5)
    assert result['evidence']==prompt
    assert not (tmp_path/'should-not-exist').exists()

def test_bridge_rejects_non_json_and_nonzero(tmp_path):
    for text in ['print("not json")','raise SystemExit(2)']:
        script=tmp_path/'adapter.py';script.write_text(text)
        assert Bridge().run([sys.executable,str(script)],{},str(tmp_path),5)['outcome']=='FAILED'

def test_bridge_timeout_reaps_process(tmp_path):
    script=tmp_path/'slow.py';script.write_text('import time\ntime.sleep(30)\n')
    r=Bridge().run([sys.executable,str(script)],{},str(tmp_path),.05)
    assert r['outcome']=='FAILED' and '시간 초과' in r['evidence']
