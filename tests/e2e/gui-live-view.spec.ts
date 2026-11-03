import {test, expect} from '../../apps/web/node_modules/@playwright/test';

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

 await page.getByRole('button',{name:'실제 연결 모드로 전환'}).click();
 await expect(page).toHaveURL(/guiExecution=live/);
 await expect(page.getByRole('heading',{name:'Test 현황',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'기존 모드 보기'})).toHaveAttribute('aria-pressed','true');
 await expect(page.getByLabel('실행기 연결 상태')).toContainText('미설정');
 await expect(page.getByText('MOCK DEMO',{exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Run 이력').locator('option')).toHaveCount(1);
 await expect(page.getByTestId('run-state')).toHaveCount(0);
 await expect(page.locator('select[aria-label="Board A"] option')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Preflight 검사'})).toBeDisabled();
 await expect(page.getByRole('button',{name:'▶ 테스트 시작'})).toBeDisabled();
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
 await expect(page.getByRole('button',{name:'기존 모드 보기'})).toBeVisible();
 await expect(page.getByLabel('Run 이력').locator('option')).toHaveCount(1);
 await page.getByRole('button',{name:'기존 모드 보기'}).click();
 await expect(page).toHaveURL(/guiExecution=default/);
 await expect(page.getByRole('heading',{name:'Test 현황',exact:true})).toBeVisible();
 await expect(page.getByText('MOCK DEMO',{exact:true})).toBeVisible();
 await expect(page.getByLabel('Run 이력').locator('option')).toHaveCount(previousRuns.length+2);
 await expect(page.getByLabel('Run 이력').locator(`option[value="${mockRun.id}"]`)).toHaveCount(1);
 await expect(page.getByTestId('run-state')).toBeVisible();
});
