import {selectTestSetting} from '../../tests/e2e/settings-controls';
import {jobFixture, moduleFixture, stage, legacySourceFixture, inactiveOrchestrationFixture} from './fixtures';
const {test, expect} = require('./runtime.cjs');
const {startAppServer} = require('./app-server.cjs');
const path = require('node:path');
let host: any;
test.beforeAll(async()=>{host=await startAppServer()});
test.afterAll(async()=>{await host?.close()});

// All responses are synthetic; this suite never sends commands to the running server.
async function setup(page: any) {
  const errors: string[]=[]; page.on('pageerror',(e: Error)=>errors.push(e.message));
  const writes: string[]=[];
  const module=moduleFixture('motion', 'boot', {name:'Motion fixture'});
  module.stages.analysis=stage('RUNNING');
  const job=jobFixture([module],{fingerprint:'synthetic-motion',overall:{done:3,total:6,percent:50}});
  const profile={execution:'demo',runner:'native',workspace:'/synthetic',modules:[],tool_paths:{},models:{},disabled_tools:[],role_instructions:{},agents:{},build_argv:[],max_analysis:1,timeout_seconds:60};
  const tc={id:'tc-motion',name:'Synthetic case',kind:'Single',path:'motion/case',timeout:30,content_hash:'fixture'};
  const run={id:'run-motion',version:1,state:'COMPLETED',overall_result:'PASS',controller:'another-session',simulation:true,
    tests:[tc],results:{'tc-motion':'PASS'},attempts:[],progress:{done:1,total:1,percent:100,counts:{PASS:1}},
    sync:{status:'NOT_LINKED',reason:'Synthetic unlinked run'},connection_snapshot:{},source_revision:'fixture',scenario:'pass',speed:1};
  await page.addInitScript(()=>{
    localStorage.setItem('bsp-job','job-A');localStorage.setItem('gui-last-run','run-motion');
    (window as any).motionTransitions=[];
    document.addEventListener('transitionrun',e=>{const t=e.target as HTMLElement;if(t.classList?.contains('modal'))(window as any).motionTransitions.push(e.propertyName)});
  });
  await page.route('**/api/**',async(route: any)=>{
    const req=route.request(),p=new URL(req.url()).pathname;
    let value: any=[];
    if(req.method()!=='GET') {if(!p.endsWith('/heartbeat'))writes.push(p);value={};}
    else if(p==='/api/v1/config')value={version:1,profile};
    else if(p==='/api/v1/jobs')value=[job];
    else if(p==='/api/v1/jobs/job-A')value=job;
    else if(p==='/api/v1/jobs/job-A/orchestration')value=inactiveOrchestrationFixture(job.version);
    else if(p==='/api/v1/jobs/job-A/reports')value={items:[],limit:50,next_cursor:null,total:0};
    else if(p.endsWith('/source/request-settings'))value={catalog_timeout_seconds:100};
    else if(p.endsWith('/source'))value=legacySourceFixture();
    else if(p.endsWith('/capabilities'))value={mode:'dashboard',simulation:true,branches:['demo/main'],features:{}};
    else if(p.endsWith('/catalog'))value={branch:'demo/main',revision:'fixture',tests:[tc]};
    else if(p.endsWith('/boards'))value={boards:[]};
    else if(p.endsWith('/ports'))value={ports:[],status:'mock'};
    else if(p.endsWith('/runs'))value=[run];
    else if(p.endsWith('/runs/run-motion'))value=run;
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(value)});
  });
  await page.goto(host.url);
  await expect(page.locator('.module-toggle')).toBeVisible();
  return {errors,writes};
}

test('MOTION-01 all six tabs and GUI result/settings/report/audit preserve immediate navigation',async({page})=>{
  const state=await setup(page);
  const nav=page.getByRole('navigation');
  for(const [index,name] of ['대시보드','다이어그램','사람 검토 · Jira','Test 현황','실행 기록','환경 설정'].entries()){
    await nav.getByRole('link',{name,exact:true}).click();
    await expect(nav.getByRole('link',{name,exact:true})).toHaveClass('active');
    await expect(page.locator('main')).toBeVisible();
    if(name==='환경 설정')await expect(page.getByRole('button',{name:'설정 저장',exact:true})).toBeVisible();
    if(name==='Test 현황'){
      await expect(page.getByTestId('run-state')).toContainText('PASS');
      for(const label of ['결과 리포트','감사 이력','TC 결과 · 로그']){
        await page.getByRole('tab',{name:label,exact:true}).click();
        await expect(page.getByRole('tab',{name:label,exact:true})).toHaveAttribute('aria-selected','true');
      }
      const settings=page.getByRole('button',{name:'연결 및 실행 설정',exact:true});
      await expect(page.getByRole('button',{name:'결과',exact:true})).toHaveCount(0);
      await expect(page.getByRole('heading',{name:'결과',exact:true})).toHaveCount(0);
      await settings.click();await expect(settings).toHaveAttribute('aria-expanded','true');
      await expect(page.locator('#gt-settings-view')).toBeVisible();
      await selectTestSetting(page,'source');
      await page.getByLabel('TC 브랜치',{exact:true}).focus();
      await page.keyboard.press('Escape');
      await expect(page.locator('#gt-results-view')).toBeVisible();
      await expect(settings).toHaveAttribute('aria-expanded','false');await expect(settings).toBeFocused();
    }
    await page.screenshot({path:path.resolve(__dirname,`../../.local-reports/motion/tab-${index}.png`),fullPage:true});
  }
  expect(state.errors).toEqual([]);expect(state.writes).toEqual([]);
});

test('MOTION-02 pointer modal entrance, immediate dismissal and keyboard focus restoration',async({page})=>{
  const state=await setup(page);
  const trigger=page.getByRole('button',{name:'새 업그레이드',exact:true});
  await trigger.click();
  const dialog=page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect.poll(()=>page.evaluate(()=>(window as any).motionTransitions)).toContain('transform');
  await expect(dialog.getByRole('button',{name:'닫기',exact:true})).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);await expect(trigger).toBeFocused();
  await page.evaluate(()=>(window as any).motionTransitions=[]);
  await trigger.press('Enter');
  await expect(dialog).toBeVisible();
  expect(await dialog.locator('.modal').evaluate((el:HTMLElement)=>getComputedStyle(el).transitionDuration)).toBe('0s');
  await dialog.getByRole('button',{name:'닫기',exact:true}).press('Enter');
  await expect(dialog).toHaveCount(0);expect(state.writes).toEqual([]);expect(state.errors).toEqual([]);
});

test('MOTION-03 reduced motion removes press scaling, progress movement and modal scaling',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  const state=await setup(page);
  expect(await page.locator('.overall .bar i').evaluate((el:HTMLElement)=>({property:getComputedStyle(el).transitionProperty,transform:getComputedStyle(el).transform}))).toEqual({property:'none',transform:'matrix(0.5, 0, 0, 1, 0, 0)'});
  const trigger=page.getByRole('button',{name:'새 업그레이드',exact:true});
  const box=await trigger.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
  expect(await trigger.evaluate((el:HTMLElement)=>getComputedStyle(el).transform)).toBe('none');
  await page.mouse.up();await expect(page.getByRole('dialog')).toBeVisible();
  expect(await page.getByRole('dialog').locator('.modal').evaluate((el:HTMLElement)=>getComputedStyle(el).transitionProperty)).toBe('opacity');
  await page.keyboard.press('Escape');expect(state.errors).toEqual([]);
});

test('MOTION-04 diagram keyboard camera is immediate and flow uses transform/opacity only',async({page})=>{
  const state=await setup(page);
  await page.getByRole('navigation').getByRole('link',{name:'다이어그램',exact:true}).click();
  // Entering the tab deliberately waits for a fresh host snapshot before flow resumes.
  await expect(page.locator('.wd-traveler').first()).toBeVisible();
  await page.evaluate(()=>{
    (window as any).cameraBehaviors=[];
    const original=Element.prototype.scrollTo;
    Element.prototype.scrollTo=function(...args:any[]){if(this.classList.contains('wd-canvas'))(window as any).cameraBehaviors.push(args[0]?.behavior);return (original as any).apply(this,args)};
  });
  const toggle=page.getByTestId('wd-toggle-motion');await toggle.press('Enter');
  await expect(toggle).toHaveAttribute('aria-expanded','true');
  expect(await page.getByTestId('wd-module-motion').evaluate((el:HTMLElement)=>getComputedStyle(el).transitionDuration)).toBe('0s');
  expect(await page.evaluate(()=>(window as any).cameraBehaviors)).not.toContain('smooth');
  const properties=await page.getByTestId('workflow-diagram').evaluate((el:HTMLElement)=>el.getAnimations({subtree:true}).flatMap(a=>(a.effect as KeyframeEffect).getKeyframes().flatMap(k=>Object.keys(k))));
  expect(properties).toContain('transform');expect(properties).not.toContain('strokeDashoffset');expect(properties).not.toContain('backgroundPosition');
  await page.getByRole('button',{name:'흐름 효과 일시정지'}).click();
  await expect.poll(()=>page.getByTestId('workflow-diagram').evaluate((el:HTMLElement)=>el.getAnimations({subtree:true}).filter(a=>a.playState==='running').length)).toBe(0);
  expect(state.errors).toEqual([]);expect(state.writes).toEqual([]);
});
