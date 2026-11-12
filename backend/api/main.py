import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import httpx
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from backend.domain.engine import Engine
from backend.domain.policy import Conflict, uid, file_hash
from backend.settings import Settings, Profile, validate_live, bridge_defaults, executable_status
from backend.storage.store import Store

ROOT = Path(__file__).resolve().parents[2]


class StartBody(BaseModel):
    title: str = Field(default='BSP OS Upgrade', min_length=1, max_length=120)
    mode: str = Field(default='linux', pattern='^(linux|windows)$')


class ActionBody(BaseModel):
    expected_version: int
    data: dict = Field(default_factory=dict)


class ConfigBody(BaseModel):
    version: int
    profile: Profile


def create_app(runtime=None):
    runtime = Path(runtime or os.environ.get('BSP_RUNTIME', ROOT / '.runtime')).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    instance_id = os.environ.get('BSP_INSTANCE_ID') or uid()
    engine = Engine(Store(runtime / 'dashboard.db'), runtime / 'artifacts')
    settings = Settings(engine.store)
    app = FastAPI(title='BSP Upgrade Dashboard', version='0.1.0', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.engine = engine
    app.state.settings = settings
    from backend.gui_test.runtime import live_manager
    from backend.services.gui_test_host import make_dashboard_manager, demo_router
    from backend.gui_test.api.router import router as gui_router
    from backend.gui_test.core.models import TestError
    from backend.services.module_test_selection import ModuleTestSelection
    app.state.module_test_selection = ModuleTestSelection(engine, runtime)
    app.state.gui_manager = make_dashboard_manager(runtime, module_selection_service=app.state.module_test_selection)
    app.state.gui_live_manager = live_manager(runtime, 'dashboard', app.state.gui_manager)
    for manager in (app.state.gui_manager, app.state.gui_live_manager):
        manager.module_selection_service = app.state.module_test_selection
    from backend.gui_test.connector.api import router as connector_router
    app.include_router(connector_router(app.state.gui_live_manager))
    integration_token = os.environ.get('GUI_TEST_INTEGRATION_TOKEN', '')
    integration_principal = os.environ.get('GUI_TEST_INTEGRATION_PRINCIPAL', 'bsp-upgrade')
    service_registry = None
    if getattr(app.state.gui_live_manager, 'integration', None) is not None and len(integration_token) >= 32:
        from backend.gui_test.standalone.integration import ServiceRegistry
        app.state.gui_live_manager.integration.controller_resolver = lambda target: target == integration_principal
        service_registry = ServiceRegistry(app.state.gui_live_manager, runtime, integration_principal)
    app.include_router(gui_router(app.state.gui_manager))
    app.include_router(gui_router(app.state.gui_live_manager, live=True))
    app.include_router(demo_router(app.state.gui_manager))
    app.include_router(demo_router(app.state.gui_live_manager, live=True))

    @app.exception_handler(TestError)
    async def gui_error(request, exc):
        return JSONResponse({'code': exc.code, 'message': exc.message}, status_code=exc.status)

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse({'code': exc.code, 'message': exc.message}, status_code=exc.status)

    @app.middleware('http')
    async def limits(request, call_next):
        # The single-user dashboard is reached locally or through an SSH tunnel.
        # Never trust forwarded headers as proof of a loopback peer.
        try:
            peer = ipaddress.ip_address(request.client.host if request.client else '')
            local_peer = peer.is_loopback or bool(getattr(peer, 'ipv4_mapped', None) and peer.ipv4_mapped.is_loopback)
        except ValueError:
            local_peer = False
        if not local_peer:
            return JSONResponse({'message': '로컬 주소 또는 SSH 터널로 접속해 주세요.'}, status_code=403)
        if request.url.path.startswith('/api/'):
            origin = request.headers.get('origin')
            if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
                return JSONResponse({'message': '다른 출처의 API 요청은 허용하지 않습니다.'}, status_code=403)
            if request.headers.get('sec-fetch-site') in {'cross-site', 'same-site'}:
                return JSONResponse({'message': '대시보드 화면에서 요청해 주세요.'}, status_code=403)
            service_auth = len(integration_token) >= 32 and hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + integration_token)
            if request.headers.get('authorization') and not service_auth and request.url.path not in {'/api/v1/gui-test/live/connector/register', '/api/v1/gui-test/live/connector/stop-readiness'}:
                return JSONResponse({'message':'Invalid service credential'},status_code=401)
            if service_auth:
                if request.url.path != '/api/v1/health' and not request.url.path.startswith('/api/v1/gui-test/live/'):
                    return JSONResponse({'message': 'Plugin credential is scoped to GUI Test'}, status_code=403)
                if origin or request.headers.get('sec-fetch-site'):
                    return JSONResponse({'message': 'Service credentials require a non-browser client'}, status_code=403)
                if request.method not in {'GET', 'HEAD', 'OPTIONS'} and '/integration/' not in request.url.path:
                    return JSONResponse({'message': 'Use integration contract for service mutations'}, status_code=403)
                request.state.gui_principal = integration_principal
            connector_registration = request.url.path == '/api/v1/gui-test/live/connector/register'
            # A non-secret header prevents browser forms/no-cors requests from mutating state.
            if request.method not in {'GET', 'HEAD', 'OPTIONS'} and request.headers.get('x-bsp-client') != 'dashboard' and not service_auth and not connector_registration:
                return JSONResponse({'message': '대시보드 요청 헤더가 필요합니다.'}, status_code=403)
        limit = 2_097_152
        raw_length = request.headers.get('content-length', '0')
        if not raw_length.isdigit() or int(raw_length) > limit:
            return JSONResponse({'message': '요청은 2MB 이하로 제한됩니다.'}, status_code=413)
        size = 0
        chunks = []
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                return JSONResponse({'message': '요청이 너무 큽니다.'}, status_code=413)
            chunks.append(chunk)
        request._body = b''.join(chunks)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        return response

    @app.get('/api/v1/health')
    def health():
        if service_registry is not None:
            with app.state.gui_live_manager.store.connection() as c:
                row = c.execute("SELECT value FROM meta WHERE key='connector_worker_heartbeat'").fetchone()
            import time
            running = bool(row and time.time() - float(row[0]) < 5)
            result = service_registry.snapshot(running)
            with app.state.gui_live_manager.store.connection() as c:
                epoch = c.execute("SELECT value FROM meta WHERE key='integration_worker_epoch'").fetchone()
            return result | {'worker_epoch': int(epoch[0]) if epoch else None}
        return {'status': 'ok', 'version': '0.1.0', 'instance_id': instance_id}

    @app.get('/api/v1/config')
    def config():
        return settings.get()

    @app.post('/api/v1/config/validate')
    def validate_config(body: Profile):
        return body.model_dump()

    @app.post('/api/v1/config/bridge-defaults')
    def suggested_bridges(body: Profile):
        return bridge_defaults(body.workspace)

    @app.put('/api/v1/config')
    def save_config(body: ConfigBody):
        return settings.save(body.version, body.profile.model_dump())

    @app.post('/api/v1/config/probe')
    def probe():
        p = settings.get()['profile']
        checks = []
        try:
            revision = validate_live(p)
            checks.append({'name': '실행 경로·설정', 'status': 'CONFIGURED', 'detail': '파일 접근 확인. 도구 인증/실제 실행은 미검증.'})
            checks.append({'name': '소스 기준', 'status': 'RESOLVED', 'detail': f'{revision} · 새 작업 시작 때 다시 확인하여 고정합니다.'})
        except Conflict as e:
            checks.append({'name': 'Linux 실행 환경', 'status': 'NOT_CONFIGURED', 'detail': e.message})
        if p.get('runner') == 'native':
            from backend.adapters.native import discover
            checks.extend(discover(p))
        else:
            for k, argv in [*p['agents'].items(), ('build', p['build_argv'])]:
                status, detail = executable_status(argv)
                checks.append({'name': k, 'status': status, 'detail': detail})
        return {'checks': checks, 'execution': p['execution']}

    @app.post('/api/v1/jira/probe')
    def jira_probe():
        p = settings.get()['profile']
        if p['jira_mode'] == 'claude_mcp':
            if p.get('mcp_argv'):
                from backend.adapters.jira import Jira
                try:
                    result = Jira(p).mcp('mcp_list', {})
                    return {'status': 'DISCOVERED', 'detail': '설정된 Claude 환경의 MCP 목록 조회 결과. 등록과 쓰기 권한은 별도입니다.', 'servers': result.get('servers', [])}
                except ValueError:
                    return {'status': 'FAILED', 'detail': 'Claude MCP 목록 조회 실패. 브리지와 실행 환경을 확인하세요.'}
            return {'status': 'UNVERIFIED', 'detail': 'Claude 환경의 MCP 자동 검색 브리지가 아직 연결되지 않았습니다. 등록 이름은 설정값이며 연결 확인 결과가 아닙니다.'}
        token = os.environ.get(p['jira_auth_env'])
        if not token or not p['jira_url']:
            return {'status': 'NOT_CONFIGURED', 'detail': 'Jira 주소와 서버 인증 환경변수를 설정해 주세요.'}
        if urlparse(p['jira_url']).scheme != 'https':
            raise Conflict('Jira에는 HTTPS 주소가 필요합니다.', status=422)
        try:
            with httpx.Client(timeout=8, follow_redirects=False) as client:
                r = client.get(p['jira_url'].rstrip('/') + '/rest/api/' + p['jira_api_version'] + '/myself', headers={'Authorization': 'Bearer ' + token})
            return {'status': 'READ_VERIFIED' if r.status_code == 200 else 'FAILED', 'detail': '읽기 인증 확인. 생성/수정 권한은 미검증.' if r.status_code == 200 else f'인증 조회 실패 (HTTP {r.status_code})'}
        except httpx.HTTPError:
            return {'status': 'FAILED', 'detail': 'Jira 연결 실패. 주소·인증·사내망 접근을 확인하세요.'}

    @app.get('/api/v1/jobs')
    def jobs():
        return [{'id': j['id'], 'title': j['title'], 'execution': j['execution'], 'created_at': j['created_at']} for j in engine.store.all()]

    @app.get('/api/v1/jobs/{job_id}/orchestration')
    def orchestration(job_id: str, limit: int = Query(default=50, ge=1, le=100), before: int | None = Query(default=None, ge=1)):
        return engine.orchestration.summary(job_id, limit, before)

    @app.get('/api/v1/jobs/{job_id}/reports')
    def reports(job_id: str, limit: int = Query(default=50, ge=1, le=100), before: int | None = Query(default=None, ge=1)):
        return engine.reports.page(job_id, limit, before)

    @app.get('/api/v1/jobs/{job_id}/reports/{report_id}')
    def report_detail(job_id: str, report_id: str):
        report = engine.reports.detail(job_id, report_id)
        if not report:
            raise Conflict('Report not found.', 'NOT_FOUND', 404)
        return report

    @app.get('/api/v1/jobs/{job_id}/decision-candidates')
    def decision_candidates(job_id: str, limit: int = Query(default=50, ge=1, le=100), before: int | None = Query(default=None, ge=1)):
        return engine.orchestration.page(job_id, 'candidates', limit, before)

    @app.get('/api/v1/jobs/{job_id}/scope-holds')
    def scope_holds(job_id: str, limit: int = Query(default=50, ge=1, le=100), before: int | None = Query(default=None, ge=1)):
        return engine.orchestration.page(job_id, 'holds', limit, before)

    @app.get('/api/v1/jobs/{job_id}/orchestration/{collection}/{record_id}')
    def orchestration_detail(job_id: str, collection: str, record_id: str):
        return engine.orchestration.detail(job_id, collection, record_id)

    @app.get('/api/v1/jobs/{job_id}/orchestration/{collection}')
    def orchestration_collection(job_id: str, collection: str, limit: int = Query(default=50, ge=1, le=100), before: int | None = Query(default=None, ge=1)):
        return engine.orchestration.page(job_id, collection, limit, before)

    @app.get('/api/v1/jobs/{job_id}/decision-candidates/{candidate_id}')
    def candidate_detail(job_id: str, candidate_id: str):
        return engine.orchestration.detail(job_id, 'candidates', candidate_id)

    @app.get('/api/v1/jobs/{job_id}/scope-holds/{hold_id}')
    def hold_detail(job_id: str, hold_id: str):
        return engine.orchestration.detail(job_id, 'holds', hold_id)

    @app.post('/api/v1/jobs', status_code=202)
    def start(body: StartBody, request: Request):
        return engine.create(request.headers.get('idempotency-key'), settings.get()['profile'], body.title, body.mode)

    @app.get('/api/v1/jobs/{job_id}')
    def snapshot(job_id: str):
        return engine.snapshot(job_id, metadata=True)

    @app.get('/api/v1/jobs/{job_id}/modules/{module_id}')
    def module_detail(job_id: str, module_id: str):
        from backend.domain.orchestration import public_snapshot
        return public_snapshot(engine.module(engine.store.snapshot(job_id), module_id))

    @app.get('/api/v1/jobs/{job_id}/events')
    def events(job_id: str, after: int = 0):
        engine.store.snapshot(job_id)
        return engine.store.events(job_id, after)

    @app.post('/api/v1/jobs/{job_id}/actions/{action}')
    def action(job_id: str, action: str, body: ActionBody, request: Request):
        return engine.act(job_id, request.headers.get('idempotency-key'), body.expected_version, action, body.data)

    @app.post('/api/v1/jobs/{job_id}/evidence')
    async def evidence(job_id: str, request: Request):
        engine.store.snapshot(job_id)
        raw = await request.body()
        if not raw:
            raise Conflict('비어 있는 근거 파일입니다.', status=422)
        name = uid() + '.log'
        folder = engine.artifacts / job_id
        folder.mkdir(exist_ok=True)
        (folder / name).write_bytes(raw)
        return {'id': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}

    @app.get('/api/v1/jobs/{job_id}/artifacts/{artifact_id}')
    def download(job_id: str, artifact_id: str):
        job = engine.store.snapshot(job_id)
        artifact = next((m['stages']['build']['result'].get('artifact') for m in job['modules'] if m['stages']['build']['result'] and m['stages']['build']['result'].get('artifact', {}).get('id') == artifact_id), None)
        if not artifact:
            raise Conflict('이 작업에 연결된 산출물이 아닙니다.', status=404)
        file = (engine.artifacts / job_id / artifact_id).resolve()
        if file.parent != (engine.artifacts / job_id).resolve() or not file.is_file() or file_hash(file) != artifact['sha256']:
            raise Conflict('산출물 파일 또는 해시를 확인할 수 없습니다.', status=422)
        return FileResponse(file, filename=artifact['name'], media_type='application/octet-stream')

    dist = ROOT / 'apps/web/dist'
    if dist.exists():
        app.mount('/', StaticFiles(directory=dist, html=True), name='web')
    return app
