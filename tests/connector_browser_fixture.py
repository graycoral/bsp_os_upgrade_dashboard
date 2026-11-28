"""Test-only loopback browser fixture. Never starts production connector code."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx
import uvicorn
from backend.api.shared_monitor import create_shared_monitor
from backend.gui_test.connector.preview import MockConnector
from backend.gui_test.connector.web import BrowserUI
from backend.gui_test.connector.web_actions import PreviewActions
from backend.gui_test.core.models import TestError
from backend.gui_test.core.monitor_identity import redeem_proof


class MonitorFixture:
    """Mock Host behind a real task-only Monitor surface."""

    projects = {'a' * 32: ('Last Reporter', 'operator-a'), 'b' * 32: ('Run Owner', 'operator-b')}
    monitor_id = 'fixture-monitor'
    run = {'run_id': 'c' * 32, 'state': 'RUNNING', 'steps': [{'tc_id': 'owner_tc.py', 'state': 'PASS'}],
           'attempts': [{'attempt_id': 'd' * 32, 'phase': 'TC', 'state': 'PASS', 'ordinal': 1}]}

    def __init__(self):
        self.tickets, self.views, self.revoked = {}, {}, set()
        self.monitor_token = secrets.token_urlsafe(32)

    def act(self, body, origin):
        task = body.get('task_id')
        if task not in self.projects:
            return JSONResponse({}, status_code=404)
        if body.get('action') == 'issue':
            ticket = secrets.token_urlsafe(32)
            self.tickets[ticket] = task
            return JSONResponse({'url': f'{origin}/plugin-task/?task={task}#ticket={ticket}'})
        if body.get('action') == 'revoke':
            self.revoked.add(task)
            return JSONResponse({'revoked': True})
        return JSONResponse({}, status_code=422)

    def reply(self, request):
        path = request.url.path
        if path == '/v1/sharing/view-tickets/redeem':
            body = json.loads(request.content)
            task = self.tickets.pop(body['ticket'], None)
            if (not task or body['task_id'] != task or body['monitor_id'] != self.monitor_id or task in self.revoked
                    or body.get('monitor_proof') != redeem_proof(self.monitor_token, self.monitor_id, body['ticket'])):
                return httpx.Response(403, json={})
            token = secrets.token_urlsafe(32)
            self.views[token] = task
            return httpx.Response(200, json={'task_id': task, 'monitor_id': self.monitor_id, 'view_token': token,
                                            'expires_at': time.time() + 900})
        token = request.headers.get('authorization', '').removeprefix('Bearer ')
        task = self.views.get(token)
        if not task or task in self.revoked or not path.startswith(f'/v1/sharing/tasks/{task}/view'):
            return httpx.Response(403, json={})
        project, account = self.projects[task]
        run = self.run if task == 'b' * 32 else None
        if path.endswith('/logs') and run:
            return httpx.Response(200, json={'text': 'owner log', 'offset': 0, 'next_offset': 9, 'eof': True,
                                            'run_id': run['run_id'], 'attempt_id': run['attempts'][0]['attempt_id'],
                                            'monitor_id': self.monitor_id})
        return httpx.Response(200, json={'task': {'task_id': task, 'account': account, 'project': project,
                                                   'monitor_id': self.monitor_id, 'last_seen_at': time.time(),
                                                   'active_run_id': run and run['run_id']},
                                         'run': run, 'runs': [run] if run else []})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,required=True);args=parser.parse_args()
    origin='http://127.0.0.1:'+str(args.port)
    with tempfile.TemporaryDirectory(prefix='connector-web-fixture-') as directory:
        home=Path(directory)
        app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
        ui=BrowserUI(PreviewActions(MockConnector(home)),origin)
        fixture = MonitorFixture()
        @app.middleware('http')
        async def guard(request,call_next):
            if request.url.path in {'/fixture-ticket', '/fixture-monitor'}:
                if request.client.host!='127.0.0.1' or not secrets.compare_digest(request.headers.get('x-test-driver',''),os.environ['CONNECTOR_FIXTURE_KEY']):
                    return JSONResponse({},status_code=403)
                if request.url.path == '/fixture-monitor':
                    return fixture.act(await request.json(), origin)
                if request.headers.get('x-test-reset')=='true':
                    ui.actions.adapter=MockConnector(home)
                return JSONResponse(ui.ticket())
            if request.url.path.startswith(('/plugin-task/', '/api/v1/plugin-task/')):
                return await call_next(request)
            return await ui.guard(request,call_next)
        @app.exception_handler(TestError)
        async def error(request,exc):return JSONResponse({'code':exc.code,'message':exc.message},status_code=exc.status)
        ui.routes(app)
        app.mount('/', create_shared_monitor(home, fixture.monitor_id, 8771, monitor_token=fixture.monitor_token,
                                             protected_listener=True, transport=httpx.MockTransport(fixture.reply)))
        uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False,log_level='warning')


if __name__=='__main__':main()
