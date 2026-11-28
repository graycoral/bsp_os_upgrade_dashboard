// Reusable DOM view. All data uses text/value properties, never HTML interpolation.
const clone = value => structuredClone(value);
const states = {CONNECTED:'연결됨', CONNECTING:'연결 중', DISCONNECTED:'미연결', DISCONNECTING:'연결 종료 중', RUNNING:'시험 중', RESERVED:'예약 중', UNKNOWN:'확인 필요', ERROR:'오류'};
const element = (tag, text, className) => { const value = document.createElement(tag); if (text !== undefined) value.textContent = text; if (className) value.className = className; return value; };
const tone = code => ['CONNECTED','READY'].includes(code) ? 'green' : /ERROR|FAIL|DENIED|TIMEOUT/.test(code) ? 'red' : ['DISCONNECTED','WAITING',''].includes(code) ? 'gray' : 'amber';
function signal(target, code, label) {
  if (!target.firstElementChild) target.append(element('span',undefined,'signal'),element('span',undefined,'sr-only'));
  target.dataset.state=code;target.dataset.tone=tone(code);target.setAttribute('role','img');target.setAttribute('aria-label',label);target.title=label;
  target.firstElementChild.className='signal '+tone(code);target.firstElementChild.setAttribute('aria-hidden','true');target.lastElementChild.textContent=label;
}
export function mountConnector(root, host) {
  root.innerHTML = `<header class="header"><div><h1 class="connector-title">WINDOWS · BOARD CONNECTOR <span id="preview" class="badge" hidden>모의 미리보기</span></h1></div><span id="state" class="status-indicator"></span></header>
  <div class="connection-line"><div id="stages" class="stages" aria-label="연결 단계"></div><div id="connection-actions" class="actions"><button id="verify-conn" type="button" title="양방향 연결 상태와 포트를 점검합니다">연결 확인</button><button id="reconnect-ssh" type="button" title="SSH -R 터널만 재연결합니다">SSH 재연결</button><button id="settings-tab" class="settings-icon" type="button" aria-label="환경설정" title="환경설정" aria-controls="settings" aria-expanded="false"><span class="gear-symbol" aria-hidden="true">⚙︎</span><span id="dirty" aria-hidden="true"></span></button><button id="connection-power" class="connection-power" type="button" aria-label="연결 시작" aria-pressed="false" disabled><span class="power-symbol" aria-hidden="true">⏻</span><span id="power-label">시작</span></button><a id="dashboard" class="button" target="_blank" rel="noreferrer" hidden>Agent Monitor 열기</a></div><div id="notice" class="notice" role="status" aria-live="polite" hidden></div><p id="cleanup-state" role="status" hidden></p></div>
  <section id="overview"><p id="plugin-status" role="status">플러그인 연결 보고 대기</p><details id="plugin-report" hidden><summary>플러그인이 보낸 설정</summary><pre id="plugin-values"></pre></details><p id="freshness" class="muted" hidden></p><p id="peer-banner" class="error" role="alert" hidden></p><p id="readiness-warning" class="notice" role="status" hidden></p>
  <p id="analysis-state" class="muted" aria-live="polite"></p><div id="error" class="error" role="alert" hidden></div>
  <div class="board-toolbar"><div id="boards" class="board-list" role="group" aria-label="보드 선택"></div><div id="summary" class="board-counts" role="group" aria-label="보드 수"><span><span>등록</span><strong id="count-registered">—</strong></span><span><span>감지</span><strong id="count-detected">—</strong></span><span><span>시험 중</span><strong id="count-running">—</strong></span></div></div>
  <section class="panel board-detail"><div class="section-heading"><div><div class="board-title-row"><h2 id="board-title">보드를 선택하세요</h2><button id="putty" class="putty-icon" type="button" aria-label="PuTTY 열기" title="PuTTY 열기" disabled><svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="3" y="4" width="18" height="16" rx="3"></rect><path d="m7 9 3 3-3 3m6 0h4"></path></svg></button></div><p id="board-subtitle" class="muted">보드가 없어도 환경설정과 기록을 확인할 수 있습니다.</p></div><span id="board-state" class="status-indicator"></span></div>
  <p id="control-reason" class="muted"></p>
  <div id="workspace" class="workspace"><section id="tc-status" class="tc-status" aria-label="테스트 스크립트 상태"><h3>테스트 스크립트</h3><p id="tc-source" class="muted"></p><p id="tc-status-note" class="muted" role="status"></p><div class="tc-tools"><input id="tc-search" type="search" placeholder="TC 검색" aria-label="TC 검색"><select id="tc-filter" aria-label="TC 상태 필터"><option value="all">전체 상태</option><option value="RUNNING">진행 중</option><option value="PENDING">대기 중</option><option value="PASS">PASS</option><option value="FAIL">FAIL · 오류 · 시간 초과</option><option value="UNKNOWN">확인 필요</option><option value="CANCELLED">취소됨</option><option value="NOT_RUN">미실행</option><option value="NOT_SELECTED">미선택</option></select></div><div class="tc-table-scroll" tabindex="0" aria-label="TC 목록 스크롤"><table><thead><tr><th scope="col">스크립트</th><th scope="col">상태</th></tr></thead><tbody id="tc-status-rows"></tbody></table><p id="tc-empty" class="muted" hidden>표시할 TC가 없습니다.</p></div></section>
  <div id="panel-divider" class="panel-divider" role="separator" tabindex="0" aria-label="TC 목록과 로그 너비 조절" aria-orientation="vertical" aria-controls="tc-status log-window" aria-valuemin="20" aria-valuemax="60" aria-valuenow="30" title="드래그 또는 좌우 방향키로 너비 조절"></div>
  <section id="log-window" class="log-window" aria-label="보드 로그"><div class="log-tab-bar"><div id="log-tabs" class="tabs" role="tablist" aria-label="로그 종류"></div><button id="open-logs">로그 폴더 열기</button></div>
  <div class="log-tools"><input id="search" placeholder="현재 로그에서 검색" aria-label="로그 검색"><label class="check"><input type="checkbox" id="errors-only">오류만</label><button id="copy">복사</button></div>
  <div id="log-panel" role="tabpanel"><p id="log-hint" class="muted"></p><textarea id="log" readonly spellcheck="false" aria-label="선택 보드 로그"></textarea></div></section></div>
  <details><summary>소스와 실행 경로</summary><pre id="paths">서버 경로 미수신</pre><p id="storage" class="muted"></p></details>
<details id="connection-details" class="connection-details"><summary>연결 상세 · 콘솔 안내</summary><p id="board-server" class="board-server" hidden></p><div class="callout"><strong>COM 멀티플렉서</strong><p>커넥터가 물리 COM 하나를 열고 TC·콘솔·PuTTY에 출력을 나눕니다.</p></div><p class="muted">보드 콘솔은 보드의 UART 수신 로그입니다. PuTTY는 같은 보드의 별도 터미널 창이며, 열면 입력 제어권을 자동으로 받고 창을 닫으면 반환합니다. COM 감지는 부팅·시험 통과를 뜻하지 않습니다.</p><p class="muted">신호등: 초록 정상 · 노랑 진행/확인 필요 · 빨강 오류 · 회색 미연결/대기.</p></details></section>
  <div id="scenario-row" class="panel" hidden><label>모의 상태 <select id="scenario"><option>연결</option><option>시험 중</option><option>오류</option><option>미연결</option><option>확인 필요</option></select></label></div></section>
  <section id="settings" hidden><div class="settings-navigation"><button id="overview-tab" type="button" aria-label="보드 현황" aria-controls="overview">← 보드 현황</button></div><div class="settings-grid"><form id="local-form" class="panel"><div class="section-heading"><div><h2>Windows 연결 설정</h2><p class="muted">연결을 종료한 뒤 변경하세요. 기존 작업과 설정은 보존됩니다.</p></div><span id="draft-state" class="badge">저장된 설정</span></div>
  <div class="fields"><label>Linux SSH 서버<input id="server" required placeholder="서버 주소"></label><label>SSH 계정<input id="account" required autocomplete="username"></label><label>Agent Monitor 서버 포트<input id="server-port" type="number" min="1" max="65535" value="8766" required></label></div>
  <label>TC Python 전체 경로<span class="path-field"><input id="python" placeholder="C:\\TC\\Python\\python.exe"><button type="button" data-pick="python">찾아보기</button></span></label><p class="muted">커넥터 실행용 Python과 별개입니다. 파일 선택을 지원하지 않으면 전체 경로를 직접 입력하세요.</p>
  <details><summary>상세 연결 설정</summary><div class="fields"><label>SSH 포트<input id="ssh-port" type="number" min="1" max="65535" value="22" required></label><label>SSH 개인 키 전체 경로<span class="path-field"><input id="ssh-key"><button type="button" data-pick="ssh_key">찾아보기</button></span></label><label>PuTTY 전체 경로<span class="path-field"><input id="putty-path" placeholder="자동 검색"><button type="button" data-pick="putty">찾아보기</button></span></label></div><p class="muted">SSH 키/agent와 host key 인증은 Windows OpenSSH에서 먼저 준비해야 합니다.</p></details>
  <div class="fields"><label>보드 수<input id="board-count" type="number" min="1" max="32" value="1" required></label></div><p class="muted">실제 보드 COM과 통신 속도를 선택하세요. 커넥터가 TC·콘솔·PuTTY 연결을 자동으로 공유합니다.</p>
  <p id="serial-status" class="muted" role="status"></p><div class="actions"><button id="refresh-ports" type="button">COM 목록 새로고침</button></div><datalist id="port-options"></datalist><div id="board-tabs" class="subtabs" role="tablist" aria-label="보드 설정 선택"></div><div id="board-forms"></div>
  <footer class="form-footer"><button class="primary" id="save" type="submit">Windows 설정 저장</button><button id="cancel" type="button">변경 취소</button><button id="reload" type="button">최신 설정 불러오기</button></footer></form>
  <section class="panel"><h2>이미지 퓨징 · 서버 공통 설정</h2><p class="muted">플러그인·Agent Monitor와 같은 설정입니다. Windows 로컬 경로와 Linux 서버 경로를 구분하세요.</p><p id="shared-state" class="callout">서버에 연결한 뒤 불러오세요.</p><button id="load-shared">서버 공통 설정 불러오기</button>
  <form id="shared-form"><fieldset id="shared-fields" disabled><fieldset id="flash-fields"><label>Linux 설치 BAT 경로<input id="installer"></label><button id="browse-installer" type="button">서버 BAT 폴더 탐색</button><label>플래싱 프로파일<input id="flash-profile"></label><label>이미지 허용 폴더 (한 줄에 하나)<textarea id="installer-roots"></textarea></label></fieldset><label>Linux TC 소스 경로<input id="tc-root"></label><button id="browse-source" type="button">서버 TC 폴더 탐색</button><label>TC 기본 제한시간 · 초<input id="timeout" type="number" min="1" max="86400"></label><p class="muted">TC별 재정의와 진행 중 실행의 고정 설정은 보존합니다.</p><button id="save-shared" class="primary">서버 공통 설정 저장</button></fieldset></form>
  <details><summary>저장 공간 자동 정리</summary><p class="muted">기본 7일 · 20 GiB. 진행 중 작업과 실패 근거는 보존합니다. 보호 파일이 많으면 한도를 넘을 수 있습니다.</p><button id="load-storage" type="button">정리 기준 불러오기</button><form id="storage-form" hidden><label class="check"><input id="storage-enabled" type="checkbox">자동 정리</label><label>보관 기간 · 일<input id="storage-days" type="number" min="0.042" step="any" required></label><label>캐시 한도 · GiB<input id="storage-limit" type="number" min="0.001" step="any" required></label><button id="save-storage">정리 기준 저장</button></form><p id="storage-state" class="muted"></p><div class="actions"><button id="preview-cleanup" type="button">정리 대상 확인</button><button id="apply-cleanup" type="button">지금 정리</button></div><pre id="cleanup-report"></pre></details><div id="server-browser" hidden><h3>서버 폴더</h3><p id="server-folder" class="muted"></p><button id="use-folder" type="button">이 폴더 선택</button><div id="server-entries"></div></div></section></div></section>
`;
  const q = id => root.querySelector('#' + id);
  const workspace=q('workspace'),divider=q('panel-divider'),splitKey='board-connector.tc-panel-percent';
  let splitPercent=30,dragPointer=null;
  try { const stored=Number(localStorage.getItem(splitKey));if(stored>=20&&stored<=60)splitPercent=stored; } catch {}
  function splitLimits(){
    const width=Math.max(1,workspace.clientWidth-12),min=Math.max(20,Math.min(60,220/width*100));
    return [min,Math.max(min,Math.min(60,(width-320)/width*100))];
  }
  function applySplit(){
    const [min,max]=splitLimits(),percent=Math.max(min,Math.min(max,splitPercent));
    workspace.style.setProperty('--tc-share',percent+'fr');workspace.style.setProperty('--log-share',(100-percent)+'fr');
    divider.setAttribute('aria-valuemin',String(Math.round(min)));divider.setAttribute('aria-valuemax',String(Math.round(max)));divider.setAttribute('aria-valuenow',String(Math.round(percent)));
    divider.setAttribute('aria-valuetext','TC 목록 '+Math.round(percent)+'%, 로그 '+Math.round(100-percent)+'%');
  }
  function saveSplit(){try { localStorage.setItem(splitKey,String(splitPercent)); } catch {}}
  divider.onpointerdown=event=>{
    if(event.button!==0)return;event.preventDefault();divider.focus();dragPointer=event.pointerId;
    divider.setPointerCapture(event.pointerId);workspace.classList.add('resizing');
  };
  divider.onpointermove=event=>{
    if(event.pointerId!==dragPointer)return;
    const [min,max]=splitLimits(),box=workspace.getBoundingClientRect();
    splitPercent=Math.max(min,Math.min(max,(event.clientX-box.left-6)/Math.max(1,box.width-12)*100));applySplit();
  };
  divider.onpointerup=divider.onpointercancel=event=>{
    if(event.pointerId!==dragPointer)return;dragPointer=null;workspace.classList.remove('resizing');
    if(divider.hasPointerCapture(event.pointerId))divider.releasePointerCapture(event.pointerId);saveSplit();
  };
  divider.onlostpointercapture=()=>{dragPointer=null;workspace.classList.remove('resizing');};
  divider.onkeydown=event=>{
    const [min,max]=splitLimits(),current=Math.max(min,Math.min(max,splitPercent));
    const next={ArrowLeft:current-2,ArrowRight:current+2,Home:min,End:max,Enter:30}[event.key];
    if(next===undefined)return;event.preventDefault();splitPercent=Math.max(min,Math.min(max,next));applySplit();saveSplit();
  };
  new ResizeObserver(applySplit).observe(workspace);
  applySplit();
  const stageInfo = {
    local:['Host','로컬 Host','Windows에서 보드 연결과 자율 실행을 담당하는 로컬 실행부입니다.'],
    ssh:['SSH -R','SSH -R 터널','Linux 127.0.0.1:8771 포트로 직결 터널을 유지합니다.'],
    overall:['직결','직결 연결 상태','로컬 Host와 SSH -R 바인드 확인 시 Agent Monitor 없이도 연결됨으로 표시합니다.'],
    agent_monitor:['모니터(선택)','Agent Monitor (선택)','미연결 시에도 플러그인과 직결 연결은 정상 동작합니다.']
  };
  for(const [key,[short,label,description]] of Object.entries(stageInfo)) {
    const row=element('span',undefined,'stage-signal'),light=element('span',undefined,'status-indicator'),tip=element('span',undefined,'stage-tooltip');
    row.dataset.stage=key;row.tabIndex=0;row.setAttribute('role','group');row.setAttribute('aria-label',label);
    tip.id='stage-tip-'+key;tip.setAttribute('role','tooltip');row.setAttribute('aria-describedby',tip.id);
    row.append(light,element('span',short),tip);q('stages').append(row);
    row.onkeydown=event=>{if(event.key==='Escape')row.dataset.dismissed='true';};
    row.onpointerenter=row.onfocus=()=>{delete row.dataset.dismissed;};
  }
  let snapshot = {}, selected = null, pending = false, saved = null, drafts = [], portChoices = [], sharedValue = null, browseKind = null, browsePath = '', selectedLog = 'console', selectedSettingsBoard = 0, storageValue = null;
  let sharedSource = null, sharedDirty = false;
  q('shared-form').addEventListener('input', () => { sharedDirty = true; });
  function syncShared(value) {
    const source = value.shared_source ? JSON.stringify(value.shared_source) : null;
    if (source && source !== sharedSource) {
      sharedSource = source;
      sharedValue = null;
      sharedDirty = false;
      q('shared-form').reset();
      q('server-browser').hidden = true;
      q('server-entries').replaceChildren();
      browsePath = '';
      q('tc-root').placeholder='';
      q('shared-fields').disabled = true;
    }
    const next = value.shared_settings;
    if (next?.integration && next.timeouts && value.fresh && !value.stale) {
      if (sharedValue?.offline_direct && next.read_only) {
        q('tc-root').value = next.integration.tc_root || '';
        q('shared-state').textContent = lookupText(next);
        return;
      }
      if (!sharedDirty && (!sharedValue || sharedValue.revision !== next.revision ||
          Boolean(sharedValue.read_only) !== Boolean(next.read_only))) shared(next);
      else if (sharedDirty) q('shared-state').textContent = '미저장 변경 있음';
      else q('shared-state').textContent = sharedStatus(next);
      q('shared-fields').disabled = Boolean(next.read_only);
    } else if (sharedSource && !sharedValue?.offline_direct) {
      q('shared-fields').disabled = true;
      q('shared-state').textContent = value.shared_error || 'Linux 공통 설정 수신 대기 중';
    } else if (value.shared_error) q('shared-state').textContent = '공통 설정 조회 실패 · '+value.shared_error;
  }
  const items = new Map(), connection = []; let lastConnection = '';
  let activateSettingsBoard = () => {};
  function message(text, error = false) { q('notice').textContent = text; q('notice').hidden = !text; q('notice').className = error ? 'notice error' : 'notice'; }
  const dirty = value => { q('dirty').textContent = value ? '●' : ''; q('draft-state').textContent = value ? '저장되지 않은 변경' : '저장된 설정'; };
  q('local-form').addEventListener('input', () => dirty(true));
  q('local-form').addEventListener('invalid', event => {
    const first = q('local-form').querySelector('input:invalid,select:invalid,textarea:invalid');
    if (event.target !== first) { event.preventDefault(); return; }
    const field = first?.closest('#board-forms > fieldset');
    if (field?.hidden) {
      const index = [...q('board-forms').children].indexOf(field);
      activateSettingsBoard(index);
      message('보드 '+(index+1)+'의 필수 COM·통신 속도를 확인하세요.', true);
      first.focus();
    }
  }, true);
  for (const page of ['overview', 'settings']) q(page + '-tab').onclick = () => {
    q('overview').hidden = page !== 'overview'; q('settings').hidden = page !== 'settings';q('connection-actions').hidden = page !== 'overview';
    q('settings-tab').setAttribute('aria-expanded', String(page === 'settings'));
    q(page === 'settings' ? 'overview-tab' : 'settings-tab').focus();
  };
  const chosen = () => (snapshot.boards || []).find(board => board.board_id === selected);
  function canRequestStop() {
    if (['CONNECTED','ERROR'].includes(snapshot.state)) return true;
    return snapshot.local_state === 'READY' && snapshot.fresh === true &&
      ['CONNECTING','RECONNECTING','AUTH_OR_CONFIG_ERROR','NOT_CONFIGURED'].includes(snapshot.state);
  }
  q('connection-power').onclick = () => { if(!q('connection-power').disabled)host.action(canRequestStop()?'disconnect':'connect'); };
  q('verify-conn').onclick = () => host.action('verify-connection');
  q('reconnect-ssh').onclick = () => host.action('reconnect-ssh');
  q('putty').onclick = () => host.action('putty', {board_id:selected});
  q('open-logs').onclick = () => host.action('open-logs');
  q('scenario').onchange = () => host.action('scenario', {value:q('scenario').value});
  function tabs(container, values, selectedValue, change) {
    container.replaceChildren(...values.map(([key,label]) => {
      const button=element('button',label);button.type='button';button.setAttribute('role','tab');button.setAttribute('aria-selected',String(key===selectedValue));button.tabIndex=key===selectedValue?0:-1;
      const identity=encodeURIComponent(container.id==='board-tabs'?drafts[key].board.board_id:key);
      button.id=container.id+'-tab-'+identity;button.setAttribute('aria-controls',container.id==='board-tabs'?'board-panel-'+identity:'log-panel');
      button.onclick=()=>{change(key);container.children[values.findIndex(([k])=>k===key)]?.focus();};button.onkeydown=event=>{const index=values.findIndex(([k])=>k===key);const next=event.key==='ArrowRight'?(index+1)%values.length:event.key==='ArrowLeft'?(index+values.length-1)%values.length:event.key==='Home'?0:event.key==='End'?values.length-1:null;if(next!==null){event.preventDefault();change(values[next][0]);container.children[next].focus();}};return button;
    }));
  }
  function logTabs(){tabs(q('log-tabs'),[['console','보드 콘솔'],['execution','TC 로그'],['connection','연결'],['errors','공통 오류']],selectedLog,key=>{selectedLog=key;logTabs();renderLog();});q('log-panel').setAttribute('aria-labelledby','log-tabs-tab-'+selectedLog);}
  logTabs();
  for (const id of ['search','errors-only']) q(id).addEventListener('input', renderLog);
  q('copy').onclick = async () => { try { const log = q('log'); await navigator.clipboard.writeText(log.value.slice(log.selectionStart,log.selectionEnd) || log.value); message('로그를 복사했습니다.'); } catch { message('자동 복사가 차단됐습니다. 로그에서 내용을 선택하고 Ctrl+C를 누르세요.', true); } };
  q('refresh-ports').onclick = () => host.ports();
  q('reload').onclick = () => { if (!q('dirty').textContent || confirm('편집 중인 초안을 최신 저장값으로 바꿀까요?')) host.reload(); };
  q('cancel').onclick = () => { if (saved) settings(saved); };
  for (const button of root.querySelectorAll('[data-pick]')) button.onclick = () => host.pick(button.dataset.pick, q({python:'python',ssh_key:'ssh-key',putty:'putty-path'}[button.dataset.pick]));
  function capture() {
    for (const [index, field] of [...q('board-forms').children].entries()) {
      const row = drafts[index]; row.name = field.querySelector('[name=name]').value;
      row.board.com = field.querySelector('[name=com]').value.trim(); const node = field.querySelector('[name=node]').value.trim();
      if (node) row.board.node = node; else delete row.board.node;
      row.baudrate = Number(field.querySelector('[name=baud]').value);
    }
  }
  function boardForms(count) {
    capture();
    while (drafts.length < count) drafts.push({board:{board_id:'board-'+crypto.randomUUID().replaceAll('-','').slice(0,12), host:saved?.profile.boards?.[0]?.host || 'TEST-PC',com:''},name:'보드 '+(drafts.length+1),observer:{},baudrate:115200});
    q('board-forms').replaceChildren();
    selectedSettingsBoard=Math.min(selectedSettingsBoard,count-1);
    function selectBoard(index){capture();selectedSettingsBoard=index;settingsTabs();for(const [i,field]of [...q('board-forms').children].entries())field.hidden=i!==index;}
    activateSettingsBoard=selectBoard;
    function settingsTabs(){tabs(q('board-tabs'),drafts.slice(0,count).map((row,index)=>[index,row.name||'보드 '+(index+1)]),selectedSettingsBoard,selectBoard);}
    settingsTabs();
    for (const [index,row] of drafts.slice(0,count).entries()) {
      const field = element('fieldset'); field.hidden=index!==selectedSettingsBoard;field.id='board-panel-'+encodeURIComponent(row.board.board_id);field.setAttribute('role','tabpanel');field.setAttribute('aria-labelledby','board-tabs-tab-'+encodeURIComponent(row.board.board_id)); field.append(element('legend', '보드 '+(index+1)));
      const grid = element('div', undefined, 'fields'); field.append(grid);
      for (const [name,label,value,type] of [['name','보드 이름',row.name,'text'],['com','보드 COM',row.board.com,'text'],['baud','통신 속도',row.baudrate || 115200,'number'],['node','노드 · 선택',row.board.node || '','text']]) {
        const item = element('label',label), input = element('input'); input.name=name; input.type=type; input.value=value; if (name==='com') {input.setAttribute('list','port-options');input.required=true;} if(name==='baud'){input.min='1';input.max='12000000';input.required=true;} item.append(input);grid.append(item);
      }
      q('board-forms').append(field);
    }
  }
  q('board-count').onchange=()=>{const count=Number(q('board-count').value);if(Number.isInteger(count)&&count>=1&&count<=32)boardForms(count);};

  function settings(value) {
    saved=clone(value);const profile=value.profile,setup=profile._setup || {};const note=root.querySelector('.board-detail .callout');note.querySelector('strong').textContent='자동 COM 공유';note.querySelector('p').textContent='커넥터가 물리 COM 하나를 열고 TC·콘솔·PuTTY에 출력을 나눕니다. PuTTY를 열면 입력 제어권을 받고 창을 닫으면 반환합니다.';renderSerialStatus();
    for(const [id,text] of Object.entries({server:setup.server || '',account:setup.account || '','server-port':setup.remote_dashboard_port || 8766,'ssh-port':setup.ssh_port || 22,'ssh-key':setup.ssh_key || '',python:profile.python || '','putty-path':profile.putty_path || ''}))q(id).value=text;
    q('board-forms').replaceChildren();
    drafts=(profile.boards || []).map(board=>({board:clone(board),name:profile.board_names?.[board.board_id] || board.board_id,observer:clone(profile.console_observers?.[board.board_id] || {}),baudrate:profile.serial_settings?.[board.board_id]?.baudrate || 115200}));
    const count=Math.max(1,drafts.length);drafts.push(...clone(profile.connector_inactive_boards || []));q('board-count').value=count;boardForms(count);dirty(false);renderServer();
  }
  q('local-form').onsubmit=event=>{event.preventDefault();if(!saved)return;capture();const active=drafts.slice(0,Number(q('board-count').value));const com=active.map(row=>row.board.com.toUpperCase());
    if(com.some(value=>!value)||new Set(com).size!==com.length){message('보드별 COM을 선택하고 중복을 해소하세요.',true);return;}
    const profile={_setup:{server:q('server').value.trim(),account:q('account').value.trim(),ssh_port:Number(q('ssh-port').value),remote_dashboard_port:Number(q('server-port').value),ssh_key:q('ssh-key').value.trim()},python:q('python').value.trim(),putty_path:q('putty-path').value.trim(),serial_transport:'proxy',boards:active.map(row=>row.board),board_names:Object.fromEntries(active.map(row=>[row.board.board_id,row.name])),serial_settings:Object.fromEntries(active.map(row=>[row.board.board_id,{...(saved.profile.serial_settings?.[row.board.board_id] || {}),baudrate:row.baudrate}])),console_observers:{...clone(saved.profile.console_observers || {}),...Object.fromEntries(active.filter(row=>Object.keys(row.observer || {}).length).map(row=>[row.board.board_id,row.observer]))},connector_inactive_boards:drafts.slice(active.length)};
    host.save({profile,revision:saved.revision});};
  function ports(values){portChoices=values;q('port-options').replaceChildren(...portChoices.map(port=>{const option=element('option',port.description || '');option.value=port.com;return option;}));}
  function renderLog(){const kind=selectedLog;let lines=[];
    if(kind==='console')lines=(snapshot.console?.boards || []).filter(row=>row.board_id===selected).map(row=>'['+row.board_id+' · '+(row.phase||'')+' · '+(row.code||'')+']\n'+(row.text||''));
    if(kind==='execution')lines=(snapshot.executions || []).filter(row=>!row.board_ids || row.board_ids.includes(selected)).map(row=>'['+row.id+' · '+row.state+']\n'+(row.stdout||'')+(row.stderr||''));
    if(kind==='connection')lines=connection;
    if(kind==='errors')lines=(snapshot.console?.errors || []).filter(row=>!row.board_id || row.board_id===selected).map(row=>JSON.stringify(row));
    let text=lines.join('\n').slice(-65536);if(q('errors-only').checked)text=text.split('\n').filter(line=>/ERROR|PANIC|FAIL|GAP|UNKNOWN|오류/i.test(line)).join('\n');const needle=q('search').value.toLocaleLowerCase();if(needle)text=text.split('\n').filter(line=>line.toLocaleLowerCase().includes(needle)).join('\n');text=text.split('\n').slice(-1000).join('\n');
    const log=q('log');if(log.value!==text){const following=log.scrollTop+log.clientHeight>=log.scrollHeight-5,scroll=log.scrollTop,start=log.selectionStart,end=log.selectionEnd;log.value=text;log.setSelectionRange(Math.min(start,text.length),Math.min(end,text.length));log.scrollTop=following?log.scrollHeight:scroll;}
    const meaning={console:'보드 UART 수신 · 부팅·시스템 출력',execution:'TC 프로그램 출력 · stdout/stderr',connection:'커넥터·서버 연결 이력',errors:'공통 서버에 전달된 오류 기록'}[kind];q('log-hint').textContent=meaning+(snapshot.stale||snapshot.console?.stale?' · 과거 수신 로그, 현재 상태 확인 필요':' · 최대 1,000줄 / 64 KiB');
  }
  function renderServer(){
    const setup=snapshot.connection_server||{},label=q('board-server');
    const connected=snapshot.state==='CONNECTED'&&snapshot.fresh===true&&!snapshot.stale;
    label.hidden=!connected||!setup.server;
    label.textContent=connected&&setup.server?'서버 · '+setup.server:'';
    label.title=setup.server?(setup.account?setup.account+'@':'')+setup.server+':'+(setup.ssh_port||22):'';
  }
  function renderSerialStatus(){const applied=snapshot.state==='CONNECTED'&&snapshot.fresh===true&&(snapshot.boards||[]).length>0&&snapshot.boards.every(board=>board.serial_proxy&&!board.stale);q('serial-status').textContent=applied?'자동 COM 공유 적용됨':'다음 연결 시 자동 적용';}
  function renderControls(){renderSerialStatus();const board=chosen(),proxy=board?.serial_proxy || {};const fresh=snapshot.state==='CONNECTED'&&snapshot.fresh===true&&!board?.stale;const busy=(snapshot.boards||[]).some(row=>['RUNNING','UNKNOWN','RESERVED'].includes(row.state)&&row.serial_proxy?.owner!=='manual');const ready=fresh&&proxy.state==='READY';const owner=proxy.owner==='manual',cleanup=(snapshot.putty_cleanup||[]).find(row=>row.board_id===selected);
    q('board-title').textContent=board?.name||board?.board_id||'보드를 선택하세요';q('board-subtitle').textContent=board?board.com+(cleanup?' · 입력 제어권 반환 중':owner?' · PuTTY 입력 중':proxy.owner==='execution'?' · TC 제어권 사용 중':''):'환경설정에서 보드를 등록하세요.';signal(q('board-state'),board?(board.stale?'UNKNOWN':board.state):'DISCONNECTED',board?(board.stale?'확인 필요':states[board.state]||board.state):'보드 미선택');
    const puttyLabel=cleanup?'제어권 반환 중':proxy.putty_connected?'PuTTY 열림':owner?'PuTTY 여는 중':'PuTTY 열기';q('putty').setAttribute('aria-label',puttyLabel);q('putty').title=(board?.name||board?.board_id||'보드')+' · '+puttyLabel;q('putty').disabled=pending||!!cleanup||!ready||busy||!!proxy.owner||proxy.putty_connected===true;
    q('control-reason').textContent=cleanup?'PuTTY 입력 제어권 반환을 재시도하고 있습니다.':!board?'먼저 보드를 선택하세요.':!fresh?'최근 상태 확인 전에는 제어할 수 없습니다.':proxy.state!=='READY'?'멀티플렉서 연결을 확인하세요.':busy?'시험·예약·종료 불명 작업이 남아 있어 PuTTY를 열 수 없습니다.':owner?'PuTTY 창을 닫으면 입력 제어권이 반환됩니다.':'';q('control-reason').hidden=!q('control-reason').textContent;
    const power=q('connection-power'),stopping=canRequestStop(),transition=snapshot.state==='DISCONNECTING'||(snapshot.state==='CONNECTING'&&!stopping);
    const busyBoard=snapshot.active_run?.active||snapshot.active_run?.analysis_latched||(snapshot.boards||[]).some(row=>row.stale||['RUNNING','PAUSED','UNKNOWN','RESERVED'].includes(row.state));
    power.disabled=pending||transition||(!stopping&&snapshot.state!=='DISCONNECTED')||snapshot.stale===true||(stopping&&busyBoard);
    power.dataset.state=snapshot.state||'WAITING';power.setAttribute('aria-pressed',String(stopping));power.setAttribute('aria-busy',String(pending||transition));
    const label=stopping?'종료':snapshot.state==='CONNECTING'?'연결 중':snapshot.state==='DISCONNECTING'?'종료 중':'시작';
    q('power-label').textContent=label;power.setAttribute('aria-label',transition?label:stopping?'연결 종료':'연결 시작');
    power.title=stopping&&busyBoard?'진행·예약·종료 불명 작업이 있어 연결을 종료할 수 없습니다.':snapshot.stale?'최근 연결 상태를 확인하고 있습니다.':stopping?'Windows 실행부와 서버 연결을 종료합니다.':'Windows 실행부와 SSH·서버 연결을 시작합니다. TC 실행과는 별개입니다.';
    q('save').disabled=pending||['CONNECTED','CONNECTING','DISCONNECTING'].includes(snapshot.state);
  }
  function render(value){snapshot=value;renderServer();q('cleanup-state').hidden=!(value.putty_cleanup||[]).length;q('cleanup-state').textContent=(value.putty_cleanup||[]).length?'PuTTY 입력 제어권 반환 재시도 중 · '+value.putty_cleanup.map(row=>row.board_id).join(', '):'';const boards=value.boards||[];signal(q('state'),value.stale?'UNKNOWN':value.state||'WAITING',value.stale?'상태 확인 필요':states[value.state]||value.state||'준비 중');const counts=[boards.length,boards.filter(row=>row.detected).length,boards.filter(row=>row.state==='RUNNING').length];for(const [index,id] of ['registered','detected','running'].entries())q('count-'+id).textContent=counts[index]+'대';const summary='등록 '+counts[0]+'대 · 감지 '+counts[1]+'대 · 시험 중 '+counts[2]+'대';q('summary').setAttribute('aria-label',summary);q('summary').title=summary;q('freshness').textContent=value.stale?'최근 보드 상태 수신이 지연됐습니다. 표시된 정보는 과거 기록입니다.':value.state==='CONNECTED'&&value.source_ready===false?'시험 전에 환경설정에서 서버 TC 소스를 선택하세요.':'';q('freshness').hidden=!q('freshness').textContent;
    const analyses=Array.isArray(value.analyses)?value.analyses:value.analyses?.analyses||value.pending_analyses||[];const analysis=analyses[0];const activeRun=value.active_run;q('analysis-state').textContent=[activeRun?'실행 묶음 '+activeRun.run_id.slice(0,8)+' · '+activeRun.state+(activeRun.analysis_latched?' (실패 분석 래치됨)':''):'',analysis?'플러그인 분석 · '+({PENDING:'분석 대기',ANALYZING:'분석 중',LEASED:'분석 중',HOLD:'조치 확인 대기',RETRY_READY:'재실행 준비',STOPPED:'재실행 중단'}[analysis.status]||analysis.status):''].filter(Boolean).join(' · ');
    const receipt = value.plugin_receipt;
    const current = value.fresh && !value.stale && value.state === 'CONNECTED';
    const labels = {CONNECTED:'연동 확인', STALE:'마지막 보고 만료', MISMATCH:'연결 정보 불일치'};
    const received = receipt && new Date(receipt.observed_at * 1000).toLocaleString('ko-KR');
    q('plugin-status').textContent = receipt
      ? '플러그인 ' + (current ? labels[receipt.state] || '확인 필요' : '현재 상태 확인 필요') + ' · 마지막 수신 ' + received + ' · ' + receipt.linux_host + ':' + receipt.port
      : '플러그인 연결 보고 대기';
    q('plugin-report').hidden = !receipt;
    q('plugin-values').textContent = receipt?.settings ? JSON.stringify(receipt.settings, null, 2) : '이 보고에서 확인할 수 있는 설정값이 없습니다.';
    const peerWarnings=value.peer_warnings||value.diagnostics?.peer_warnings||[];
    q('peer-banner').textContent=peerWarnings.length?'피어 연결 불일치 경고: '+peerWarnings.map(w=>(w.peer_type||'peer')+' ('+(w.client_issue?.code||w.client_status)+')').join(', '):'';
    q('peer-banner').hidden=!peerWarnings.length;
    const rd=value.readiness||value.diagnostics?.readiness;
    const rdWarnings=[];if(rd&&rd.com_port&&!rd.com_port.ready)rdWarnings.push('COM 포트 미감지');if(rd&&rd.tc_python&&!rd.tc_python.ready)rdWarnings.push('TC Python 미설정');
    q('readiness-warning').textContent=(value.state==='CONNECTED'&&rdWarnings.length)?'전송 연결됨 · 실행 준비 확인 필요: '+rdWarnings.join(', '):'';
    q('readiness-warning').hidden=!q('readiness-warning').textContent;
    for(const [key,[short,label,description]] of Object.entries(stageInfo)) {
      const row=q('stages').querySelector('[data-stage="'+key+'"]'),light=row.querySelector('.status-indicator');
      const reported=value.stages?.[key]||(key==='agent_monitor'?'OPTIONAL_OFFLINE':'WAITING'),code=value.stale&&reported==='READY'?'UNKNOWN':reported;
      const status={READY:'정상',CONNECTED:'연결됨',WAITING:'대기',OPTIONAL_OFFLINE:'선택(미연결)',UNKNOWN:'확인 필요 · 최근 상태 수신 지연',AUTH_OR_CONFIG_ERROR:'인증/설정 오류',RECONNECTING:'재연결 중',REGISTRATION_FAILED:'실패'}[code]||states[code]||code;
      signal(light,code==='OPTIONAL_OFFLINE'?'DISCONNECTED':code,label+' · '+status);light.removeAttribute('title');
      row.querySelector('.stage-tooltip').textContent=label+' · '+status+'\n'+description;
    }
    const diagMsg=value.diagnostics?.ssh_diagnostic?.summary&&value.state!=='CONNECTED'?value.diagnostics.ssh_diagnostic.summary:'';
    let error=value.error||diagMsg||'';if(error.includes('401'))error+='\n서버가 등록을 거부했습니다. 서버·커넥터 버전과 실제 응답 내용을 확인하세요. 구버전 토큰 요구 여부는 확인이 필요합니다.';q('error').textContent=error;q('error').hidden=!error;
    const mark=value.state+'|'+(value.error||'');if(mark!==lastConnection){connection.push(new Date().toLocaleTimeString()+' '+(value.error?'ERROR '+value.error:value.state));if(connection.length>300)connection.shift();lastConnection=mark;}
    const ids=new Set(boards.map(board=>board.board_id));for(const [id,item]of items)if(!ids.has(id)){item.remove();items.delete(id);}if(!ids.has(selected))selected=boards[0]?.board_id||null;
    for(const board of boards){let item=items.get(board.board_id);if(!item){item=element('button');item.type='button';item.append(element('span',undefined,'board-status status-indicator'),element('span',undefined,'board-name'));item.onclick=()=>{selected=board.board_id;render(snapshot);};items.set(board.board_id,item);q('boards').append(item);}const name=board.name||board.board_id,state=board.stale?'확인 필요':states[board.state]||board.state;const title=name+' · '+board.com+' · '+state;const nameNode=item.querySelector('.board-name');if(nameNode.textContent!==name)nameNode.textContent=name;item.title=title;item.setAttribute('aria-label',title);signal(item.querySelector('.board-status'),board.stale?'UNKNOWN':board.state,state);item.setAttribute('aria-pressed',String(selected===board.board_id));}
    q('paths').textContent=value.path_text||'서버 경로 미수신';q('storage').textContent=value.storage?'Windows 로컬 사용량 '+(value.storage.runtime_bytes/1024**2).toFixed(1)+' MiB'+(value.storage.partial?' · 일부 집계':'')+(value.storage.protected?' · 진행 작업 보호':''):'';
    const dashboard=q('dashboard');
    let url;
    if (value.fresh === true && !value.stale && (value.state === 'CONNECTED' || value.connection_mode === 'legacy')) {
      try {
        const link=new URL(value.dashboard_url);
        if (link.protocol==='http:' && link.hostname==='127.0.0.1' && !link.username && !link.password) url=link.href;
      } catch {}
    }
    if (url) dashboard.href=url;
    else dashboard.removeAttribute('href');
    dashboard.hidden=!url;
    syncShared(value);renderControls();renderLog();renderTests();}
  let testSignature='';
  for(const id of ['tc-search','tc-filter'])q(id).addEventListener('input',renderTests);
  const tcLabels={PENDING:'대기 중',RUNNING:'진행 중',PASS:'PASS',PASSED:'PASS',FAIL:'FAIL',FAILED:'FAIL',ERROR:'FAIL · 실행 오류',TIMEOUT:'FAIL · 시간 초과',UNKNOWN:'확인 필요',CANCELLED:'취소됨',NOT_SELECTED:'미선택',NOT_RUN:'미실행'};
  const normTcState=s=>s==='PASSED'?'PASS':s==='FAILED'?'FAIL':(s||'NOT_RUN');
  function renderTests(){
    let data=snapshot.test_status;
    if(data?.steps?.length && data.active_run && (data.active_run.active || !data.has_projection)){
      const run=data.active_run;
      data={...data,tc_root:null,source:{location:(run?.active?'현재 실행':'최근 실행')+' · '+run.run_id},
        message:'플러그인이 지정한 실행 순서',projection_stale:false,
        items:data.steps.map(step=>({path:step.path,run_step:step}))};
    }
    const stale=snapshot.state!=='CONNECTED'||snapshot.fresh!==true||snapshot.stale||data?.stale||data?.projection_stale;
    q('tc-source').textContent=data?.source?.location||data?.tc_root||'TC 경로 미수신';
    q('tc-source').title=q('tc-source').textContent;
    q('tc-status-note').textContent=[stale&&data?'과거 수신 정보 · 현재 상태 확인 필요':'',data?.message||(!data?'플러그인 연결 또는 TC 투영 후 목록을 확인할 수 있습니다.':''),'상태 조회 전용 · 실행 제어는 플러그인·Agent Monitor에서 수행합니다.'].filter(Boolean).join(' · ');
    q('tc-status-note').title=q('tc-status-note').textContent;
    const needle=q('tc-search').value.toLocaleLowerCase(),filter=q('tc-filter').value;
    const rawItems=data?.items?data.items.map(it=>{const st=it.run_step;const raw=st?.state||'NOT_RUN';const norm=normTcState(raw);return {path:it.path,status:st?{state:norm,label:tcLabels[raw]||tcLabels[norm]||raw,run_id:st.run_id,run_state:raw}:{state:'NOT_RUN',label:'미실행'}};}):(data?.rows||[]).map(row=>({path:row.path,status:row.boards?.[selected]}));
    const rows=rawItems.filter(row=>{
      const state=normTcState(row.status?.state);
      return row.path.toLocaleLowerCase().includes(needle)&&(filter==='all'||filter===state||(filter==='PASS'&&['PASS','PASSED'].includes(state))||(filter==='FAIL'&&['FAIL','FAILED','ERROR','TIMEOUT'].includes(state)));
    });
    const signature=JSON.stringify([selected,rows]);if(signature===testSignature)return;testSignature=signature;
    q('tc-status-rows').replaceChildren(...rows.map(row=>{const tr=element('tr'),path=element('td',row.path),status=element('td');const state=row.status;const norm=normTcState(state?.state);status.textContent=state?.label||tcLabels[norm]||'미실행';status.dataset.state=norm;status.title=state?`${state.historical?'이전 실행':'현재 실행'} · ${state.run_id||''} · ${state.run_state||''}`:'';tr.append(path,status);return tr;}));
    q('tc-empty').hidden=rows.length>0;
  }
  function applicationText(value){return 'Windows 적용: '+({UNCONFIGURED:'미설정',SAVED:'로컬 저장',PENDING:'적용 대기',APPLIED:'적용 확인',BLOCKED:'적용 차단'}[value.state]||value.state||'확인 전')+(value.reason?' · '+value.reason:'');}
  q('load-shared').onclick=()=>host.shared();
  function lookupText(value, previous) {
    const path = value.integration.tc_root;
    const same = path && previous?.integration?.tc_root === path && previous.settings_source === value.settings_source;
    const result = path ? (same ? 'TC 소스 경로 변경 없음 · ' : 'TC 소스 경로 · ') + path : 'Linux TC 소스 경로 미설정';
    return [value.settings_source, result].filter(Boolean).join(' · ');
  }
  function sharedStatus(value) {
    const status = value.read_only ? 'Linux 서버 설정 수신 · 읽기 전용' : applicationText(value.connector_application||{});
    return status + ' · ' + lookupText(value);
  }
  function shared(value){
    const previous = sharedValue;
    sharedValue=clone(value);
    sharedDirty=false;
    q('shared-fields').disabled=Boolean(value.read_only);
    q('tc-root').disabled=Boolean(value.offline_direct);
    q('browse-source').disabled=Boolean(value.offline_direct);
    q('flash-fields').disabled=Boolean(value.offline_direct);
    q('installer').value=value.integration.installer_path||'';
    q('installer-roots').value=(value.integration.installer_roots||[]).join('\n');
    q('flash-profile').value=value.integration.flash_profile||'';
    q('tc-root').value=value.integration.tc_root||'';
    q('tc-root').placeholder=value.offline_direct?'Linux 서버 설정 확인 대기':'Linux 서버에 TC 소스 경로 미설정';
    q('timeout').value=value.timeouts.default_seconds??'';
    q('shared-state').textContent=value.offline_direct?'Windows 로컬 설정 · Linux 공통 서버 연결 대기':sharedStatus(value);
    return lookupText(value, previous);
  }
  q('shared-form').onsubmit=event=>{
    event.preventDefault();
    if(!sharedValue)return;
    const timeouts={...sharedValue.timeouts,default_seconds:q('timeout').value?Number(q('timeout').value):null};
    delete timeouts.revision;
    const integration=sharedValue.offline_direct?{}:{...sharedValue.integration,tc_root:q('tc-root').value.trim()};
    if(!sharedValue.offline_direct){
      integration.installer_path=q('installer').value.trim();
      integration.installer_roots=q('installer-roots').value.split('\n').map(path=>path.trim()).filter(Boolean);
      const profile=q('flash-profile').value.trim();
      if(profile!==(integration.flash_profile||''))integration.flash_profile_revision=null;
      integration.flash_profile=profile;
    }
    host.saveShared({expected_revision:sharedValue.revision,integration,timeouts});
  };
  for(const [id,kind]of [['browse-installer','installer'],['browse-source','source']])q(id).onclick=()=>{browseKind=kind;host.paths(kind,'');};
  function paths(value){browseKind=value.kind;browsePath=value.path||'';q('server-browser').hidden=false;q('server-folder').textContent=browsePath||'서버에서 허용한 루트를 선택하세요.';q('use-folder').hidden=browseKind!=='source'||!browsePath;const entries=value.path?value.entries:value.roots.map(path=>({name:path,path,directory:true}));if(!entries.length){q('server-entries').replaceChildren(element('p',browsePath?'표시할 하위 항목이 없습니다.':'허용된 서버 폴더가 없습니다. 서버 접근 범위(이미지/TC 허용 폴더)를 먼저 설정하세요.','muted'));}else{q('server-entries').replaceChildren(...entries.map(entry=>{const button=element('button',(entry.directory?'폴더 · ':'파일 · ')+entry.name);button.type='button';button.onclick=()=>{if(entry.directory)host.paths(browseKind,entry.path);else if(browseKind==='installer'){q('installer').value=entry.path;sharedDirty=true;}};return button;}));}q('server-browser').scrollIntoView({block:'nearest'});}
  q('use-folder').onclick=()=>{q('tc-root').value=browsePath;sharedDirty=true;};
  q('load-storage').onclick=()=>host.storage();
  function storage(value){storageValue=clone(value);q('storage-form').hidden=false;q('storage-enabled').checked=value.enabled;q('storage-days').value=value.max_age_seconds/86400;q('storage-limit').value=value.max_bytes/1024**3;q('storage-state').textContent='Windows 적용: '+(value.connector_sync?.state||'확인 전');}
  q('storage-form').onsubmit=event=>{event.preventDefault();if(storageValue)host.saveStorage({expected_revision:storageValue.revision,enabled:q('storage-enabled').checked,max_age_seconds:Math.round(Number(q('storage-days').value)*86400),max_bytes:Math.round(Number(q('storage-limit').value)*1024**3)});};
  q('preview-cleanup').onclick=()=>host.cleanup(true);q('apply-cleanup').onclick=()=>host.cleanup(false);
  function cleanup(value){const rows=[];for(const [name,report]of [['Linux',value],['Windows',value.connector_cleanup?.report||value.connector_cleanup]]){if(!report)continue;rows.push(name+' · '+(report.skipped_reason||report.reason||report.state||((report.dry_run?'정리 예정 ':'정리됨 ')+((report.dry_run?report.planned_bytes:report.deleted_bytes)||0)/1024**2+' MiB'))+(report.over_budget?' · 용량 한도 초과':'')+(report.batch_limited?' · 다음 주기에 계속 정리':'')+(report.measurement_complete===false?' · 일부 집계':''));}q('cleanup-report').textContent=rows.join('\n');}
  return {render,settings,ports,shared,paths,storage,cleanup,message,preview(value){q('preview').hidden=!value;q('scenario-row').hidden=!value;},busy(value,form){pending=value;if(form)for(const input of q(form+'-form').querySelectorAll('input,select,textarea'))input.disabled=value;for(const id of ['load-storage','save-storage','preview-cleanup','apply-cleanup','save-shared','load-shared','refresh-ports','reload','cancel','scenario','browse-installer','browse-source','use-folder'])q(id).disabled=value;for(const button of root.querySelectorAll('[data-pick],#server-entries button'))button.disabled=value;if(!value && sharedValue?.offline_direct){q('tc-root').disabled=true;q('browse-source').disabled=true;}renderControls();},unavailable(text){snapshot={...snapshot,dashboard_url:'',fresh:false,stale:true,boards:(snapshot.boards||[]).map(board=>({...board,stale:true}))};render(snapshot);message(text,true);}};
}
