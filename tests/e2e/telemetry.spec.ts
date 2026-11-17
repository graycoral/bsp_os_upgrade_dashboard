import {test,expect} from '../../apps/web/node_modules/@playwright/test';

test('T-274 explicit implementation selection persists with Sonnet default',async({page})=>{
 await page.goto('/');
 await page.getByRole('navigation').getByRole('link',{name:'환경 설정',exact:true}).click();
 const select=page.getByRole('combobox',{name:'구현 도구',exact:true});
 await expect(select).toHaveValue('claude');
 await expect(page.getByLabel('claude 모델 (선택)',{exact:true})).toHaveValue('sonnet');
 await select.selectOption('opencode');
 await page.getByRole('button',{name:'설정 저장',exact:true}).click();
 await expect(page.getByRole('status').filter({hasText:'설정을 저장'})).toBeVisible();
 await page.reload();
 await expect(select).toHaveValue('opencode');
 await select.selectOption('claude');
 await page.getByRole('button',{name:'설정 저장',exact:true}).click();
});

test('T-276 compact totals, phase/module time, paged ROUND and same-version metering',async({page})=>{
 const created=await page.request.post('/api/v1/jobs',{data:{title:'사용량 모의 표시'},headers:{'X-BSP-Client':'dashboard','Idempotency-Key':crypto.randomUUID()}});
 const id=(await created.json()).job_id;
 const job=await (await page.request.get(`/api/v1/jobs/${id}`)).json();
 let price='0.0123';
 const models=()=>[{provider:'anthropic',model:'sonnet-fixture',input_tokens:120,output_tokens:20,cache_read_tokens:10,cache_write_tokens:5,cost_usd:price}];
 const summary=()=>({status:'reported',models:models(),cost_usd:price,reported_cost_usd:price,round_count:31,call_count:31,total_seconds:120,elapsed_seconds:75});
 await page.route(`**/api/v1/jobs/${id}`,async route=>{
  const value=structuredClone(job);value.telemetry=summary();value.modules.forEach((m:any)=>{m.telemetry=summary();Object.values(m.stages).forEach((s:any)=>s.telemetry=summary())});
  await route.fulfill({json:value});
 });
 const queried:string[]=[];
 await page.route(`**/api/v1/jobs/${id}/telemetry?**`,async route=>{
  const url=new URL(route.request().url());queried.push(url.search);
  const offset=Number(url.searchParams.get('offset')||0),limit=Number(url.searchParams.get('limit')||25);
  const items=Array.from({length:31},(_,i)=>({id:'round-'+i,ordinal:31-i,module_name:'Bootloader',stage:'analysis',started_at:new Date(Date.UTC(2026,10,17,0,0,31-i)).toISOString(),telemetry:summary(),calls:[]}));
  await route.fulfill({json:{items:items.slice(offset,offset+limit),total:31,offset,next_offset:offset+limit<31?offset+limit:null}});
 });
 await page.addInitScript(value=>localStorage.setItem('bsp-job',value),id);
 await page.goto('/');
 const totals=page.getByLabel('전체 작업 토큰 비용 시간');
 await expect(totals).toContainText('경과 1분 15초');
 await expect(totals).toContainText('ROUND 누적 2분 0초');
 await expect(totals).toContainText('sonnet-fixture · 입력 120 / 출력 20 tok');
 await expect(totals).toContainText('$0.0123');
 await expect(totals.locator('.bsp-telemetry-brief')).toHaveCSS('font-size','11px');
 await totals.getByText('전체 모델별 토큰·비용 / ROUND',{exact:true}).click();
 await expect(totals.locator('.bsp-rounds article')).toHaveCount(25);
 await totals.getByRole('button',{name:'이전 ROUND 더 보기'}).click();
 await expect(totals.locator('.bsp-rounds article')).toHaveCount(31);
 await expect(totals).toContainText('ROUND 1');
 price='0.025';
 await expect(totals.locator('.bsp-telemetry-brief')).toContainText('$0.0250',{timeout:12000});
 await page.getByRole('button',{name:/Bootloader 선행 그룹/}).click();
 const detail=page.locator('.detail').first();
 await detail.getByText('모듈 모델별 토큰·비용 / ROUND',{exact:true}).click();
 await expect.poll(()=>queried.some(q=>q.includes('module_id='+job.modules[0].id))).toBe(true);
 await detail.getByText('요구사항 분석 모델별 토큰·비용 / ROUND',{exact:true}).click();
 await expect.poll(()=>queried.some(q=>q.includes('stage=analysis'))).toBe(true);
 await page.setViewportSize({width:640,height:1000});
 await expect(totals).toBeVisible();
 await expect(totals).toContainText('캐시 읽기 10 / 쓰기 5');
});
