// Language selection must never translate or mutate project-authored content.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn,spawnSync}=require('node:child_process');
const {chromium}=require(process.env.MAINLINE_PLAYWRIGHT||'playwright');
const python=process.env.MAINLINE_PYTHON||'python';
const run=path.join(__dirname,'.test-runs','languages-'+Date.now());fs.mkdirSync(run,{recursive:true});
const state=path.join(run,'state.json'),script=path.resolve(process.env.MAINLINE_SCRIPT||path.join(__dirname,'mainline.py'));
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const goal='Keep the whole project in view, from the original goal to delivery.';
const names=['Define','Design','Build','Validate','Deliver'];
function cli(...args){const r=spawnSync(python,['-X','utf8',script,...args,'--state',state],{encoding:'utf8',windowsHide:true});assert.equal(r.status,0,r.stderr);return JSON.parse(r.stdout);}
(async()=>{
  cli('init','--task-id','language-demo','--mainline',goal,...names.flatMap(name=>['--stage',name]),'--current','Build');
  cli('status','--done','Define','--done','Design','--active','Validate');
  cli('subdivide','--parent','Build','--stage','State','--stage','View','--stage','Instructions','--current','View');
  cli('describe','--stage','Build','--mainline','Make the agreed design work reliably.');
  cli('describe','--parent','Build','--stage','View','--mainline','Make current and parallel work easy to see.','--details','A responsive timeline with optional substages. Select a stage to see its purpose and scope.');
  const child=spawn(python,['-X','utf8',script,'serve','--state',state],{windowsHide:true,stdio:'ignore'});
  let browser;
  try{
    let url;
    for(let i=0;i<100;i++){try{url=JSON.parse(fs.readFileSync(path.join(run,'state.runtime.json'),'utf8')).url;if((await fetch(url+'/health')).ok)break;}catch{}await pause(50);}
    assert.ok(url);
    browser=await chromium.launch({headless:true,channel:process.env.MAINLINE_BROWSER_CHANNEL||undefined});
    const original=fs.readFileSync(state,'utf8');
    for(const [locale,query,language,badge] of [
      ['en-US','','en','In progress'],['zh-CN','','zh-CN','进行中'],
      ['zh-CN','?lang=en','en','In progress'],['en-US','?lang=zh','zh-CN','进行中'],
      ['de-DE','','en','In progress'],['en-US','?lang=unsupported','en','In progress'],
      ['en-US','?lang=zh-TW','zh-CN','进行中']
    ]){
      const page=await browser.newPage({locale,viewport:{width:1200,height:430},colorScheme:'light'});
      await page.goto(url+'/'+query);
      await page.waitForFunction(()=>document.querySelector('#axis').dataset.stale==='false');
      assert.equal(await page.locator('html').getAttribute('lang'),language);
      assert.deepEqual(await page.locator('.activity').allTextContents(),[badge,badge]);
      assert.equal(await page.locator('#mainline').innerText(),goal);
      assert.equal(await page.locator('#axis').getAttribute('aria-label'),language==='en'?'Project stages':'项目阶段');
      assert.equal(await page.locator('#axis').getAttribute('data-layout'),'horizontal');
      if(locale==='en-US'&&!query){
        await page.screenshot({path:path.join(run,'overview-en.png'),animations:'disabled'});
        await page.locator('button[data-parent="Build"]').click();
        await page.locator('.children button[data-stage="View"]').click();
        assert.match(await page.locator('.children').getAttribute('aria-label'),/Substages of Build/);
        assert.match(await page.locator('#stage-details').innerText(),/responsive timeline/);
        await page.screenshot({path:path.join(run,'expanded-en.png'),fullPage:true,animations:'disabled'});
        await page.setViewportSize({width:360,height:700});
        await page.waitForFunction(()=>document.querySelector('#axis').dataset.layout==='vertical');
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
        await page.screenshot({path:path.join(run,'vertical-en.png'),fullPage:true});
        await page.emulateMedia({colorScheme:'dark'});
        await page.screenshot({path:path.join(run,'dark-en.png'),fullPage:true});
      }
      await page.close();
    }
    assert.equal(fs.readFileSync(state,'utf8'),original);
    cli('status','--active','Validate','--label','修复错误');
    const custom=await browser.newPage({locale:'en-US'});
    await custom.goto(url+'/?lang=en');await custom.waitForFunction(()=>document.querySelector('#axis').dataset.stale==='false');
    assert.ok((await custom.locator('.activity').allTextContents()).includes('修复错误'));
    await custom.close();
    console.log(JSON.stringify({passed:true,checks:'browser locale, query override, unsupported fallback, accessible text, read-only content, English responsive layout, custom labels preserved',artifacts:run},null,2));
  }finally{if(browser)await browser.close();child.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
