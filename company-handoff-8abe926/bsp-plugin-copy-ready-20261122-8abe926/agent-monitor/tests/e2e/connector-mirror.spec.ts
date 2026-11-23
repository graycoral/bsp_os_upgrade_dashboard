import {test,expect,type Page} from '../../apps/web/node_modules/@playwright/test';
import {createServer,type Server} from 'node:http';
import {readFileSync} from 'node:fs';
import path from 'node:path';

// Static assets only. Every API operation is intercepted, including unexpected writes.
let server:Server,origin:string;
test.beforeAll(async()=>{
  const dist=path.resolve(process.cwd(),'dist');
  server=createServer((req,res)=>{const file=path.resolve(dist,'.'+(new URL(req.url||'/','http://fixture').pathname==='/'?'/index.html':new URL(req.url||'/','http://fixture').pathname));if(!file.startsWith(dist+path.sep)){res.writeHead(403).end();return}try{res.writeHead(200,{'Content-Type':file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html'});res.end(readFileSync(file))}catch{res.writeHead(404).end()}});
  await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));const address=server.address();if(!address||typeof address==='string')throw Error('No fixture address');origin=`http://127.0.0.1:${address.port}`;
});
test.afterAll(async()=>{if(server)await new Promise<void>((resolve,reject)=>server.close(e=>e?reject(e):resolve()))});
type Data=Record<string,any>;
function snapshot():Data {
  return {schema:'connector-mirror-v1',fresh:true,
    inventory:{runner_id:'a'.repeat(32),fresh:true,boards:[{board_id:'a',name:'Alpha',com:'COM7',host:'WIN',state:'CONNECTED',detected:true,serial_proxy:{state:'READY',owner:null}},{board_id:'b',name:'Beta',com:'COM8',host:'WIN',state:'CONNECTED',detected:true,serial_proxy:{state:'READY',owner:null}}]},
    console:{fresh:true,boards:[{board_id:'a',text:'ALPHA UART evidence',code:'CONSOLE_READY'},{board_id:'b',text:'BETA UART evidence',code:'CONSOLE_READY'}]},
    errors:{events:[{event_id:'event-a',board_id:'a',code:'ALPHA_ERROR',message:'Alpha failure',time:1700000000},{event_id:'event-b',board_id:'b',code:'BETA_ERROR',message:'Beta failure',time:1700000001}]},
    projection:{session_id:'session-1',revision:'profile-1',received_at:1700000000,state:'CONNECTED',profile:{boards:[{board_id:'a',host:'WIN',com:'COM7'},{board_id:'b',host:'WIN',com:'COM8'}],board_names:{a:'Alpha',b:'Beta'},serial_transport:'proxy',serial_settings:{a:{baudrate:115200}},python:'C:/Python/python.exe'},ports:[{com:'COM7'},{com:'COM8'},{com:'COM9'}],executions:[{id:'tc-a',board_ids:['a'],state:'DONE',stdout:'ALPHA TC stdout',stderr:''},{id:'tc-b',board_ids:['b'],state:'DONE',stdout:'BETA TC stdout',stderr:'BETA TC stderr'}]},
    settings:{revision:'shared-1',integration:{installer_path:'/images/install.bat',tc_root:'/tc',global_defaults:['**/*.py']},timeouts:{default_seconds:600,source_revision:'',overrides:{}},connector_application:{runner_id:'a'.repeat(32),state:'UNCONFIGURED',revision:'desired-1',desired_revision:null}},commands:[]};
}
async function fixture(page:Page) {
  const state={value:snapshot(),reads:[] as string[],writes:[] as Data[],unexpected:[] as string[],failure:false,conflict:false,hold:false,held:[] as (()=>void)[]};
  await page.route('**/api/v1/**',async route=>{
    const req=route.request(),url=new URL(req.url()),api=url.pathname.replace('/api/v1','');
    const send=(json:unknown,status=200)=>route.fulfill({json,status});
    if(req.method()==='GET'){
      state.reads.push(api);
      if(api==='/jobs')return send([]);
      if(api==='/config')return send({version:1,profile:null});
      if(api==='/gui-test/live/connector/mirror'){
        if(state.hold)await new Promise<void>(resolve=>state.held.push(resolve));
        return state.failure?send({message:'Fixture transport unavailable'},503):send(state.value);
      }
      if(api==='/gui-test/live/integration/settings')return send(state.value.settings);
      if(api==='/gui-test/live/integration/browser-session')return send({csrf_token:'fixture-csrf'});
    }
    if(req.method()==='POST'&&api==='/gui-test/live/connector/mirror/commands'){
      const body=req.postDataJSON();state.writes.push({api,body});
      const command={...body,command_id:'command-'+state.writes.length,state:'QUEUED'};state.value.commands.push(command);return send(command);
    }
    if(req.method()==='POST'&&api.match(/^\/gui-test\/live\/connector\/mirror\/commands\/[^/]+\/abandon$/)){
      const body=req.postDataJSON();state.writes.push({api,body});const command=state.value.commands.find((item:Data)=>api.includes('/'+item.command_id+'/'));command.state='ABANDONED';return send(command);
    }
    if(req.method()==='PUT'&&api==='/gui-test/live/integration/connector-settings'){
      const body=req.postDataJSON();state.writes.push({api,body});if(state.conflict)return send({message:'Connector desired settings changed'},409);
      state.value.settings.connector_application={...body,state:'PENDING',revision:'desired-2',desired_revision:'requested-windows-settings'};return send(state.value.settings.connector_application);
    }
    if(req.method()==='PUT'&&api==='/gui-test/live/integration/settings'){
      const body=req.postDataJSON();state.writes.push({api,body});state.value.settings={...state.value.settings,...body,revision:'shared-2'};return send(state.value.settings);
    }
    state.unexpected.push(`${req.method()} ${api}`);return send({message:'Unexpected fixture request; no operation performed'},501);
  });
  await page.goto(origin+'/?tab=board-connector&guiExecution=default');
  await expect(page.getByRole('heading',{name:'보드 커넥터',exact:true})).toBeVisible();
  await expect(page.getByText('보드 커넥터 연결됨',{exact:true})).toBeVisible();
  return state;
}
async function refresh(page:Page){const button=page.getByRole('button',{name:'새로 확인',exact:true});await Promise.all([page.waitForResponse(response=>response.url().endsWith('/connector/mirror')),button.click()]);await expect(button).toBeEnabled()}
const logText=(page:Page)=>page.locator('.gt-mirror-log-panel pre');

test('mirror TC list follows selected board and current source without acquiring control',async({page})=>{
  const state=await fixture(page);
  state.value.test_status={source:{location:'/srv/tc'},message:'',stale:false,rows:[
    {id:'tc',path:'Single/uart.py',boards:{a:{state:'RUNNING',label:'진행 중',run_id:'run-a',run_state:'RUNNING',historical:false},b:{state:'PASS',label:'PASS',run_id:'run-b',run_state:'COMPLETED',historical:true}}},
    {id:'pending',path:'Single/audio.py',boards:{a:{state:'PENDING',label:'대기 중',run_id:'run-a',run_state:'RUNNING',historical:false}}}]};
  await refresh(page);
  const list=page.getByRole('region',{name:'테스트 스크립트 상태'});
  await expect(list).toContainText('/srv/tc');await expect(list).toContainText('진행 중');await expect(list).toContainText('대기 중');
  await expect(list.locator('button,input,select,a')).toHaveCount(0);
  await page.getByRole('tab',{name:/Beta COM8/}).click();await expect(list).toContainText('PASS');await expect(list).toContainText('미실행');
  state.value.test_status={source:{location:'/srv/other'},rows:[],message:'선택한 경로에 테스트 스크립트가 없습니다.',stale:false};
  await refresh(page);await expect(list).not.toContainText('Single/uart.py');await expect(list).toContainText('/srv/other');
  expect(state.writes).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('mirror always reads live APIs and separates board console, TC outputs and errors by board tabs',async({page})=>{
  const state=await fixture(page);
  await expect(logText(page)).toContainText('ALPHA UART evidence');await expect(logText(page)).not.toContainText('BETA');
  await page.getByRole('tab',{name:'TC 로그',exact:true}).click();await expect(logText(page)).toContainText('ALPHA TC stdout');
  await page.getByRole('tab',{name:/Beta COM8/}).click();await expect(logText(page)).toContainText('BETA TC stderr');await expect(logText(page)).not.toContainText('ALPHA');
  await page.getByRole('tab',{name:'공통 오류',exact:true}).click();await expect(logText(page)).toContainText('BETA_ERROR');await expect(logText(page)).not.toContainText('ALPHA_ERROR');
  await page.getByRole('tab',{name:/Beta COM8/}).focus();await page.keyboard.press('ArrowUp');await expect(logText(page)).toContainText('ALPHA_ERROR');await expect(page.getByRole('tab',{name:/Alpha COM7/})).toHaveAttribute('aria-selected','true');
  expect(state.reads.some(api=>api==='/gui-test/live/connector/mirror')).toBe(true);expect(state.reads.filter(api=>api.startsWith('/gui-test')&&!api.startsWith('/gui-test/live'))).toEqual([]);
  expect(state.writes).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('Windows command receipt stays queued until actual acknowledgment, with runner/session/revision guards',async({page})=>{
  const state=await fixture(page);await page.getByRole('button',{name:'선택 보드 PuTTY 열기'}).click();
  const commands=page.getByRole('region',{name:'Windows 명령 확인'});
  await expect(commands).toContainText('Windows 전달 대기');await expect(commands).not.toContainText('Windows 확인됨');
  expect(state.writes[0].body).toMatchObject({runner_id:'a'.repeat(32),session_id:'session-1',revision:'profile-1',action:'putty',body:{board_id:'a'}});
  expect(state.writes[0].body.idempotency_key).toMatch(/^[a-f\d-]{36}$/);
  state.value.commands[0].state='FAILED';state.value.commands[0].error='PuTTY executable not found';await refresh(page);
  await expect(commands).toContainText('실패');await expect(commands).toContainText('PuTTY executable not found');expect(state.unexpected).toEqual([]);
});

test('COM draft survives polls, CAS conflict preserves edits, and Windows application is separate from central save',async({page})=>{
  const state=await fixture(page);await page.getByText('보드·COM 설정 편집',{exact:true}).click();
  const port=page.getByLabel('COM 포트',{exact:true}).first();await port.selectOption('COM9');
  state.value.projection.profile.board_names.a='Windows changed name';await refresh(page);await expect(port).toHaveValue('COM9');
  state.value.settings.connector_application.revision='other-editor-revision';await refresh(page);
  state.conflict=true;await page.getByRole('button',{name:'장비 설정 요청 저장'}).click();await expect(page.getByRole('alert')).toContainText('Connector desired settings changed');await expect(port).toHaveValue('COM9');
  expect(state.writes.at(-1)?.body.expected_revision).toBe('desired-1');expect(state.writes.at(-1)?.body.settings.boards[0].com).toBe('COM9');
  await page.getByRole('button',{name:'편집 취소',exact:true}).click();await expect(port).toHaveValue('COM7');await port.selectOption('COM9');state.conflict=false;await page.getByRole('button',{name:'장비 설정 요청 저장'}).click();
  const receipt=page.getByRole('region',{name:'Windows 장비 설정 적용 상태'});await expect(receipt).toContainText('적용 대기');await expect(receipt).toContainText('requested-windows-settings');await expect(port).toHaveValue('COM9');
  expect(state.writes.at(-1)?.body.expected_revision).toBe('other-editor-revision');
  await expect(page.getByRole('tab',{name:/Alpha COM7/})).toBeVisible();
  await page.getByRole('button',{name:'Windows에 설정 적용 요청'}).click();expect(state.writes.at(-1)?.body).toMatchObject({action:'apply-settings',body:{desired_revision:'requested-windows-settings'}});
  state.value.settings.connector_application={...state.value.settings.connector_application,state:'APPLIED',applied_revision:'actual-windows-profile',received_at:1700000002};state.value.commands.at(-1).state='APPLIED';await refresh(page);
  await expect(receipt).toContainText('actual-windows-profile');await expect(receipt).toContainText('Windows 확인됨');expect(state.unexpected).toEqual([]);
});

test('common settings use existing central CAS API with timeout and source values preserved',async({page})=>{
  const state=await fixture(page);await page.getByText('플러그인 공통 설정 · 이미지 설치와 TC 실행',{exact:true}).click();
  await page.getByLabel('공통 TC 제한시간 (초)',{exact:true}).fill('720');await page.getByRole('button',{name:'공통 설정 저장',exact:true}).click();
  await expect(page.getByText('공통 설정을 저장했습니다. 새 실행부터 적용됩니다.',{exact:true})).toBeVisible();
  expect(state.writes.at(-1)).toMatchObject({api:'/gui-test/live/integration/settings',body:{expected_revision:'shared-1',timeouts:{default_seconds:720,source_revision:'',overrides:{}}}});expect(state.unexpected).toEqual([]);
});

test('board count preserves removed board metadata and rejects duplicate COM assignments',async({page})=>{
  const state=await fixture(page);await page.getByText('보드·COM 설정 편집',{exact:true}).click();
  await page.getByLabel('연결할 보드 수',{exact:true}).fill('1');await page.getByRole('button',{name:'장비 설정 요청 저장'}).click();
  await expect.poll(()=>state.writes.length).toBe(1);
  expect(state.writes.at(-1)?.body.settings.boards).toHaveLength(1);expect(state.writes.at(-1)?.body.settings.connector_inactive_boards[0]).toMatchObject({board:{board_id:'b',com:'COM8'},name:'Beta'});
  await page.getByLabel('연결할 보드 수',{exact:true}).fill('2');await expect(page.getByLabel('COM 포트',{exact:true}).nth(1)).toHaveValue('COM8');
  await page.getByLabel('COM 포트',{exact:true}).nth(1).selectOption('COM7');await expect(page.getByRole('button',{name:'장비 설정 요청 저장'})).toBeDisabled();
  expect(state.unexpected).toEqual([]);
});

test('board edits preserve pending flashing settings without overwriting projected observer secrets',async({page})=>{
  const state=await fixture(page);state.value.settings.connector_application={runner_id:'a'.repeat(32),state:'PENDING',revision:'pending-flash-1',desired_revision:'flash-pending',settings:{flashing:{profiles:{company:{installer_path:'flash.bat'}}}}};state.value.projection.profile.console_observers={a:{port:'COM17',rx_only_confirmed:true,control_lines_isolated:true}};await refresh(page);
  await page.getByText('보드·COM 설정 편집',{exact:true}).click();await page.getByLabel('COM 포트',{exact:true}).first().selectOption('COM9');await page.getByRole('button',{name:'장비 설정 요청 저장'}).click();
  await expect.poll(()=>state.writes.length).toBe(1);
  expect(state.writes.at(-1)?.body.expected_profile_revision).toBe('profile-1');expect(state.writes.at(-1)?.body.settings.flashing).toEqual({profiles:{company:{installer_path:'flash.bat'}}});expect(state.writes.at(-1)?.body.settings.console_observers).toBeUndefined();expect(state.writes.at(-1)?.body.settings.python).toBeUndefined();
  expect(state.unexpected).toEqual([]);
});

test('Windows profile revision change preserves draft and requires reload before save',async({page})=>{
  const state=await fixture(page);await page.getByText('보드·COM 설정 편집',{exact:true}).click();await page.getByLabel('COM 포트',{exact:true}).first().selectOption('COM9');state.value.projection.revision='profile-from-local-Windows-edit';await refresh(page);
  await expect(page.getByText('편집 중 Windows 설정이 변경되었습니다. 현재 초안을 확인한 뒤 편집을 취소해 최신 설정을 불러오세요.',{exact:true})).toBeVisible();await expect(page.getByLabel('COM 포트',{exact:true}).first()).toHaveValue('COM9');await expect(page.getByRole('button',{name:'장비 설정 요청 저장'})).toBeDisabled();
  expect(state.writes).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('command list keeps newest command after thirteen requests and displays Windows failure result',async({page})=>{
  const state=await fixture(page);state.value.commands=Array.from({length:13},(_,index)=>({command_id:'command-'+(13-index),action:'putty',state:index===0?'FAILED':'APPLIED',result:index===0?{code:'PUTTY_NOT_FOUND',message:'Windows could not open PuTTY'}:{}}));await refresh(page);
  const commands=page.getByRole('region',{name:'Windows 명령 확인'});await expect(commands).toContainText('command-13');await expect(commands).toContainText('PUTTY_NOT_FOUND · Windows could not open PuTTY');await expect(commands).not.toContainText(/^command-1$/);
  expect(await commands.locator('li').count()).toBe(12);expect(state.unexpected).toEqual([]);
});

test('UNKNOWN recovery requires replacement Manager and preserves acknowledgment without replaying command',async({page})=>{
  const state=await fixture(page);state.value.commands=[{command_id:'unknown-command',session_id:'session-1',action:'putty',state:'UNKNOWN',updated_at:1700000009}];await refresh(page);
  await expect(page.getByText('보드 커넥터를 종료 후 다시 실행하고 보드·PuTTY 상태를 확인하세요.',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'이전 요청 결과 불명 확인'})).toHaveCount(0);await expect(page.getByRole('button',{name:'선택 보드 PuTTY 열기'})).toBeDisabled();
  state.value.projection.session_id='replacement-session';await refresh(page);await page.getByRole('button',{name:'이전 요청 결과 불명 확인'}).click();
  await expect(page.getByRole('region',{name:'Windows 명령 확인'})).toContainText('결과 불명 확인 완료');expect(state.writes).toHaveLength(1);expect(state.writes[0]).toMatchObject({api:'/gui-test/live/connector/mirror/commands/unknown-command/abandon',body:{runner_id:'a'.repeat(32),session_id:'replacement-session',expected_updated_at:1700000009}});expect(state.unexpected).toEqual([]);
});

test('truncated TC tails are marked and actual server and Windows paths remain read-only',async({page})=>{
  const state=await fixture(page);state.value.projection.logs_truncated=true;state.value.projection.server_paths={selected_tc_source:'/srv/current/tc',run:{id:'previous-run',state:'COMPLETED',historical:true,installer:'/srv/images/old.bat',tc_source:'/srv/pinned/tc'}};state.value.projection.execution_paths=[{id:'actual-execution',working_directory:'C:/runtime/snapshot'}];await refresh(page);
  await page.getByRole('tab',{name:'TC 로그',exact:true}).click();await expect(page.getByText('TC 로그는 Windows가 보고한 마지막 일부만 표시합니다.',{exact:true})).toBeVisible();await page.getByText('소스·실행 경로',{exact:true}).click();await expect(page.getByText('/srv/current/tc',{exact:true})).toBeVisible();await expect(page.getByText('C:/runtime/snapshot',{exact:true})).toBeVisible();await expect(page.getByText('previous-run · COMPLETED · 이전 실행',{exact:true})).toBeVisible();expect(state.writes).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('hidden mirror stops polling and retains the local board draft on return',async({page})=>{
  await page.clock.install();const state=await fixture(page);await page.getByText('보드·COM 설정 편집',{exact:true}).click();await page.getByLabel('COM 포트',{exact:true}).first().selectOption('COM9');
  await page.getByRole('navigation').getByRole('link',{name:'대시보드',exact:true}).click();const before=state.reads.filter(api=>api==='/gui-test/live/connector/mirror').length;await page.clock.runFor(5000);expect(state.reads.filter(api=>api==='/gui-test/live/connector/mirror')).toHaveLength(before);
  await page.getByRole('navigation').getByRole('link',{name:'보드 커넥터',exact:true}).click();await expect(page.getByText('보드 커넥터 연결됨',{exact:true})).toBeVisible();await expect(page.getByLabel('COM 포트',{exact:true}).first()).toHaveValue('COM9');expect(state.writes).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('offline projection keeps historical logs and application receipts while blocking Windows commands',async({page})=>{
  const state=await fixture(page);state.value.settings.connector_application={state:'APPLIED',desired_revision:'desired-old',applied_revision:'applied-old',received_at:1700000002};state.value.fresh=false;state.value.inventory.fresh=false;state.value.console.fresh=false;await refresh(page);
  await expect(page.getByText('Windows 연결 확인 필요 · 오래된 정보',{exact:true})).toBeVisible();await expect(logText(page)).toContainText('ALPHA UART evidence');await expect(page.getByRole('button',{name:'선택 보드 PuTTY 열기'})).toBeDisabled();
  await expect(page.getByText('위 적용 확인은 마지막 수신 기록입니다. 현재 Windows 연결은 다시 확인해야 합니다.',{exact:true})).toBeVisible();
  expect(state.writes).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('failed refresh retains last evidence and does not keep a formerly fresh command enabled',async({page})=>{
  const state=await fixture(page);state.failure=true;await refresh(page);
  await expect(page.getByRole('alert')).toContainText('Fixture transport unavailable');await expect(page.getByRole('button',{name:'선택 보드 PuTTY 열기'})).toBeDisabled();await expect(logText(page)).toContainText('ALPHA UART evidence');expect(state.writes).toEqual([]);
});

test('hung refresh expires local freshness before another Windows command can be sent',async({page})=>{
  await page.clock.install();const state=await fixture(page);state.hold=true;
  await page.clock.runFor(17000);
  await expect(page.getByRole('button',{name:'선택 보드 PuTTY 열기'})).toBeDisabled();await expect(logText(page)).toContainText('ALPHA UART evidence');
  state.hold=false;for(const release of state.held)release();expect(state.writes).toEqual([]);
});

test('legacy native mirror requests automatic sharing without RX controls or premature application claims',async({page})=>{
  const state=await fixture(page);const inactive={board:{board_id:'c',host:'WIN',com:'COM29'},name:'Saved board',baudrate:9600,observer:{port:'COM29',rx_only_confirmed:false},company:{keep:true}};
  state.value.projection.profile.serial_transport='native';for(const board of state.value.inventory.boards)delete board.serial_proxy;state.value.projection.profile.console_observers={a:{port:'COM7',rx_only_confirmed:false,control_lines_isolated:true}};state.value.projection.profile.connector_inactive_boards=[inactive];await refresh(page);
  await page.getByText('보드·COM 설정 편집',{exact:true}).click();
  await expect(page.getByRole('button',{name:'선택 보드 PuTTY 열기'})).toBeDisabled();await expect(page.getByLabel('시리얼 연결 방식',{exact:true})).toHaveCount(0);await expect(page.getByLabel(/RX/)).toHaveCount(0);await expect(page.getByText('다음 연결 시 자동 적용',{exact:true})).toBeVisible();
  await page.getByLabel('COM 포트',{exact:true}).first().selectOption('COM9');await page.getByRole('button',{name:'장비 설정 요청 저장'}).click();
  await expect.poll(()=>state.writes.length).toBe(1);
  expect(state.writes[0].body.settings.serial_transport).toBe('proxy');expect(state.writes[0].body.settings.console_observers).toBeUndefined();expect(state.writes[0].body.settings.connector_inactive_boards).toEqual([inactive]);
  await expect(page.getByText('다음 연결 시 자동 적용',{exact:true})).toBeVisible();await expect(page.getByRole('region',{name:'Windows 장비 설정 적용 상태'})).toContainText('적용 대기');
  state.value.projection.profile.serial_transport='proxy';for(const board of state.value.inventory.boards)board.serial_proxy={state:'READY',owner:null};await refresh(page);
  await expect(page.getByText('다음 연결 시 자동 적용',{exact:true})).toHaveCount(0);expect(state.unexpected).toEqual([]);
});
