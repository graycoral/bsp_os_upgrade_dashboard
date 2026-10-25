import {test,expect} from '../../apps/web/node_modules/@playwright/test';
import {readFileSync} from 'node:fs';
const standalone=process.env.GUI_TEST_STANDALONE==='1';
async function openTest(page:any){
 await page.goto('/');
 if(!standalone)await page.getByRole('navigation').getByRole('button',{name:'Test 현황',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Test 현황',exact:true})).toBeVisible();
 await expect(page.getByLabel('선택 04_pair')).toBeChecked();
}
async function launch(page:any,scenario='pass',speed='5'){
 await page.getByLabel('데모 시나리오',{exact:true}).selectOption(scenario);
 await page.getByLabel('데모 속도',{exact:true}).selectOption(speed);
 await page.getByRole('button',{name:'Preflight 검사',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('Preflight 통과');
 await page.getByRole('button',{name:'▶ 테스트 시작',exact:true}).click();
}

test('GUI-UI-01 TC filters, suites, profiles, Single/Dual, report downloads',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await openTest(page);
 await page.getByLabel('TC 검색').fill('pair');
 await expect(page.getByLabel('선택 04_pair')).toBeChecked();
 await page.getByLabel('TC 검색').fill('');
 await expect(page.getByLabel('선택 01_boot')).toBeChecked();
 await page.getByLabel('Suite 이름').fill('Browser suite');
 await page.getByRole('button',{name:'Suite 저장 / 수정',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('Suite를 저장');
 await page.getByRole('button',{name:'프로파일 저장',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('연결 프로파일 저장');
 await launch(page);
 await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · PASS',{timeout:20000});
 await page.getByRole('tab',{name:'결과 리포트',exact:true}).click();
 const waiting=page.waitForEvent('download');await page.getByRole('link',{name:'JSON 다운로드',exact:true}).click();
 const download=await waiting;const report=JSON.parse(readFileSync((await download.path())!,'utf8'));
 expect(report.overall_result).toBe('PASS');expect(report.attempts).toHaveLength(5);
 const pair=report.attempts.find((a:any)=>a.tc_id.includes('dual'));
 expect(pair.resolved_command_argv.slice(-2)).toEqual(['COM3','COM4']);
 await page.screenshot({path:'../../.local-reports/gui-test/'+(standalone?'standalone':'dashboard')+'-desktop.png',fullPage:true});
 await page.setViewportSize({width:680,height:1000});
 await page.screenshot({path:'../../.local-reports/gui-test/'+(standalone?'standalone':'dashboard')+'-narrow.png',fullPage:true});
 expect(errors).toEqual([]);
});

test('GUI-UI-02 disconnect, reload, explicit recovery and new attempt',async({page})=>{
 await openTest(page);await launch(page,'disconnect');
 await expect(page.getByTestId('run-state')).toContainText('PAUSED',{timeout:20000});
 await page.reload();if(!standalone)await page.getByRole('navigation').getByRole('button',{name:'Test 현황',exact:true}).click();
 await expect(page.getByTestId('run-state')).toContainText('PAUSED');
 await expect(page.getByRole('button',{name:'▶ 재개',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'데모 연결 / 종료 확인',exact:true}).click();
 await page.getByRole('button',{name:'▶ 재개',exact:true}).click();
 await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · PASS',{timeout:20000});
 await expect(page.locator('.gt-logs')).toContainText('Attempt 2');
});

test('GUI-UI-03 pause/cancel and observer control transfer',async({page,context})=>{
 await openTest(page);await launch(page,'pass','0.2');
 await expect(page.getByTestId('run-state')).toContainText('RUNNING');
 const observer=await context.newPage();await openTest(observer);
 await expect(observer.getByText('관찰 모드',{exact:false})).toBeVisible();
 await observer.getByRole('button',{name:'제어권 요청',exact:true}).click();
 await expect(page.getByRole('button',{name:'제어권 이전 승인',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'제어권 이전 승인',exact:true}).click();
 await expect(observer.getByRole('button',{name:'Ⅱ 일시 정지',exact:true})).toBeEnabled();
 await observer.getByRole('button',{name:'Ⅱ 일시 정지',exact:true}).click();
 await expect(observer.getByTestId('run-state')).toContainText('PAUSED',{timeout:20000});
 await observer.getByRole('button',{name:'■ 테스트 중단',exact:true}).click();
 await expect(observer.getByTestId('run-state')).toHaveText('CANCELLED · INCOMPLETE');
 await observer.close();
});

test('GUI-UI-04 FAIL continues and isolated Dashboard synchronization',async({page})=>{
 await openTest(page);
 if(!standalone){await page.getByRole('button',{name:'격리 데모 Job 준비',exact:true}).click();await expect(page.getByLabel('GUI Test Job')).not.toHaveValue('');}
 await launch(page,'fail');
 await expect(page.getByTestId('run-state')).toHaveText('COMPLETED · FAIL',{timeout:20000});
 await expect(page.getByLabel('TC 판정 진행률')).toHaveAttribute('value','5');
 if(!standalone){await page.getByRole('tab',{name:'결과 리포트',exact:true}).click();await expect(page.getByRole('heading',{name:'판정 FAIL · 동기화 SUCCEEDED'})).toBeVisible();
  const jobId=await page.getByLabel('GUI Test Job').inputValue();const j=await (await page.request.get('/api/v1/gui-test/demo/jobs/'+jobId)).json();
  expect(j.modules.map((m:any)=>m.stages.device_test.status)).toEqual(['FAILED','SUCCEEDED']);}
});
