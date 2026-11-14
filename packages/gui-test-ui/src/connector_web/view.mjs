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
  root.innerHTML = `<header class="header"><div><div class="eyebrow">WINDOWS · BOARD CONNECTOR</div><h1>보드 커넥터 <span id="preview" class="badge" hidden>모의 미리보기</span></h1><p>보드의 상태를 보고, 연결과 제어를 한곳에서 관리하세요.</p></div><span id="state" class="status-indicator"></span></header>
  <div id="notice" class="notice" role="status" aria-live="polite" hidden></div>
  <nav class="tabs" aria-label="화면 선택"><button id="overview-tab" aria-current="page">보드 현황</button><button id="settings-tab">환경설정 <span id="dirty"></span></button></nav>
  <section id="overview"><div class="toolbar"><div><strong id="summary">등록된 보드를 확인하고 있습니다.</strong><p id="freshness" class="muted">화면을 닫아도 연결과 시험은 계속됩니다.</p></div><div class="actions"><button id="connection-power" class="connection-power" type="button" aria-label="연결 시작" aria-pressed="false" disabled><span class="power-symbol" aria-hidden="true">⏻</span><span id="power-label">시작</span></button><a id="dashboard" class="button" target="_blank" rel="noreferrer" hidden>Agent Monitor 열기</a></div></div>
  <p id="analysis-state" class="muted" aria-live="polite"></p><div id="stages" class="stages" aria-label="연결 단계"></div><div id="error" class="error" role="alert" hidden></div>
  <div class="workspace"><aside class="panel board-sidebar"><h2>보드 리스트</h2><div id="boards" class="board-list" role="group" aria-label="보드 선택"></div></aside>
  <section class="panel board-detail"><div class="section-heading"><div><h2 id="board-title">보드를 선택하세요</h2><p id="board-subtitle" class="muted">보드가 없어도 환경설정과 기록을 확인할 수 있습니다.</p></div><span id="board-state" class="status-indicator"></span></div>
  <div class="actions"><button id="putty">PuTTY 열기</button><button id="manual">수동 제어 시작</button></div><p id="control-reason" class="muted"></p>
  <details id="connection-details" class="connection-details"><summary>연결 상세 · 콘솔 안내</summary><div class="callout"><strong>COM 멀티플렉서</strong><p>커넥터가 물리 COM 하나를 열고 TC·콘솔·PuTTY에 출력을 나눕니다.</p></div><p class="muted">보드 콘솔은 보드의 UART 수신 로그입니다. PuTTY는 같은 보드의 별도 터미널 창이며, 명령 입력은 수동 제어권을 받은 뒤 사용할 수 있습니다. COM 감지는 부팅·시험 통과를 뜻하지 않습니다.</p><p class="muted">신호등: 초록 정상 · 노랑 진행/확인 필요 · 빨강 오류 · 회색 미연결/대기.</p></details>
  <section id="log-window" class="log-window" aria-label="로그 보기"><div class="log-heading"><h3>로그 보기</h3><button id="open-logs">로그 폴더 열기</button></div>
  <div class="log-tools"><div id="log-tabs" class="subtabs" role="tablist" aria-label="로그 종류"></div><input id="search" placeholder="현재 로그에서 검색" aria-label="로그 검색"><label class="check"><input type="checkbox" id="errors-only">오류만</label><button id="copy">복사</button></div>
  <div id="log-panel" role="tabpanel"><p id="log-hint" class="muted"></p><textarea id="log" readonly spellcheck="false" aria-label="선택 보드 로그"></textarea></div></section>
  <details><summary>소스와 실행 경로</summary><pre id="paths">서버 경로 미수신</pre><p id="storage" class="muted"></p></details></section></div>
  <div id="scenario-row" class="panel" hidden><label>모의 상태 <select id="scenario"><option>연결</option><option>시험 중</option><option>오류</option><option>미연결</option><option>확인 필요</option></select></label></div></section>
  <section id="settings" hidden><div class="settings-grid"><form id="local-form" class="panel"><div class="section-heading"><div><h2>Windows 연결 설정</h2><p class="muted">연결을 종료한 뒤 변경하세요. 기존 작업과 설정은 보존됩니다.</p></div><span id="draft-state" class="badge">저장된 설정</span></div>
  <div class="fields"><label>Linux SSH 서버<input id="server" required placeholder="서버 주소"></label><label>SSH 계정<input id="account" required autocomplete="username"></label><label>Agent Monitor 서버 포트<input id="server-port" type="number" min="1" max="65535" value="8766" required></label></div>
  <label>TC Python 전체 경로<span class="path-field"><input id="python" placeholder="C:\\TC\\Python\\python.exe"><button type="button" data-pick="python">찾아보기</button></span></label><p class="muted">커넥터 실행용 Python과 별개입니다. 파일 선택을 지원하지 않으면 전체 경로를 직접 입력하세요.</p>
  <details><summary>상세 연결 설정</summary><div class="fields"><label>SSH 포트<input id="ssh-port" type="number" min="1" max="65535" value="22" required></label><label>SSH 개인 키 전체 경로<span class="path-field"><input id="ssh-key"><button type="button" data-pick="ssh_key">찾아보기</button></span></label><label>PuTTY 전체 경로<span class="path-field"><input id="putty-path" placeholder="자동 검색"><button type="button" data-pick="putty">찾아보기</button></span></label></div><p class="muted">SSH 키/agent와 host key 인증은 Windows OpenSSH에서 먼저 준비해야 합니다.</p></details>
  <div class="fields"><label>통신 방식<select id="transport"><option value="proxy">포트 멀티플렉서</option><option value="native">기존 COM 직접 연결</option></select></label><label>보드 수<input id="board-count" type="number" min="1" max="32" value="1" required></label></div><p class="muted">멀티플렉서는 TC 공통 모듈의 Serial 어댑터 연결이 필요합니다. 기존 native 설정은 자동 전환하지 않습니다.</p>
  <div class="actions"><button id="refresh-ports" type="button">COM 목록 새로고침</button></div><datalist id="port-options"></datalist><div id="board-tabs" class="subtabs" role="tablist" aria-label="보드 설정 선택"></div><div id="board-forms"></div>
  <footer class="form-footer"><button class="primary" id="save" type="submit">Windows 설정 저장</button><button id="cancel" type="button">변경 취소</button><button id="reload" type="button">최신 설정 불러오기</button></footer></form>
  <section class="panel"><h2>서버 공통 설정</h2><p class="muted">플러그인·Agent Monitor와 같은 설정입니다. Windows 로컬 경로와 Linux 서버 경로를 구분하세요.</p><p id="shared-state" class="callout">서버에 연결한 뒤 불러오세요.</p><button id="load-shared">서버 공통 설정 불러오기</button>
  <form id="shared-form" hidden><label>Linux 설치 BAT 경로<input id="installer"></label><button id="browse-installer" type="button">서버 BAT 폴더 탐색</button><label>Linux TC 소스 경로<input id="tc-root"></label><button id="browse-source" type="button">서버 TC 폴더 탐색</button><label>TC 기본 제한시간 · 초<input id="timeout" type="number" min="1" max="86400"></label><p class="muted">TC별 재정의와 진행 중 실행의 고정 설정은 보존합니다.</p><button id="save-shared" class="primary">서버 공통 설정 저장</button></form>
  <details><summary>저장 공간 자동 정리</summary><p class="muted">기본 7일 · 20 GiB. 진행 중 작업과 실패 근거는 보존합니다. 보호 파일이 많으면 한도를 넘을 수 있습니다.</p><button id="load-storage" type="button">정리 기준 불러오기</button><form id="storage-form" hidden><label class="check"><input id="storage-enabled" type="checkbox">자동 정리</label><label>보관 기간 · 일<input id="storage-days" type="number" min="0.042" step="any" required></label><label>캐시 한도 · GiB<input id="storage-limit" type="number" min="0.001" step="any" required></label><button id="save-storage">정리 기준 저장</button></form><p id="storage-state" class="muted"></p><div class="actions"><button id="preview-cleanup" type="button">정리 대상 확인</button><button id="apply-cleanup" type="button">지금 정리</button></div><pre id="cleanup-report"></pre></details><div id="server-browser" hidden><h3>서버 폴더</h3><p id="server-folder" class="muted"></p><button id="use-folder" type="button">이 폴더 선택</button><div id="server-entries"></div></div></section></div></section>
  <footer class="page-footer">화면 닫기 ≠ 연결 종료 · 연결과 장비 작업은 Windows 실행부에서 유지됩니다.</footer>`;
  const q = id => root.querySelector('#' + id);
  const stageInfo = {
    local:['Windows','Windows 실행부','PC에서 보드 연결과 시험을 담당하는 실행부입니다.'],
    ssh:['SSH','SSH 연결','Windows에서 Linux 서버로 연결하는 보안 통신입니다.'],
    dashboard:['서버','서버 연결','Linux의 Agent Monitor 서버 응답을 확인합니다.'],
    roundtrip:['왕복','왕복 등록','서버가 Windows 커넥터에 다시 연결할 수 있는지 확인합니다.']
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
  for (const tab of ['overview', 'settings']) q(tab + '-tab').onclick = () => { for (const name of ['overview','settings']) { q(name).hidden = name !== tab; q(name + '-tab').setAttribute('aria-current', name === tab ? 'page' : 'false'); } };
  const chosen = () => (snapshot.boards || []).find(board => board.board_id === selected);
  q('connection-power').onclick = () => { if(!q('connection-power').disabled)host.action(['CONNECTED','ERROR'].includes(snapshot.state)?'disconnect':'connect'); };
  q('putty').onclick = () => host.action('putty', {board_id:selected});
  q('manual').onclick = () => host.action('manual', {board_id:selected, manual:chosen()?.serial_proxy?.owner !== 'manual'});
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
      row.observer = {...row.observer, port:field.querySelector('[name=rx]').value.trim(), rx_only_confirmed:field.querySelector('[name=confirmed]').checked, control_lines_isolated:field.querySelector('[name=confirmed]').checked};
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
      for (const [name,label,value,type] of [['name','보드 이름',row.name,'text'],['com','제어 COM',row.board.com,'text'],['baud','통신 속도',row.baudrate || 115200,'number'],['node','노드 · 선택',row.board.node || '','text']]) {
        const item = element('label',label), input = element('input'); input.name=name; input.type=type; input.value=value; if (name==='com') {input.setAttribute('list','port-options');input.required=true;} if(name==='baud'){input.min='1';input.max='12000000';input.required=true;} item.append(input);grid.append(item);
      }
      const legacy = element('div',undefined,'legacy fields'); legacy.hidden=q('transport').value!=='native';
      const label = element('label','RX 전용 COM'), rx=element('input');rx.name='rx';rx.value=row.observer?.port || '';rx.setAttribute('list','port-options');label.append(rx);legacy.append(label);
      const check=element('label','RX 전용·제어선 격리를 확인했습니다.','check'), input=element('input');input.type='checkbox';input.name='confirmed';input.checked=row.observer?.rx_only_confirmed===true;check.prepend(input);legacy.append(check);field.append(legacy);q('board-forms').append(field);
    }
  }
  q('board-count').onchange=()=>{const count=Number(q('board-count').value);if(Number.isInteger(count)&&count>=1&&count<=32)boardForms(count);};
  q('transport').onchange=()=>{for(const section of root.querySelectorAll('.legacy'))section.hidden=q('transport').value!=='native';};
  function settings(value) {
    saved=clone(value);const profile=value.profile,setup=profile._setup || {};const note=root.querySelector('.board-detail .callout');note.querySelector('strong').textContent=profile.serial_transport==='proxy'?'COM 멀티플렉서':'기존 COM 직접 연결';note.querySelector('p').textContent=profile.serial_transport==='proxy'?'커넥터가 물리 COM 하나를 열고 TC·콘솔·PuTTY에 출력을 나눕니다. PuTTY는 기본 조회 전용이며, 입력하려면 수동 제어권을 받아야 합니다.':'기존 native 방식입니다. 콘솔 동시 관찰에는 RX 전용 포트 구성이 필요합니다. 멀티플렉서 전환은 연결 종료 후 명시적으로 선택하세요.';
    for(const [id,text] of Object.entries({server:setup.server || '',account:setup.account || '','server-port':setup.remote_dashboard_port || 8766,'ssh-port':setup.ssh_port || 22,'ssh-key':setup.ssh_key || '',python:profile.python || '','putty-path':profile.putty_path || ''}))q(id).value=text;
    q('transport').value=profile.serial_transport || 'native';q('board-forms').replaceChildren();
    drafts=(profile.boards || []).map(board=>({board:clone(board),name:profile.board_names?.[board.board_id] || board.board_id,observer:clone(profile.console_observers?.[board.board_id] || {}),baudrate:profile.serial_settings?.[board.board_id]?.baudrate || 115200}));
    const count=Math.max(1,drafts.length);drafts.push(...clone(profile.connector_inactive_boards || []));q('board-count').value=count;boardForms(count);dirty(false);
  }
  q('local-form').onsubmit=event=>{event.preventDefault();if(!saved)return;capture();const active=drafts.slice(0,Number(q('board-count').value));const com=active.map(row=>row.board.com.toUpperCase());const rx=active.map(row=>row.observer?.port?.toUpperCase()).filter(Boolean);
    if(com.some(value=>!value)||new Set(com).size!==com.length||(q('transport').value==='native'&&(new Set(rx).size!==rx.length||rx.some(value=>com.includes(value))||active.some(row=>row.observer?.port&&!row.observer.rx_only_confirmed)))){message('보드별 COM 중복과 RX 전용 확인을 확인하세요.',true);return;}
    const profile={_setup:{server:q('server').value.trim(),account:q('account').value.trim(),ssh_port:Number(q('ssh-port').value),remote_dashboard_port:Number(q('server-port').value),ssh_key:q('ssh-key').value.trim()},python:q('python').value.trim(),putty_path:q('putty-path').value.trim(),serial_transport:q('transport').value,boards:active.map(row=>row.board),board_names:Object.fromEntries(active.map(row=>[row.board.board_id,row.name])),serial_settings:Object.fromEntries(active.map(row=>[row.board.board_id,{...(saved.profile.serial_settings?.[row.board.board_id] || {}),baudrate:row.baudrate}])),console_observers:Object.fromEntries(active.filter(row=>row.observer?.port).map(row=>[row.board.board_id,row.observer])),connector_inactive_boards:drafts.slice(active.length)};
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
  function renderControls(){const board=chosen(),proxy=board?.serial_proxy || {};const fresh=snapshot.state==='CONNECTED'&&snapshot.fresh===true&&!board?.stale;const busy=(snapshot.boards||[]).some(row=>['RUNNING','UNKNOWN','RESERVED'].includes(row.state)&&row.serial_proxy?.owner!=='manual');const ready=fresh&&proxy.state==='READY';const owner=proxy.owner==='manual';
    q('board-title').textContent=board?.name||board?.board_id||'보드를 선택하세요';q('board-subtitle').textContent=board?board.com+(owner?' · 수동 제어권 사용 중':proxy.owner==='execution'?' · TC 제어권 사용 중':''):'환경설정에서 보드를 등록하세요.';signal(q('board-state'),board?(board.stale?'UNKNOWN':board.state):'DISCONNECTED',board?(board.stale?'확인 필요':states[board.state]||board.state):'보드 미선택');
    q('manual').textContent=owner?'수동 제어 종료':'수동 제어 시작';q('manual').disabled=pending||!ready||(!owner&&(busy||!!proxy.owner));q('putty').disabled=pending||!ready||proxy.putty_connected===true;
    q('control-reason').textContent=!board?'먼저 보드를 선택하세요.':!fresh?'최근 상태 확인 전에는 제어할 수 없습니다.':proxy.state!=='READY'?'멀티플렉서 연결을 확인하세요.':busy&&!owner?'시험·예약·종료 불명 작업이 남아 있어 수동 제어를 시작할 수 없습니다.':owner?'PuTTY를 다시 열면 입력할 수 있습니다. 기존 조회 연결의 입력은 재전송하지 않습니다.':'명령 입력은 PuTTY에서 수동 제어 후 사용하세요.';
    const power=q('connection-power'),stopping=['CONNECTED','ERROR'].includes(snapshot.state),transition=['CONNECTING','DISCONNECTING'].includes(snapshot.state);
    const busyBoard=(snapshot.boards||[]).some(row=>['RUNNING','UNKNOWN','RESERVED'].includes(row.state));
    power.disabled=pending||transition||!['DISCONNECTED','CONNECTED','ERROR'].includes(snapshot.state)||snapshot.stale===true||(stopping&&busyBoard);
    power.dataset.state=snapshot.state||'WAITING';power.setAttribute('aria-pressed',String(stopping));power.setAttribute('aria-busy',String(pending||transition));
    const label=snapshot.state==='CONNECTING'?'연결 중':snapshot.state==='DISCONNECTING'?'종료 중':stopping?'종료':'시작';
    q('power-label').textContent=label;power.setAttribute('aria-label',transition?label:stopping?'연결 종료':'연결 시작');
    power.title=stopping&&busyBoard?'진행·예약·종료 불명 작업이 있어 연결을 종료할 수 없습니다.':snapshot.stale?'최근 연결 상태를 확인하고 있습니다.':stopping?'Windows 실행부와 서버 연결을 종료합니다.':'Windows 실행부와 SSH·서버 연결을 시작합니다. TC 실행과는 별개입니다.';
    q('save').disabled=pending||['CONNECTED','CONNECTING','DISCONNECTING'].includes(snapshot.state);
  }
  function render(value){snapshot=value;const boards=value.boards||[];signal(q('state'),value.stale?'UNKNOWN':value.state||'WAITING',value.stale?'상태 확인 필요':states[value.state]||value.state||'준비 중');q('summary').textContent='등록 '+boards.length+'대 · 감지 '+boards.filter(row=>row.detected).length+'대 · 시험 중 '+boards.filter(row=>row.state==='RUNNING').length+'대';q('freshness').textContent=value.stale?'최근 보드 상태 수신이 지연됐습니다. 표시된 정보는 과거 기록입니다.':value.state==='DISCONNECTED'?'전원 버튼으로 Windows 실행부와 서버 연결을 시작하세요.':value.source_ready===false?'연결은 정상입니다. 시험 전에 환경설정에서 서버 TC 소스를 선택하세요.':'화면을 닫아도 연결과 시험은 계속됩니다.';
    const analyses=Array.isArray(value.analyses)?value.analyses:value.analyses?.analyses||[];const analysis=analyses[0];q('analysis-state').textContent=analysis?'플러그인 분석 · '+({PENDING:'분석 대기',LEASED:'분석 중',HOLD:'조치 확인 대기',RETRY_READY:'재실행 준비',STOPPED:'재실행 중단'}[analysis.status]||analysis.status):'';
    for(const [key,[short,label,description]] of Object.entries(stageInfo)) {
      const row=q('stages').querySelector('[data-stage="'+key+'"]'),light=row.querySelector('.status-indicator');
      const reported=value.stages?.[key]||'WAITING',code=value.stale&&reported==='READY'?'UNKNOWN':reported;
      const status={READY:'정상',WAITING:'대기',UNKNOWN:'확인 필요 · 최근 상태 수신 지연',REGISTRATION_FAILED:'실패'}[code]||states[code]||code;
      signal(light,code,label+' · '+status);light.removeAttribute('title');
      row.querySelector('.stage-tooltip').textContent=label+' · '+status+'\n'+description;
    }
    let error=value.error||'';if(error.includes('401'))error+='\n서버가 등록을 거부했습니다. 서버·커넥터 버전과 실제 응답 내용을 확인하세요. 구버전 토큰 요구 여부는 확인이 필요합니다.';q('error').textContent=error;q('error').hidden=!error;
    const mark=value.state+'|'+(value.error||'');if(mark!==lastConnection){connection.push(new Date().toLocaleTimeString()+' '+(value.error?'ERROR '+value.error:value.state));if(connection.length>300)connection.shift();lastConnection=mark;}
    const ids=new Set(boards.map(board=>board.board_id));for(const [id,item]of items)if(!ids.has(id)){item.remove();items.delete(id);}if(!ids.has(selected))selected=boards[0]?.board_id||null;
    for(const board of boards){let item=items.get(board.board_id);if(!item){item=element('button');item.type='button';item.append(element('span',undefined,'board-name'),element('span',undefined,'board-port'),element('span',undefined,'board-status status-indicator'));item.onclick=()=>{selected=board.board_id;render(snapshot);};items.set(board.board_id,item);q('boards').append(item);}const name=board.name||board.board_id,state=board.stale?'확인 필요':states[board.state]||board.state;const title=name+' · '+board.com+' · '+state;const nameNode=item.querySelector('.board-name'),portNode=item.querySelector('.board-port');if(nameNode.textContent!==name)nameNode.textContent=name;if(portNode.textContent!==board.com)portNode.textContent=board.com;item.title=title;item.setAttribute('aria-label',title);signal(item.querySelector('.board-status'),board.stale?'UNKNOWN':board.state,state);item.setAttribute('aria-pressed',String(selected===board.board_id));}
    q('paths').textContent=value.path_text||'서버 경로 미수신';q('storage').textContent=value.storage?'Windows 로컬 사용량 '+(value.storage.runtime_bytes/1024**2).toFixed(1)+' MiB'+(value.storage.partial?' · 일부 집계':'')+(value.storage.protected?' · 진행 작업 보호':''):'';const url=(()=>{try{const link=new URL(value.dashboard_url);return link.protocol==='http:'&&link.hostname==='127.0.0.1'&&!link.username&&!link.password?link.href:null;}catch{return null;}})();q('dashboard').hidden=!url;if(url)q('dashboard').href=url;
    const app=value.shared_settings?.connector_application;if(app)q('shared-state').textContent=applicationText(app);if(value.shared_error)q('shared-state').textContent='공통 설정 조회 실패 · '+value.shared_error;renderControls();renderLog();}
  function applicationText(value){return 'Windows 적용: '+({UNCONFIGURED:'미설정',SAVED:'로컬 저장',PENDING:'적용 대기',APPLIED:'적용 확인',BLOCKED:'적용 차단'}[value.state]||value.state||'확인 전')+(value.reason?' · '+value.reason:'');}
  q('load-shared').onclick=()=>host.shared();
  function shared(value){sharedValue=clone(value);q('shared-form').hidden=false;q('installer').value=value.integration.installer_path||'';q('tc-root').value=value.integration.tc_root||'';q('timeout').value=value.timeouts.default_seconds??'';q('shared-state').textContent=applicationText(value.connector_application||{});}
  q('shared-form').onsubmit=event=>{event.preventDefault();if(!sharedValue)return;const timeouts={...sharedValue.timeouts,default_seconds:q('timeout').value?Number(q('timeout').value):null};delete timeouts.revision;host.saveShared({expected_revision:sharedValue.revision,integration:{...sharedValue.integration,installer_path:q('installer').value.trim(),tc_root:q('tc-root').value.trim()},timeouts});};
  for(const [id,kind]of [['browse-installer','installer'],['browse-source','source']])q(id).onclick=()=>{browseKind=kind;host.paths(kind,'');};
  function paths(value){browseKind=value.kind;browsePath=value.path||'';q('server-browser').hidden=false;q('server-folder').textContent=browsePath||'서버에서 허용한 루트를 선택하세요.';q('use-folder').hidden=browseKind!=='source'||!browsePath;const entries=value.path?value.entries:value.roots.map(path=>({name:path,path,directory:true}));q('server-entries').replaceChildren(...entries.map(entry=>{const button=element('button',(entry.directory?'폴더 · ':'파일 · ')+entry.name);button.type='button';button.onclick=()=>{if(entry.directory)host.paths(browseKind,entry.path);else if(browseKind==='installer')q('installer').value=entry.path;};return button;}));}
  q('use-folder').onclick=()=>{q('tc-root').value=browsePath;};
  q('load-storage').onclick=()=>host.storage();
  function storage(value){storageValue=clone(value);q('storage-form').hidden=false;q('storage-enabled').checked=value.enabled;q('storage-days').value=value.max_age_seconds/86400;q('storage-limit').value=value.max_bytes/1024**3;q('storage-state').textContent='Windows 적용: '+(value.connector_sync?.state||'확인 전');}
  q('storage-form').onsubmit=event=>{event.preventDefault();if(storageValue)host.saveStorage({expected_revision:storageValue.revision,enabled:q('storage-enabled').checked,max_age_seconds:Math.round(Number(q('storage-days').value)*86400),max_bytes:Math.round(Number(q('storage-limit').value)*1024**3)});};
  q('preview-cleanup').onclick=()=>host.cleanup(true);q('apply-cleanup').onclick=()=>host.cleanup(false);
  function cleanup(value){const rows=[];for(const [name,report]of [['Linux',value],['Windows',value.connector_cleanup?.report||value.connector_cleanup]]){if(!report)continue;rows.push(name+' · '+(report.skipped_reason||report.reason||report.state||((report.dry_run?'정리 예정 ':'정리됨 ')+((report.dry_run?report.planned_bytes:report.deleted_bytes)||0)/1024**2+' MiB'))+(report.over_budget?' · 용량 한도 초과':'')+(report.batch_limited?' · 다음 주기에 계속 정리':'')+(report.measurement_complete===false?' · 일부 집계':''));}q('cleanup-report').textContent=rows.join('\n');}
  return {render,settings,ports,shared,paths,storage,cleanup,message,preview(value){q('preview').hidden=!value;q('scenario-row').hidden=!value;},busy(value,form){pending=value;if(form)for(const input of q(form+'-form').querySelectorAll('input,select,textarea'))input.disabled=value;for(const id of ['load-storage','save-storage','preview-cleanup','apply-cleanup','save-shared','load-shared','refresh-ports','reload','cancel','scenario','browse-installer','browse-source','use-folder'])q(id).disabled=value;for(const button of root.querySelectorAll('[data-pick],#server-entries button'))button.disabled=value;renderControls();},unavailable(text){snapshot={...snapshot,fresh:false,stale:true,boards:(snapshot.boards||[]).map(board=>({...board,stale:true}))};render(snapshot);message(text,true);}};
}
