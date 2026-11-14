// Host owns authentication, API calls and polling; the reusable view never fetches.
import {mountConnector} from './view.mjs';
let csrf = '', stopped = false, polling = false, command = false, freshUntil = 0;
const base = location.pathname.replace(/\/$/, '');
const ticket = new URLSearchParams(location.hash.slice(1)).get('ticket');
history.replaceState(null, '', location.pathname);
const api = async (path, body) => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), path === '/api/status' ? 5000 : path === '/api/pick' ? 185000 : 15000);
  try {
    const response = await fetch(base + path, {method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', signal:controller.signal,
      headers: body === undefined ? {} : {'Content-Type': 'application/json', 'X-Connector-CSRF': csrf},
      body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store'});
    const value = await response.json();
    if (!response.ok) { const error = new Error(value.message || '요청을 완료하지 못했습니다.'); error.status = response.status; throw error; }
    return value;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('응답 시간이 초과됐습니다. 요청이 진행 중일 수 있으니 최근 상태를 확인하세요.');
    throw error;
  } finally { clearTimeout(timeout); }
};
const run = async (task, form) => {
  if (command) return;
  command = true; view.busy(true, form);
  try { await task(); } catch (error) { view.message(error.message, true); }
  finally { command = false; view.busy(false, form); }
};
const view = mountConnector(document.getElementById('app'), {
  action: (action, payload = {}) => run(async () => { await api('/api/action', {action, payload}); view.message('요청을 전달했습니다. 상태를 확인하고 있습니다.'); await refresh(); }),
  save: body => run(async () => { view.settings(await api('/api/settings', body)); view.message('Windows 설정을 저장했습니다. 연결하면 적용됩니다.'); }, 'local'),
  reload: () => run(async () => { view.settings(await api('/api/settings')); view.message('최신 Windows 설정을 불러왔습니다.'); }, 'local'),
  ports: () => run(async () => { view.ports(await api('/api/ports')); view.message('COM 목록을 갱신했습니다. 포트를 열거나 부팅 상태를 검사하지 않습니다.'); }),
  pick: (kind, input) => run(async () => { const value = await api('/api/pick', {kind}); if (value.path) { input.value = value.path; input.dispatchEvent(new Event('input', {bubbles:true})); } }),
  shared: () => run(async () => { view.shared(await api('/api/shared')); view.message('서버 공통 설정을 불러왔습니다.'); }, 'shared'),
  saveShared: body => run(async () => { view.shared(await api('/api/shared', body)); view.message('서버 공통 설정을 저장했습니다. Windows 적용 상태는 별도로 확인하세요.'); }, 'shared'),
  storage: () => run(async () => view.storage(await api('/api/storage')), 'storage'),
  saveStorage: body => run(async () => { view.storage(await api('/api/storage', body)); view.message('정리 기준을 저장했습니다. 커넥터 적용 상태를 확인하세요.'); }, 'storage'),
  cleanup: dry_run => run(async () => view.cleanup(await api('/api/storage-cleanup', {dry_run})), 'storage'),
  paths: (kind, path) => run(async () => view.paths(await api('/api/server-paths', {kind, path}))),
});
async function refresh() {
  if (polling || stopped) return;
  polling = true;
  try {
    const value = await api('/api/status');
    const checked = Number(value.last_checked_at);
    freshUntil = value.fresh ? Math.min(Date.now()+15000, checked > 0 ? checked*1000+15000 : Infinity) : 0;
    if (value.fresh && freshUntil <= Date.now()) { freshUntil=0; value.fresh=false; value.stale=true; value.boards=(value.boards || []).map(board=>({...board,stale:true})); }
    view.render(value);
  }
  catch (error) { freshUntil=0; view.unavailable(error.message); if (error.status === 401) stopped = true; }
  finally { polling = false; }
}
async function poll() {
  await refresh();
  if (!stopped) setTimeout(poll, document.hidden ? 4000 : 1200);
}
// Runs independently of fetch completion so a pending status request cannot
// keep a previous hardware snapshot displayed as fresh indefinitely.
const watchdog = setInterval(() => {
  if (freshUntil && Date.now() > freshUntil) {
    freshUntil = 0;
    view.unavailable('최근 보드 상태가 만료됐습니다. 연결을 확인하고 새 상태를 기다리세요.');
  }
}, 1000);
try {
  const session = ticket ? await api('/session', {ticket}) : await api('/api/session');
  csrf = session.csrf; view.preview(session.preview);
  view.settings(await api('/api/settings'));
  try { view.ports(await api('/api/ports')); } catch (error) { view.message(error.message, true); }
  poll();
} catch (error) { stopped = true; view.unavailable(error.message); }
// Closing or refreshing a browser tab never disconnects the manager or its work.
