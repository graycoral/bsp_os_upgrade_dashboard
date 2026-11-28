"""RX-only console projection; TC/control COM is never opened by this module."""
import re
import sqlite3
import json
import threading
import secrets
import time
from collections import deque
from ..core.models import digest
from ..core.models import TestError
from ..execution.console_observer import ConsoleObserver


class ConsoleHub:
    def __init__(self, host, configs, factory=ConsoleObserver):
        self.host, self.configs, self.factory = host, configs, factory
        self.multiplexers = getattr(host, 'multiplexers', None)
        if self.multiplexers:
            self.configs = {b['board_id']: dict({'panic_signatures':['Kernel panic'], 'boot_signatures':['U-Boot'], 'login_markers':['login :']}, **configs.get(b['board_id'], {})) for b in host.configured_boards}
        self.normal = {}
        self.stop = threading.Event(); self.thread = None
        self.epoch = secrets.token_hex(16); self.seq = 0; self.records = deque(maxlen=64)
        self.snapshot = {'runner_id': host.identity, 'boards': [], 'errors': [], 'epoch': self.epoch, 'cursor': 0}
        self.last = None
        with sqlite3.connect(host.db) as c:
            c.execute('CREATE TABLE IF NOT EXISTS connector_console_errors(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE,data TEXT NOT NULL)')
        controls = {b['com'] for b in host.configured_boards}
        ports = []
        for board_id, config in ({} if self.multiplexers else configs).items():
            port = config.get('port', '').upper()
            if (not re.fullmatch(r'COM[1-9][0-9]{0,3}', port) or port in controls or
                    config.get('rx_only_confirmed') is not True or config.get('control_lines_isolated') is not True):
                raise TestError('Explicit isolated RX mapping required; control COM observation prohibited', 'OBSERVER_CONFIG')
            ports.append(port)
        if len(ports) != len(set(ports)):
            raise TestError('Each RX endpoint needs one owner', 'OBSERVER_CONFIG')

    def suspend(self, board_ids=None):
        for board_id in list(self.normal):
            if board_ids is None or board_id in board_ids: self.normal.pop(board_id).close()

    def start(self):
        if self.thread: return
        def loop():
            while not self.stop.is_set():
                try: self.refresh()
                except Exception: pass
                self.stop.wait(.2)
        self.thread = threading.Thread(target=loop, name='connector-console-owner', daemon=True); self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread: self.thread.join(timeout=3)
        self.suspend()

    def projection(self, after=0, epoch=None, limit=4, error_after=0):
        with self.host.lock:
            reset = epoch is not None and epoch != self.epoch
            retained = self.records[0]['seq'] if self.records else self.seq
            pending=[r for r in self.records if reset or r['seq']>after]
            selected=pending[-limit:] if after==0 or reset else pending[:limit]
            cursor=selected[-1]['seq'] if selected else self.seq
            with sqlite3.connect(self.host.db) as c:
                events=c.execute('SELECT seq,data FROM connector_console_errors WHERE seq>? ORDER BY seq LIMIT 100',(error_after,)).fetchall()
            return dict(self.snapshot, records=selected,cursor=cursor,snapshot_seq=self.seq,
                        error_events=[dict(json.loads(data),source_seq=seq) for seq,data in events],error_cursor=events[-1][0] if events else error_after,
                        retained_from=retained,reset=reset,delivery_gap=not reset and after>0 and after<retained-1,
                        history_truncated=len(pending)>len(selected),more=bool(pending and cursor<pending[-1]['seq']))

    def refresh(self):
        with self.host.lock, sqlite3.connect(self.host.db) as c:
            jobs = [json.loads(r[0]) for r in c.execute('SELECT data FROM jobs')]
            batches = [json.loads(r[0]) for r in c.execute('SELECT data FROM batches')]
            active_batches = [b for b in batches if b['state'] != 'RELEASED']
            connector = getattr(self.host, 'connector', None)
            connector_runs = []
            if connector is not None:
                try:
                    for run_id, execution_mode, state, req_raw in c.execute(
                        "SELECT run_id, execution_mode, state, request_json FROM connector_runs "
                        "WHERE state IN ('QUEUED','FLASHING','RUNNING','PAUSE_REQUESTED','CANCEL_REQUESTED','FINALIZING','UNKNOWN')"
                    ).fetchall():
                        try:
                            req = json.loads(req_raw)
                        except Exception:
                            req = {}
                        connector_runs.append({
                            'id': run_id,
                            'execution_mode': execution_mode,
                            'state': state,
                            'connection': req.get('connection') or {},
                        })
                except sqlite3.OperationalError:
                    connector_runs = []
            rows = []
            for board in self.host.configured_boards:
                board_id = board['board_id']
                owner = next((b for b in active_batches if any(v and v['board_id'] == board_id for v in b['connection'].values())), None)
                connector_owner = next(
                    (cr for cr in connector_runs if any(isinstance(v, dict) and v.get('board_id') == board_id for v in cr['connection'].values())),
                    None,
                )
                run_observer = None
                run_observer_id = None
                if connector is not None:
                    run_obs_map = getattr(connector, '_run_observers', {})
                    candidate_lists = (
                        [(connector_owner['id'], run_obs_map.get(connector_owner['id'], []))]
                        if connector_owner and connector_owner['id'] in run_obs_map
                        else []
                    ) + [(rid, obs_list) for rid, obs_list in list(run_obs_map.items()) if not connector_owner or rid != connector_owner['id']]
                    for rid, obs_list in candidate_lists:
                        for obs in obs_list:
                            if getattr(obs, 'board_id', None) == board_id or (
                                not getattr(obs, 'board_id', None)
                                and getattr(obs, 'config', {}).get('port') == self.configs.get(board_id, {}).get('port')
                            ):
                                run_observer = obs
                                run_observer_id = rid
                                break
                        if run_observer is not None:
                            break
                evidence = None
                observer = None
                origin = 'serial-multiplexer' if self.multiplexers else 'connector-rx'
                if owner:
                    self.suspend([board_id])  # Batch FlashService is the only owner during reservations.
                    origin = 'batch-observer'
                    observers = self.host.flashing.observers.get(owner['id'], [])
                    for obs in observers:
                        if getattr(obs,'board_id',None)==board_id or (not getattr(obs,'board_id',None) and obs.config.get('port') == self.configs.get(board_id, {}).get('port')):
                            observer = obs
                            evidence = observer.evidence(); break
                elif run_observer is not None or (
                    connector_owner and (
                        connector_owner['state'] == 'FLASHING'
                        or (connector_owner['execution_mode'] == 'flash_and_test' and connector_owner['state'] in {'RUNNING', 'PAUSE_REQUESTED', 'CANCEL_REQUESTED', 'FINALIZING'})
                    )
                ):
                    self.suspend([board_id])  # ConnectorRunExecutor flash observer owns RX during flash_and_test.
                    origin = 'batch-observer'
                    if run_observer is not None:
                        observer = run_observer
                        evidence = observer.evidence()
                elif board_id in self.configs:
                    if board_id not in self.normal:
                        observer = None
                        try:
                            observer = (self.multiplexers.observer(self.host.runtime / 'console' / board_id, board_id, self.configs[board_id])
                                        if self.multiplexers else self.factory(self.host.runtime / 'console' / board_id, self.configs[board_id]))
                            observer.connector_epoch=secrets.token_hex(16); observer.start(); self.normal[board_id] = observer
                        except Exception:
                            if observer is not None: observer.close()
                            rows.append({'board_id': board_id, 'code': 'OBSERVER_UNAVAILABLE', 'state': 'ERROR', 'runner_id':self.host.identity, 'source':'connector-rx', 'run_ids':[], 'phase':'IDLE', 'evidence':None, 'text': '', 'source_byte_offset': 0}); continue
                    observer = self.normal[board_id]
                    evidence = observer.evidence()
                observer_epoch=None
                if evidence is not None:
                    if not getattr(observer,'connector_epoch',None): observer.connector_epoch=secrets.token_hex(16)
                    observer_epoch=observer.connector_epoch
                    evidence={k:v[-16:] if k in {'events','gaps'} else v for k,v in evidence.items() if k!='tail'}
                    console_text=(observer.evidence().get('tail') or '')[-4096:]
                else: console_text=''
                code = ('OBSERVER_NOT_CONFIGURED' if evidence is None else 'CONSOLE_GAP' if not evidence.get('complete', True) else
                        'CONSOLE_PANIC' if evidence.get('panic', False) else 'CONSOLE_READY')
                active = [j['id'] for j in jobs if j['state'] in {'RUNNING', 'UNKNOWN'} and
                          any(v and v.get('board_id') == board_id for v in j.get('connection', j.get('request', {}).get('connection', {})).values())]
                for cr in connector_runs:
                    if cr['id'] not in active and any(isinstance(v, dict) and v.get('board_id') == board_id for v in cr['connection'].values()):
                        active.append(cr['id'])
                if run_observer_id and run_observer_id not in active:
                    active.append(run_observer_id)
                rows.append({'board_id': board_id, 'runner_id': self.host.identity, 'source': origin,
                             'run_ids': active, 'phase': evidence.get('phase', 'IDLE') if evidence else 'IDLE',
                             'code': code, 'state': 'READY' if code == 'CONSOLE_READY' else 'ERROR',
                             'text': console_text, 'observer_epoch':observer_epoch, 'source_byte_offset': evidence.get('end_offset', 0) if evidence else 0,
                             'evidence': evidence})
            result = {'runner_id': self.host.identity, 'boards': rows,
                    'errors': [{k: row[k] for k in ('board_id', 'runner_id', 'run_ids', 'phase', 'code', 'evidence','observer_epoch') if k in row}
                               for row in rows if row['state'] == 'ERROR']}

            for error in result['errors']:
                event=dict(error,observer_epoch=error.get('observer_epoch') or self.epoch)
                event_id=digest(event)
                c.execute('INSERT OR IGNORE INTO connector_console_errors(event_id,data) VALUES(?,?)',(event_id,json.dumps(dict(event,event_id=event_id,time=time.time()))))
            signature = digest(result)
            if signature != self.last:
                self.seq += 1; self.last = signature
                self.records.append({'epoch': self.epoch, 'seq': self.seq, 'at': time.time(), 'boards': [{k: v[-4096:] if k=='text' else v for k, v in row.items() if k != 'evidence'} for row in rows]})
            self.snapshot = dict(result, epoch=self.epoch, cursor=self.seq)
