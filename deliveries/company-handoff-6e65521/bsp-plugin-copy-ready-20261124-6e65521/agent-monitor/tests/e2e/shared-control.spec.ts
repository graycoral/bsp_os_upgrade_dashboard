import {test,expect} from '../../apps/web/node_modules/@playwright/test';

const base='/api/v1/gui-test/live';
const fixture=()=>({revision:'a'.repeat(64),integration:{installer_roots:['/srv/images'],source_roots:['/srv/tc'],installer_path:'/srv/images/install.bat',tc_root:'/srv/tc',global_defaults:['**/*.py'],flash_profile:'fixture'},timeouts:{revision:'timeouts-fixture',default_seconds:null,source_revision:'',overrides:{}},connector_application:{state:'PENDING'}});

async function setup(page:any){
 let current=fixture();const writes:any[]=[];let conflict=false;
 await page.route('**'+base+'/integration/settings',async(route:any)=>{
  if(route.request().method()==='PUT'){
   const body=route.request().postDataJSON();writes.push(body);
   if(conflict){await route.fulfill({status:409,json:{code:'SETTINGS_CHANGED',message:'다른 클라이언트가 설정을 변경했습니다.'}});return;}
   current={...current,...body,revision:'b'.repeat(64)};
  }
  await route.fulfill({json:current});
 });
 await page.goto('/?tab=gui-test&guiExecution=live');
 const panel=page.locator('.gt-shared-control');
 await page.getByText('플러그인 공통 설정 · 이미지 설치와 TC 실행',{exact:true}).click({timeout:15000});
 await expect(panel).toBeVisible();
 const load=panel.getByRole('button',{name:'불러오기',exact:true});if(await load.isVisible())await load.click();
 await expect(panel.getByLabel('Linux 설치 BAT')).toHaveValue('/srv/images/install.bat');
 return {panel,writes,conflict:()=>{conflict=true;current={...current,revision:'c'.repeat(64),integration:{...current.integration,flash_profile:'remote-update'}}}};
}

test('shared settings save carries one revision and conflict keeps unsaved edits',async({page})=>{
 const {panel,writes,conflict}=await setup(page);
 await panel.getByLabel('플래싱 프로파일',{exact:true}).fill('edited-profile');
 await panel.getByLabel('공통 TC 제한시간 (초)',{exact:true}).fill('75');
 await panel.getByRole('button',{name:'공통 설정 저장',exact:true}).click();
 await expect(panel.getByRole('status')).toContainText('공통 설정을 저장했습니다.');
 expect(writes[0]).toMatchObject({expected_revision:'a'.repeat(64),integration:{flash_profile:'edited-profile'},timeouts:{default_seconds:75}});
 expect(writes[0].timeouts).not.toHaveProperty('revision');
 conflict();
 await panel.getByLabel('플래싱 프로파일',{exact:true}).fill('local-unsaved');
 await panel.getByRole('button',{name:'공통 설정 저장',exact:true}).click();
 await expect(panel.getByRole('alert')).toContainText('다른 클라이언트');
 await page.waitForResponse((response:any)=>response.url().endsWith(base+'/integration/settings')&&response.request().method()==='GET');
 await expect(panel.getByLabel('플래싱 프로파일',{exact:true})).toHaveValue('local-unsaved');
 await expect(panel.getByRole('button',{name:'공통 설정 저장',exact:true})).toBeEnabled();
 await panel.getByRole('button',{name:'다시 불러오기',exact:true}).click();
 await expect(panel.getByLabel('플래싱 프로파일',{exact:true})).toHaveValue('remote-update');
 await expect(panel.getByRole('button',{name:'공통 설정 저장',exact:true})).toBeDisabled();
});

test('shared settings browser selects Linux root and BAT without local filesystem access',async({page})=>{
 const visited:string[]=[];
 await page.route('**'+base+'/integration/paths?**',async(route:any)=>{
  const url=new URL(route.request().url());visited.push(url.searchParams.get('path')||'');
  await route.fulfill({json:{roots:['/srv/images'],path:url.searchParams.get('path')||'',entries:[{name:'picked.bat',path:'/srv/images/picked.bat',directory:false}]}});
 });
 const {panel,writes}=await setup(page);
 await panel.getByLabel('Linux 설치 BAT').locator('..').getByRole('button',{name:'서버에서 선택'}).click();
 const dialog=page.getByRole('dialog',{name:'Linux 서버 경로 선택',exact:true});
 await dialog.getByRole('button',{name:'▸ /srv/images',exact:true}).click();
 await dialog.getByRole('button',{name:'picked.bat',exact:true}).click();
 await expect(dialog).toHaveCount(0);
 await expect(panel.getByLabel('Linux 설치 BAT')).toHaveValue('/srv/images/picked.bat');
 expect(visited).toEqual(['','/srv/images']);expect(writes).toEqual([]);
});

test('inactive host navigation preserves shared settings unsaved draft',async({page})=>{
 const {panel}=await setup(page);
 await panel.getByLabel('플래싱 프로파일',{exact:true}).fill('draft-kept-through-navigation');
 await page.getByRole('navigation').getByRole('link',{name:'대시보드',exact:true}).click();
 await page.getByRole('navigation').getByRole('link',{name:'Test 현황',exact:true}).click();
 await expect(panel.getByLabel('플래싱 프로파일',{exact:true})).toHaveValue('draft-kept-through-navigation');
 await expect(panel.getByRole('button',{name:'공통 설정 저장',exact:true})).toBeEnabled();
});

test('first failure analysis is visible and ordinary resume remains blocked',async({page})=>{
 const run={id:'analysis-fixture',version:7,state:'PAUSED',overall_result:'FAIL',controller:'bsp-upgrade',
  tests:[],results:{},attempts:[],progress:{percent:33,done:1,total:3,counts:{FAIL:1,PENDING:2}},
  environment_ready:true,simulation:false,source_revision:'fixture',connection_snapshot:{a:{board_id:'board-a',host:'fixture',com:'COM7'}},
  integration:{phase:'TC',logical_results:{}},execution_policy:'fail-stop-analysis-v1',
  failure_analysis:{status:'PENDING',latched:true,reason:'첫 TC 실패 후 후속 TC 배정 중단',cause_key:'uart-response'},retry_chain:{automatic_retries:0},
  sync:{status:'PENDING',reason:''},started_at:'2026-11-14T00:00:00Z'};
 await page.addInitScript(()=>localStorage.setItem('gui-last-run:live','analysis-fixture'));
 await page.route('**'+base+'/runs',async(route:any)=>route.fulfill({json:[run]}));
 await page.route('**'+base+'/runs/analysis-fixture',async(route:any)=>route.fulfill({json:run}));
 await page.route('**'+base+'/runs/analysis-fixture/events',async(route:any)=>route.fulfill({json:[]}));
 await page.goto('/?tab=gui-test&guiExecution=live');
 const analysis=page.getByRole('region',{name:'플러그인 분석 상태',exact:true});
 await expect(analysis).toContainText('분석 대기');
 await expect(analysis).toContainText('첫 TC 실패 후 후속 TC 배정 중단');
 await expect(analysis).toContainText('자동 재실행 0/3');
 await expect(analysis.getByRole('button',{name:'재개',exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:'테스트 시작',exact:true})).toBeDisabled();
});

test('TC server browser selects a folder and never assigns a Python file as installer',async({page})=>{
 await page.route('**'+base+'/integration/paths?**',async(route:any)=>{
  const url=new URL(route.request().url());
  await route.fulfill({json:{roots:['/srv/tc'],path:url.searchParams.get('path')||'',entries:[{name:'case.py',path:'/srv/tc/case.py',directory:false}]}});
 });
 const {panel}=await setup(page);
 await panel.getByLabel('Linux TC 폴더').locator('..').getByRole('button',{name:'서버에서 선택'}).click();
 const dialog=page.getByRole('dialog',{name:'Linux 서버 경로 선택',exact:true});
 await dialog.getByRole('button',{name:'▸ /srv/tc',exact:true}).click();
 const file=dialog.getByRole('button',{name:'case.py',exact:true});
 if(await file.count())await expect(file).toBeDisabled();
 await dialog.getByRole('button',{name:'이 폴더 선택',exact:true}).click();
 await expect(panel.getByLabel('Linux TC 폴더')).toHaveValue('/srv/tc');
 await expect(panel.getByLabel('Linux 설치 BAT')).toHaveValue('/srv/images/install.bat');
});

test('storage policy uses CAS, preserves conflicts and reports protected cache on both hosts',async({page})=>{
 const policy={revision:'a'.repeat(64),enabled:true,max_age_seconds:604800,max_bytes:20*1024**3,connector_sync:{state:'APPLIED'}};
 let conflict=false;const writes:any[]=[];const cleans:any[]=[];
 await page.route('**'+base+'/integration/storage-policy',async route=>{
  if(route.request().method()==='PUT'){const body=route.request().postDataJSON();writes.push(body);
   if(conflict){await route.fulfill({status:409,json:{message:'Storage policy changed'}});return;}
   await route.fulfill({json:{...policy,...body,revision:'b'.repeat(64),connector_sync:{state:'SYNC_PENDING'}}});return;
  }await route.fulfill({json:policy});
 });
 await page.route('**'+base+'/integration/storage-cleanup',async route=>{const body=route.request().postDataJSON();cleans.push(body);await route.fulfill({json:{dry_run:body.dry_run,planned_bytes:1048576,deleted_bytes:1048576,over_budget:true,connector_cleanup:body.dry_run?{state:'UNAVAILABLE',reason:'CONNECTOR_UNAVAILABLE'}:{state:'CHECKED',report:{dry_run:false,deleted_bytes:2097152,over_budget:true,batch_limited:true}}}});});
 const {panel}=await setup(page);await panel.getByText('저장 공간 자동 정리',{exact:true}).click();
 const storage=panel.locator('.gt-storage-control');await storage.getByRole('button',{name:'정리 기준 불러오기'}).click();
 await storage.getByLabel('보관 기간 (일)').fill('14');await storage.getByRole('button',{name:'정리 기준 저장'}).click();
 await expect.poll(()=>writes[0]).toMatchObject({expected_revision:policy.revision,max_age_seconds:1209600});
 await expect(storage).toContainText('SYNC_PENDING');conflict=true;
 await storage.getByLabel('캐시 한도 (GiB)').fill('12');await storage.getByRole('button',{name:'정리 기준 저장'}).click();
 await expect(storage.getByRole('alert')).toContainText('Storage policy changed');await expect(storage.getByLabel('캐시 한도 (GiB)')).toHaveValue('12');
 await storage.getByRole('button',{name:'정리 대상 확인'}).click();await expect.poll(()=>cleans).toEqual([{dry_run:true}]);
 await expect(storage.getByRole('status')).toContainText('용량 한도 초과');
 await expect(storage.getByRole('status')).toContainText('CONNECTOR_UNAVAILABLE');
 await storage.getByRole('button',{name:'지금 정리'}).click();await expect.poll(()=>cleans[1]).toEqual({dry_run:false});
 await expect(storage.getByRole('status')).toContainText('Windows: 정리됨 2.0 MiB · 용량 한도 초과 · 다음 주기에 계속 정리');
});
