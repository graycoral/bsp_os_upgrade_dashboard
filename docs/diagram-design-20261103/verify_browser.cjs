const { chromium } = require('../../apps/web/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const crypto = require('node:crypto');

(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const results=[];
  try {
    for(const variant of ['default','blueprint']){
      const file=path.join(__dirname,`bsp-system-${variant}.html`);
      const page=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
      await page.goto(pathToFileURL(file).href,{waitUntil:'networkidle'});
      await page.evaluate(()=>document.fonts.ready);
      const desktop=await page.evaluate(()=>{
        const overflow=[];
        for(const group of document.querySelectorAll('g[data-node]')){
          const bounds=group.querySelector('rect').getBBox();
          for(const t of group.querySelectorAll('text')){
            const b=t.getBBox();
            if(b.x<bounds.x+6||b.x+b.width>bounds.x+bounds.width-6||b.y<bounds.y||b.y+b.height>bounds.y+bounds.height)
              overflow.push({node:group.dataset.node,text:t.textContent,box:{x:b.x,y:b.y,width:b.width,height:b.height}});
          }
        }
        const missingLinks=[...document.querySelectorAll('a[href^="#"]')].filter(a=>!document.getElementById(a.hash.slice(1))).map(a=>a.hash);
        return {overflow,missingLinks,svgCount:document.querySelectorAll('svg').length,
          diagrams:[...document.querySelectorAll('svg')].map(s=>({nodes:s.querySelectorAll('g[data-node]').length,edges:s.querySelectorAll('path[data-edge]').length})),
          fonts:{sans:getComputedStyle(document.querySelector('.name')).fontFamily,title:getComputedStyle(document.querySelector('h1')).fontFamily,
            loaded:[...document.fonts].filter(f=>f.status==='loaded').map(f=>f.family).filter((v,i,a)=>a.indexOf(v)===i)},
          pageOverflow:document.documentElement.scrollWidth>innerWidth+1};
      });
      for(let i=0;i<2;i++)await page.locator('svg').nth(i).screenshot({path:path.join(__dirname,'verification',`${variant}-figure-${i+1}.png`)});
      await page.setViewportSize({width:390,height:844});
      const mobile=await page.evaluate(()=>({pageOverflow:document.documentElement.scrollWidth>innerWidth+1,scrollers:[...document.querySelectorAll('.diagram-container')].map(el=>({width:el.clientWidth,scrollWidth:el.scrollWidth,overflowX:getComputedStyle(el).overflowX,minWidth:getComputedStyle(el.querySelector('svg')).minWidth}))}));
      await page.emulateMedia({media:'print'});
      const print=await page.evaluate(()=>[...document.querySelectorAll('svg')].map(s=>({minWidth:getComputedStyle(s).minWidth,overflowX:getComputedStyle(s.parentElement).overflowX})));
      const ok=!desktop.overflow.length&&!desktop.missingLinks.length&&!desktop.pageOverflow&&!mobile.pageOverflow&&mobile.scrollers.every(s=>s.overflowX==='auto'&&s.scrollWidth>s.width&&s.minWidth==='1280px')&&print.every(s=>s.minWidth==='0px'&&s.overflowX==='visible');
      results.push({file:path.basename(file),sha256:crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'),ok,desktop,mobile,print});
      await page.close();
    }
  } finally {await browser.close();}
  fs.writeFileSync(path.join(__dirname,'verification','browser.json'),JSON.stringify(results,null,2));
  console.log(JSON.stringify(results,null,2));
  if(results.some(r=>!r.ok))process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1});
