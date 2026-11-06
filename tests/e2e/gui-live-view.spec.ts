import {test, expect} from '../../apps/web/node_modules/@playwright/test';
import {selectTestSetting} from './settings-controls';

const base='/api/v1/gui-test';
const standalone=process.env.GUI_TEST_STANDALONE==='1';

async function openWorkspace(page:any){
 await page.goto('/');
 await showWorkspace(page);
}

async function showWorkspace(page:any){
 if(!standalone)await page.getByRole('navigation').getByRole('link',{name:'Test 현황',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Test 현황',exact:true})).toBeVisible();
}

async function applyView(page:any,mode:'default'|'live'){
 if(standalone)await page.getByRole('button',{name:'연결 및 실행 설정',exact:true}).click();
 else await page.getByRole('navigation').getByRole('link',{name:'환경 설정',exact:true}).click();
 await selectTestSetting(page,'view');
 const setting=page.getByRole('region',{name:'Test 현황 보기 모드',exact:true});
 const select=setting.getByRole('combobox',{name:'Test 현황 보기 모드',exact:true});
 const apply=setting.getByRole('button',{name:'보기 모드 적용',exact:true});
 await expect(apply).toBeDisabled();
 const previousUrl=page.url();await select.selectOption(mode);await expect(apply).toBeEnabled();expect(page.url()).toBe(previousUrl);
 await apply.click();await expect(page).toHaveURL(new RegExp('guiExecution='+mode));
 if(!standalone){
  expect(new URL(page.url()).searchParams.get('tab')).toBe('settings');
  await expect(page.getByRole('navigation').getByRole('link',{name:'환경 설정',exact:true})).toHaveAttribute('aria-current','page');
  await selectTestSetting(page,'view');
  await expect(page.getByRole('combobox',{name:'Test 현황 보기 모드',exact:true})).toHaveValue(mode);
 }
 expect(await page.evaluate(()=>localStorage.getItem('gui-execution-view'))).toBe(mode);
 await showWorkspace(page);
}

test('live view stays selected on reload and never displays Mock TC, boards, or Run history',async({page})=>{
 await openWorkspace(page);
 await expect(page.getByText('MOCK DEMO',{exact:true})).toBeVisible();
 const catalog=await (await page.request.get(base+'/catalog')).json();
 const boards=await (await page.request.get(base+'/boards')).json();
 expect(catalog.tests.length).toBeGreaterThan(0);
 expect(boards.boards.length).toBeGreaterThan(0);
 const previousRuns=await (await page.request.get(base+'/runs')).json();
 const runResponse=await page.request.post(base+'/runs',{
  headers:{'X-BSP-Client':'dashboard','X-GUI-Session':'browser-live-fixture','Idempotency-Key':'browser-live-fixture-'+Date.now()},
  data:{tc_ids:[catalog.tests[0].id],source_revision:catalog.revision,
   connection:{a:boards.boards[0]},execution:'mock',speed:0.2}
 });
 expect(runResponse.status()).toBe(202);
 const mockRun=await runResponse.json();
 for(let attempt=0;attempt<20;attempt++){
  const snapshot=await (await page.request.get(base+'/runs/'+mockRun.id)).json();
  if(['COMPLETED','CANCELLED'].includes(snapshot.state))break;
  if(attempt===0||snapshot.state==='RUNNING'||snapshot.state==='QUEUED'){
   const response=await page.request.post(base+'/runs/'+mockRun.id+'/actions/cancel',{
    headers:{'X-BSP-Client':'dashboard','X-GUI-Session':'browser-live-fixture','Idempotency-Key':'browser-cancel-'+Date.now()+'-'+attempt},
    data:{expected_version:snapshot.version,data:{}}
   });
   expect([200,409]).toContain(response.status());
  }
  await page.waitForTimeout(250);
 }
 expect(['COMPLETED','CANCELLED']).toContain((await (await page.request.get(base+'/runs/'+mockRun.id)).json()).state);
 await page.evaluate((id:string)=>localStorage.setItem('gui-last-run',id),mockRun.id);
 await page.reload();
 await showWorkspace(page);
 await expect(page.getByLabel('Run 이력').locator('option')).toHaveCount(previousRuns.length+2);
 await expect(page.getByLabel('Run 이력').locator(`option[value="${mockRun.id}"]`)).toHaveCount(1);
 await expect(page.getByTestId('run-state')).toBeVisible();
 await expect(page.getByRole('button',{name:'실제 연결 모드로 전환'})).toHaveCount(0);
 await expect(page.getByLabel('실행기 연결 상태')).toHaveCount(0);
 await applyView(page,'live');
 await expect(page).toHaveURL(/guiExecution=live/);
 await expect(page.getByRole('heading',{name:'Test 현황',exact:true})).toBeVisible();
 const connection=page.getByLabel('실행기 연결 상태',{exact:true});
 await expect(connection).toContainText('미설정');await expect(connection).not.toHaveAttribute('open','');
 await expect(connection.getByRole('button',{name:'연결 다시 확인',exact:true})).toBeHidden();
 await connection.locator(':scope>summary').press('Enter');
 await expect(connection.getByRole('button',{name:'연결 다시 확인',exact:true})).toBeVisible();
 await connection.locator(':scope>summary').press('Space');await expect(connection).not.toHaveAttribute('open','');
 await expect(page.getByText('MOCK DEMO',{exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Run 이력').locator('option')).toHaveCount(1);
 await expect(page.getByTestId('run-state')).toHaveCount(0);
 // The retained compact editor has an explicit empty-choice placeholder when
 // live has no registered boards. Hidden editors must still contain no Mock data.
 for(const role of ['A','B']){
  const board=page.locator(`select[aria-label="Board ${role}"]`);
  await expect(board).toBeHidden();await expect(board).toHaveValue('');
  expect(await board.locator('option').evaluateAll(items=>items.map(item=>({
   value:(item as HTMLOptionElement).value,text:item.textContent
  })))).toEqual([{value:'',text:'등록 보드 없음'}]);
 }
 await expect(page.getByRole('button',{name:'Preflight 검사'})).toBeDisabled();
 await expect(page.getByRole('button',{name:'테스트 시작',exact:true})).toBeDisabled();
 await page.screenshot({path:'../../.local-reports/live-view.png',fullPage:true});
 const capability=await (await page.request.get(base+'/live/capabilities')).json();
 expect(capability.simulation).toBe(false);
 expect(capability.connection).toMatchObject({state:'unconfigured',ready:false});
 expect((await (await page.request.get(base+'/live/catalog')).json()).tests).toEqual([]);
 expect((await (await page.request.get(base+'/live/boards')).json()).boards).toEqual([]);
 expect(await (await page.request.get(base+'/live/runs')).json()).toEqual([]);
 const blocked=await page.request.post(base+'/live/runs',{
  headers:{'X-BSP-Client':'dashboard','X-GUI-Session':'browser-live-fixture','Idempotency-Key':'forged-live-'+Date.now()},
  data:{tc_ids:[catalog.tests[0].id],source_revision:catalog.revision,
   connection:{a:boards.boards[0]},execution:'hardware'}
 });
 expect(blocked.status()).toBe(503);
 expect((await blocked.json()).code).toBe('RUNNER_UNAVAILABLE');

 await page.reload();
 await expect(page.getByRole('heading',{name:'Test 현황',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'기존 모드 보기'})).toHaveCount(0);
 await expect(connection).not.toHaveAttribute('open','');
 await expect(page.getByLabel('Run 이력').locator('option')).toHaveCount(1);
 await applyView(page,'default');
 await expect(page).toHaveURL(/guiExecution=default/);
 await expect(page.getByRole('heading',{name:'Test 현황',exact:true})).toBeVisible();
 await expect(page.getByText('MOCK DEMO',{exact:true})).toBeVisible();
 await expect(page.getByLabel('Run 이력').locator('option')).toHaveCount(previousRuns.length+2);
 await expect(page.getByLabel('Run 이력').locator(`option[value="${mockRun.id}"]`)).toHaveCount(1);
 await expect(page.getByTestId('run-state')).toBeVisible();
});
