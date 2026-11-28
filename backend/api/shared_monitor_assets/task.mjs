const get = id => document.getElementById(id);
const task = new URL(location.href).searchParams.get('task');
const openingTicket = new URLSearchParams(location.hash.slice(1)).get('ticket');
history.replaceState(null, '', location.pathname + (task ? '?task=' + encodeURIComponent(task) : ''));

let viewToken;
let connectionTimer;
let requestVersion = 0;
const runSelector = get('run-select');
const attemptSelector = get('attempt-select');
const logStream = get('log-stream');
const loadLog = get('load-log');
let renderedRun;
let logVersion = 0;
let logOffset = 0;
const path = '/api/v1/plugin-task/' + encodeURIComponent(task || '');
const statuses = {
  CANCELLED: '취소됨', COMPLETED: '완료', ERROR: '오류', FAIL: 'FAIL', FAILED: 'FAIL',
  PASSED: 'PASS', PASS: 'PASS', PAUSED: '일시정지', PENDING: '대기 중', RUNNING: '실행 중',
  UNKNOWN: '확인 필요',
};

async function request(url, options) {
  let response, data;
  try {
    response = await fetch(url, {cache: 'no-store', credentials: 'omit', signal: AbortSignal.timeout(6000), ...options});
    data = await response.json();
  } catch {
    throw new Error('작업 Monitor 또는 접속 경로가 오프라인입니다.');
  }
  if (!response.ok) {
    const error = new Error(data.message || '작업 상태를 조회하지 못했습니다.');
    error.status = response.status;
    throw error;
  }
  return data;
}

function render(data) {
  const {task: work, run, runs} = data;
  get('task-name').textContent = work.project || work.task_id;
  const lastSeen = new Date(work.last_seen_at * 1000);
  get('task-info').textContent = [work.account, work.task_id,
    Number.isFinite(lastSeen.getTime()) ? '마지막 보고 ' + lastSeen.toLocaleString() : '',
    work.active_run_id ? '현재 Run ' + work.active_run_id : '현재 Run 없음',
  ].filter(Boolean).join(' · ');
  const selected = runSelector.value;
  const latest = new Option('최근 실행', '');
  runSelector.replaceChildren(latest, ...(runs || []).map(item =>
    new Option((statuses[item.state] || item.state || '') + ' · ' + item.run_id, item.run_id)));
  runSelector.value = [...runSelector.options].some(option => option.value === selected) ? selected : '';
  runSelector.disabled = !(runs || []).length;
  get('run-status').textContent = run ? [statuses[run.state] || run.state, run.run_id].filter(Boolean).join(' · ') : '실행 기록 없음';
  const cases = run?.steps || [];
  get('results').replaceChildren(...cases.map(test => {
    const li = document.createElement('li');
    li.textContent = [test.tc_id, statuses[test.state] || test.state, test.result_reason].filter(Boolean).join(' · ');
    return li;
  }));
  const event = run?.events?.at(-1);
  get('last-event').textContent = event ? '최근 상태 변경 ' + event.event_type + ' · ' + new Date(event.created_at * 1000).toLocaleString() : '';
  const attempts = run?.attempts || [];
  get('log-panel').hidden = !attempts.length;
  const attempt = renderedRun === run?.run_id ? attemptSelector.value : null;
  attemptSelector.replaceChildren(...attempts.map(item =>
    new Option([item.ordinal, item.phase, statuses[item.state] || item.state].filter(Boolean).join(' · '), item.attempt_id)));
  if (attempt && attempts.some(item => item.attempt_id === attempt)) attemptSelector.value = attempt;
  if (run?.run_id !== renderedRun || attemptSelector.value !== attempt) resetLog();
  renderedRun = run?.run_id;
  get('task').hidden = false;
  get('status').textContent = '';
  get('status').hidden = true;
}

function showError(error) {
  resetLog();
  get('task').hidden = true;
  get('status').hidden = false;
  get('status').textContent = error.message;
}

function resetLog() {
  logVersion++;
  logOffset = 0;
  get('log-output').textContent = '';
  loadLog.textContent = '로그 읽기';
  loadLog.disabled = false;
}

attemptSelector.addEventListener('change', resetLog);
logStream.addEventListener('change', resetLog);
loadLog.addEventListener('click', async () => {
  if (!viewToken || !renderedRun || !attemptSelector.value) return;
  const version = ++logVersion;
  const run = encodeURIComponent(renderedRun);
  const attempt = encodeURIComponent(attemptSelector.value);
  const query = new URLSearchParams({stream: logStream.value, offset: logOffset});
  loadLog.disabled = true;
  try {
    const data = await request(path + '/runs/' + run + '/attempts/' + attempt + '/logs?' + query,
      {headers: {Authorization: 'Bearer ' + viewToken}});
    if (version !== logVersion) return;
    get('log-output').textContent = data.offset ? get('log-output').textContent + data.text : data.text;
    logOffset = data.next_offset;
    loadLog.textContent = data.eof ? '로그 읽기 완료' : '다음 로그 읽기';
    loadLog.disabled = Boolean(data.eof);
  } catch (error) {
    if (version !== logVersion) return;
    if ([401, 403, 404].includes(error.status)) {
      viewToken = undefined;
      clearTimeout(connectionTimer);
      requestVersion++;
      showError(error);
    } else {
      get('log-output').textContent = error.message;
      loadLog.disabled = false;
    }
  }
});

async function refresh() {
  clearTimeout(connectionTimer);
  const sequence = ++requestVersion;
  try {
    const run = runSelector.value;
    const query = run ? '?run_id=' + encodeURIComponent(run) : '';
    const data = await request(path + query, {headers: {Authorization: 'Bearer ' + viewToken}});
    if (sequence !== requestVersion) return;
    render(data);
  } catch (error) {
    if (sequence !== requestVersion) return;
    showError(error);
    if ([401, 403, 404].includes(error.status)) viewToken = undefined;
  }
  if (viewToken) connectionTimer = setTimeout(refresh, document.hidden ? 6000 : 2500);
}

runSelector.addEventListener('change', refresh);
try {
  if (!task || !openingTicket) throw new Error('커넥터 또는 플러그인에서 이 작업을 다시 여세요.');
  const session = await request(path + '/session', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ticket: openingTicket}),
  });
  viewToken = session.view_token;
  await refresh();
} catch (error) {
  showError(error);
}
