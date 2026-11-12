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
        self.normal = {}
        self.stop = threading.Event(); self.thread = None
        self.epoch = secrets.token_hex(16); self.seq = 0; self.records = deque(maxlen=64)
        self.snapshot = {'runner_id': host.identity, 'boards': [], 'errors': [], 'epoch': self.epoch, 'cursor': 0}
        self.last = None
        with sqlite3.connect(host.db) as c:
            c.execute('CREATE TABLE IF NOT EXISTS connector_console_errors(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE,data TEXT NOT NULL)')
        controls = {b['com'] for b in host.configured_boards}
        ports = []
        for board_id, config in configs.items():
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
            rows = []
            for board in self.host.configured_boards:
                board_id = board['board_id']
                owner = next((b for b in active_batches if any(v and v['board_id'] == board_id for v in b['connection'].values())), None)
                evidence = None
                origin = 'connector-rx'
                if owner:
                    self.suspend([board_id])  # Batch FlashService is the only owner during reservations.
                    origin = 'batch-observer'
                    observers = self.host.flashing.observers.get(owner['id'], [])
                    for observer in observers:
                        if getattr(observer,'board_id',None)==board_id or (not getattr(observer,'board_id',None) and observer.config.get('port') == self.configs.get(board_id, {}).get('port')):
                            evidence = observer.evidence(); break
                elif board_id in self.configs:
                    if board_id not in self.normal:
                        observer = None
                        try:
                            observer = self.factory(self.host.runtime / 'console' / board_id, self.configs[board_id])
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
                    console_text=observer.evidence()['tail'][-4096:]
                else: console_text=''
                code = ('OBSERVER_NOT_CONFIGURED' if evidence is None else 'CONSOLE_GAP' if not evidence['complete'] else
                        'CONSOLE_PANIC' if evidence['panic'] else 'CONSOLE_READY')
                active = [j['id'] for j in jobs if j['state'] in {'RUNNING', 'UNKNOWN'} and
                          any(v and v.get('board_id') == board_id for v in j.get('connection', j.get('request', {}).get('connection', {})).values())]
                rows.append({'board_id': board_id, 'runner_id': self.host.identity, 'source': origin,
                             'run_ids': active, 'phase': evidence.get('phase', 'IDLE') if evidence else 'IDLE',
                             'code': code, 'state': 'READY' if code == 'CONSOLE_READY' else 'ERROR',
                             'text': console_text, 'observer_epoch':observer_epoch, 'source_byte_offset': evidence['end_offset'] if evidence else 0,
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
