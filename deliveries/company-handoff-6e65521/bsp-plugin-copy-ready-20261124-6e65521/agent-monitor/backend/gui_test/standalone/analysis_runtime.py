"""Persistent failure analysis in the existing worker, with trusted local adapters.

Adapter programs consume a JSON request file and print one JSON result. They are
registered by the installer/OS owner, never by analysis output or browser input.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Literal

from pydantic import Field, model_validator

from ..core.models import StrictModel, TestError, digest, now
from ..core.failure_analysis import AnalysisResult
from ..connector.logs import redact
from ..execution.process import ProcessTree


class AdapterCommand(StrictModel):
    argv: list[str] = Field(min_length=2, max_length=32)
    files: dict[str, str]
    timeout_seconds: int = Field(default=60, strict=True, ge=1, le=240)

    @model_validator(mode='after')
    def validate_command(self):
        if not Path(self.argv[0]).is_absolute() or self.argv.count('{request_file}') != 1:
            raise ValueError('Use an absolute executable and one {request_file} argument')
        if any(not a or len(a)>4096 or '\x00' in a for a in self.argv):
            raise ValueError('Invalid adapter arguments')
        if self.argv[0] not in self.files or not self.files or len(self.files)>32:
            raise ValueError('Pin the executable and adapter files by SHA256')
        for name, value in self.files.items():
            if not Path(name).is_absolute() or not re.fullmatch('[a-f0-9]{64}', value):
                raise ValueError('Invalid pinned adapter file')
        for arg in self.argv:
            if Path(arg).is_absolute() and Path(arg).is_file() and arg not in self.files:
                raise ValueError('Every executable/script file argument must be pinned')
        return self


class AutomationSettings(StrictModel):
    enabled: bool = Field(default=True, strict=True)
    mode: Literal['builtin', 'command', 'external'] = 'builtin'
    analyzer: AdapterCommand | None = None
    verifier: AdapterCommand | None = None
    interval_seconds: int = Field(default=2, strict=True, ge=1, le=300)

    @model_validator(mode='after')
    def check_provider(self):
        if self.mode == 'command' and self.analyzer is None:
            raise ValueError('Command analysis requires a registered analyzer')
        return self


def settings(path):
    path=Path(path)
    if not path.exists(): return AutomationSettings()
    if path.stat().st_size>65536: raise ValueError('Analysis configuration exceeds 64 KiB')
    return AutomationSettings.model_validate_json(path.read_bytes())


def sanitized(value):
    if isinstance(value, dict):
        return {k:sanitized(v) for k,v in value.items()
                if not any(word in k.casefold() for word in ('token','password','credential','secret'))}
    if isinstance(value, list): return [sanitized(v) for v in value]
    return redact(value) if isinstance(value,str) else value


def context(item):
    run=item['run']
    attempts=[]
    for a in run['attempts']:
        if a['id'] != item.get('attempt_id'): continue
        attempts.append({k:(redact(v)[-16384:] if k in {'stdout','stderr'} else v) for k,v in a.items()
                         if k in {'id','tc_id','state','reason','exit_code','terminated','stdout','stderr','console_evidence'}})
    meta = run.get('integration') or {}
    receipt = meta.get('receipt') or {}
    evidence = {k: meta[k] for k in ('phase', 'batch_id', 'diagnostic', 'request',
                                   'config_revision', 'preparation_id') if k in meta}
    evidence['inputs'] = {k: receipt[k] for k in ('source_snapshot', 'installer_snapshot') if k in receipt}
    if 'batch' in meta:
        evidence['batch'] = meta['batch']
    evidence, truncated = bounded_evidence(evidence)
    return sanitized({'contract':'failure-analysis-v1',
        'analysis':{k:v for k,v in item.items() if k not in {'lease_token','run'}},
        'run':{k:run.get(k) for k in ('id','state','source_revision','command_snapshot','connection_snapshot','retry_chain','reason')},
        'attempts':attempts, 'integration': evidence, 'integration_evidence_truncated': truncated})


def bounded_evidence(value):
    """Keep failure tails and snapshot references without passing an unbounded batch.

    The full evidence stays in the Run API. The command adapter gets at most
    64 KiB of strings, 512 nodes, eight levels and the last 32 list entries.
    Redact before cutting strings so truncation cannot expose credential tails.
    """
    remaining, nodes, truncated = 65536, 512, False

    def visit(item, depth=0):
        nonlocal remaining, nodes, truncated
        if depth > 8 or nodes <= 0 or remaining <= 0:
            truncated = True
            return '[TRUNCATED]'
        nodes -= 1
        if isinstance(item, dict):
            result = {}
            for key, child in item.items():
                if any(word in key.casefold() for word in ('token', 'password', 'credential', 'secret', 'private_key')):
                    continue
                if nodes <= 0 or remaining <= 0 or len(result) >= 64:
                    truncated = True
                    break
                result[key[:128]] = visit(child, depth + 1)
            return result
        if isinstance(item, list):
            truncated |= len(item) > 32
            result = []
            for child in item[-32:]:
                if nodes <= 0 or remaining <= 0:
                    truncated = True
                    break
                result.append(visit(child, depth + 1))
            return result
        if isinstance(item, str):
            raw = redact(item).encode('utf-8')
            limit = min(16384, remaining)
            truncated |= len(raw) > limit
            output = raw[-limit:].decode('utf-8', errors='ignore')
            remaining -= len(output.encode('utf-8'))
            return output
        return item

    result = visit(value)
    return result, truncated


def invoke(command, payload, home):
    """Use existing process containment and bounded private temporary files."""
    for name, checksum in command.files.items():
        path=Path(name)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=checksum:
            raise TestError('Registered analysis adapter changed', 'ANALYSIS_ADAPTER_CHANGED')
    home=Path(home);home.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='analysis-',dir=home) as directory:
        folder=Path(directory);request=folder/'request.json'
        request.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8');request.chmod(0o600)
        argv=[str(request) if a=='{request_file}' else a for a in command.argv]
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            tree=ProcessTree(argv,folder,out,err)
            deadline=time.monotonic()+command.timeout_seconds
            problem=None
            try:
                while not tree.stopped():
                    if time.monotonic()>=deadline: problem='ANALYSIS_ADAPTER_TIMEOUT'
                    if os.fstat(out.fileno()).st_size+os.fstat(err.fileno()).st_size>262144:
                        problem='ANALYSIS_ADAPTER_OUTPUT_LIMIT'
                    if problem:
                        if not tree.stop(): problem='ANALYSIS_ADAPTER_TERMINATION_UNKNOWN'
                        raise TestError('Analysis adapter did not return a bounded result',problem)
                    time.sleep(.02)
                if tree.process.returncode or os.fstat(out.fileno()).st_size+os.fstat(err.fileno()).st_size>262144:
                    raise TestError('Analysis adapter failed', 'ANALYSIS_ADAPTER_FAILED')
                out.seek(0)
                value=json.loads(out.read(262145))
                if not isinstance(value,dict): raise ValueError('Expected a JSON object')
                return value
            finally:
                tree.close()


def diagnose(item):
    run=item['run'];attempt=next((a for a in run['attempts'] if a['id']==item.get('attempt_id')), {})
    state=attempt.get('state',item['phase']).lower()
    detail=attempt.get('reason') or run.get('reason') or '실행 근거를 확인하세요.'
    # A deterministic diagnostic is not evidence of a completed remediation.
    return {'base_revision':item['evidence_revision'],
        'cause_key':f"{state}-"+digest({'tc':attempt.get('tc_id'), 'reason':detail})[:16],
        'cause_summary':redact(detail)[:4000],
        'remediation_summary':'기본 진단 완료. 등록된 플러그인 조치와 독립 검증 근거가 필요합니다.',
        'evidence_refs':item['evidence_refs'],'remediation_refs':[],'action':'HOLD'}


class RuntimeAnalysis:
    def __init__(self, manager, runtime, *, principal='bsp-upgrade', clock=time.monotonic, executor=invoke):
        self.manager=manager;self.root=Path(runtime);self.path=self.root/'failure-analysis.json'
        self.principal=principal;self.clock=clock;self.executor=executor;self.next_poll=0

    def status(self):
        values=self.manager.store.documents('analysis-runtime')
        return values[0] if values else {'state':'WAITING','mode':'builtin'}

    def record(self,state,**values):
        value={'state':state,'updated_at':now(),**values}
        with self.manager.store.transaction() as c:
            c.execute('INSERT INTO documents VALUES(?,?,?) ON CONFLICT(kind,name) DO UPDATE SET data=excluded.data',
                      ('analysis-runtime','current',json.dumps(value,ensure_ascii=False)))

    def verify(self,run,item,result):
        cfg=settings(self.path)
        if not cfg.enabled or cfg.verifier is None: return None
        revision=digest(cfg.model_dump())
        proof=self.executor(cfg.verifier, sanitized({'contract':'failure-remediation-v1',
            'run':run,'analysis':item,'result':result}), self.root/'analysis-adapters')
        if revision!=digest(settings(self.path).model_dump()): return None
        return proof

    def tick(self):
        if self.clock()<self.next_poll: return None
        self.next_poll=self.clock()+2
        try:
            cfg=settings(self.path);revision=digest(cfg.model_dump())
            self.next_poll=self.clock()+cfg.interval_seconds
            if not cfg.enabled or cfg.mode=='external':
                self.record('EXTERNAL' if cfg.enabled else 'DISABLED', mode=cfg.mode,config_revision=revision)
                return None
            item=self.manager.analysis.claim(self.principal,'service-analysis',600)
            if item is None: return None
            self.record('RUNNING',mode=cfg.mode,config_revision=revision,analysis_id=item['id'])
            result=diagnose(item) if cfg.mode=='builtin' else self.executor(cfg.analyzer,context(item),self.root/'analysis-adapters')
            result=AnalysisResult.model_validate(result).model_dump()
            if revision!=digest(settings(self.path).model_dump()):
                raise TestError('Analysis configuration changed', 'ANALYSIS_CONFIG_CHANGED')
            receipt=self.manager.analysis.submit(item['id'],self.principal,item['lease_token'],result)
            self.record(receipt['status'],mode=cfg.mode,config_revision=revision,analysis_id=item['id'])
            return receipt
        except Exception as exc:
            # The unacknowledged durable lease remains available after expiry.
            self.record('ERROR',code=exc.code if isinstance(exc,TestError) else 'ANALYSIS_ADAPTER_INVALID')
            return None


def attach(manager,runtime):
    control=RuntimeAnalysis(manager,runtime,principal=os.environ.get('GUI_TEST_INTEGRATION_PRINCIPAL','bsp-upgrade'))
    manager.analysis_runtime=control
    if manager.analysis.verifier is None: manager.analysis.verifier=control.verify
    manager.analysis_worker=control
    return manager


def pinned(argv):
    files={arg:hashlib.sha256(Path(arg).read_bytes()).hexdigest()
           for arg in argv if Path(arg).is_absolute() and Path(arg).is_file()}
    return AdapterCommand(argv=argv,files=files).model_dump()


def save_settings(runtime,value,expected_revision=None):
    from ..execution.launch import LaunchLock
    root=Path(runtime);root.mkdir(parents=True,exist_ok=True)
    path=root/'failure-analysis.json'
    cfg=AutomationSettings.model_validate(value)
    with LaunchLock(root/'analysis-config.lock'):
        revision=digest(settings(path).model_dump())
        if path.exists() and expected_revision!=revision:
            raise TestError('Analysis configuration changed; read its current revision', 'ANALYSIS_CONFIG_CHANGED')
        temporary=path.with_suffix('.tmp')
        try:
            with temporary.open('w',encoding='utf-8') as f:
                os.chmod(temporary,0o600)
                json.dump(cfg.model_dump(),f,ensure_ascii=False,indent=2)
                f.flush();os.fsync(f.fileno())
            os.replace(temporary,path)
        finally:
            temporary.unlink(missing_ok=True)
    return {'revision':digest(cfg.model_dump()),'mode':cfg.mode,'enabled':cfg.enabled}


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='Configure the persistent plugin failure-analysis adapter')
    parser.add_argument('action',choices=['status','configure'])
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--mode',choices=['builtin','command','external'],default='builtin')
    parser.add_argument('--analyzer-argv',help='JSON array; absolute executable and {request_file}')
    parser.add_argument('--verifier-argv',help='JSON array; independent trusted verification program')
    parser.add_argument('--expected-revision')
    args=parser.parse_args(argv)
    try:
        if args.action=='status':
            cfg=settings(args.runtime/'failure-analysis.json')
            result={'revision':digest(cfg.model_dump()),'mode':cfg.mode,'enabled':cfg.enabled,
                    'analyzer_configured':cfg.analyzer is not None,'verifier_configured':cfg.verifier is not None}
        else:
            value={'mode':args.mode}
            for key,raw in [('analyzer',args.analyzer_argv),('verifier',args.verifier_argv)]:
                if raw is not None: value[key]=pinned(json.loads(raw))
            result=save_settings(args.runtime,value,args.expected_revision)
        print(json.dumps(result,ensure_ascii=False));return 0
    except (OSError,ValueError,TestError):
        print(json.dumps({'error':'ANALYSIS_CONFIGURATION_INVALID_OR_STALE'}));return 1


if __name__=='__main__': raise SystemExit(main())
