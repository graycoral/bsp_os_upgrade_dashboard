import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlparse
import httpx
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from backend.domain.engine import Engine
from backend.domain.policy import Conflict, uid, file_hash
from backend.settings import Settings, Profile, validate_live
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


def create_app(runtime=None, access_token=None):
    runtime = Path(runtime or os.environ.get('BSP_RUNTIME', ROOT / '.runtime')).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    token_file = runtime / 'access-token'
    if access_token is None:
        if not token_file.exists():
            fd = os.open(token_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(secrets.token_urlsafe(32))
        access_token = token_file.read_text().strip()
    engine = Engine(Store(runtime / 'dashboard.db'), runtime / 'artifacts')
    settings = Settings(engine.store)
    app = FastAPI(title='BSP Upgrade Dashboard', version='0.1.0', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.engine = engine
    app.state.settings = settings
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse({'code': exc.code, 'message': exc.message}, status_code=exc.status)

    @app.middleware('http')
    async def limits(request, call_next):
        origin = request.headers.get('origin')
        if origin and request.method not in {'GET', 'HEAD', 'OPTIONS'} and urlparse(origin).netloc != request.headers.get('host'):
            return JSONResponse({'message': '다른 출처의 변경 요청은 허용하지 않습니다.'}, status_code=403)
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

    def auth(request: Request):
        provided = request.headers.get('authorization', '').removeprefix('Bearer ') or request.cookies.get('bsp_session', '')
        if not hmac.compare_digest(provided, access_token):
            raise Conflict('접속 키를 입력해 주세요.', 'UNAUTHORIZED', 401)

    secure = [Depends(auth)]

    @app.post('/api/v1/session')
    async def login(request: Request):
        data = await request.json()
        if not isinstance(data.get('token'), str) or not hmac.compare_digest(data['token'], access_token):
            raise Conflict('접속 키가 일치하지 않습니다.', 'UNAUTHORIZED', 401)
        response = JSONResponse({'ok': True})
        response.set_cookie('bsp_session', access_token, httponly=True, samesite='strict', secure=request.url.scheme == 'https', max_age=86400)
        return response

    @app.get('/api/v1/health')
    def health():
        return {'status': 'ok', 'version': '0.1.0'}

    @app.get('/api/v1/config', dependencies=secure)
    def config():
        return settings.get()

    @app.post('/api/v1/config/validate', dependencies=secure)
    def validate_config(body: Profile):
        return body.model_dump()

    @app.put('/api/v1/config', dependencies=secure)
    def save_config(body: ConfigBody):
        return settings.save(body.version, body.profile.model_dump())

    @app.post('/api/v1/config/probe', dependencies=secure)
    def probe():
        p = settings.get()['profile']
        checks = []
        try:
            validate_live(p)
            checks.append({'name': '실행 경로·브리지', 'status': 'CONFIGURED', 'detail': '파일 접근 확인. 도구 인증/실제 실행은 미검증.'})
        except Conflict as e:
            checks.append({'name': 'Linux 실행 환경', 'status': 'NOT_CONFIGURED', 'detail': e.message})
        for k, argv in p['agents'].items():
            checks.append({'name': k, 'status': 'REGISTERED' if argv else 'NOT_CONFIGURED', 'detail': '브리지 등록 · 실제 인증 미확인' if argv else '실행 브리지 미설정'})
        return {'checks': checks, 'execution': p['execution']}

    @app.post('/api/v1/jira/probe', dependencies=secure)
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

    @app.get('/api/v1/jobs', dependencies=secure)
    def jobs():
        return [{'id': j['id'], 'title': j['title'], 'execution': j['execution'], 'created_at': j['created_at']} for j in engine.store.all()]

    @app.post('/api/v1/jobs', dependencies=secure, status_code=202)
    def start(body: StartBody, request: Request):
        return engine.create(request.headers.get('idempotency-key'), settings.get()['profile'], body.title, body.mode)

    @app.get('/api/v1/jobs/{job_id}', dependencies=secure)
    def snapshot(job_id: str):
        return engine.snapshot(job_id)

    @app.get('/api/v1/jobs/{job_id}/events', dependencies=secure)
    def events(job_id: str, after: int = 0):
        engine.store.snapshot(job_id)
        return engine.store.events(job_id, after)

    @app.post('/api/v1/jobs/{job_id}/actions/{action}', dependencies=secure)
    def action(job_id: str, action: str, body: ActionBody, request: Request):
        return engine.act(job_id, request.headers.get('idempotency-key'), body.expected_version, action, body.data)

    @app.post('/api/v1/jobs/{job_id}/evidence', dependencies=secure)
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

    @app.get('/api/v1/jobs/{job_id}/artifacts/{artifact_id}', dependencies=secure)
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
