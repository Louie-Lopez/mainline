// Browser coverage for optional routes and isolation from mainline progress.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn,spawnSync}=require('node:child_process');
const {chromium}=require(process.env.MAINLINE_PLAYWRIGHT||'playwright');
const python=process.env.MAINLINE_PYTHON||'python';
const script=path.resolve(process.env.MAINLINE_SCRIPT||path.join(__dirname,'mainline.py'));
const run=path.join(__dirname,'.test-runs','branch-browser-'+Date.now());fs.mkdirSync(run,{recursive:true});
const state=path.join(run,'state.json');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function cli(...args){const r=spawnSync(python,['-X','utf8',script,...args,'--state',state],{encoding:'utf8',windowsHide:true});assert.equal(r.status,0,r.stderr);return JSON.parse(r.stdout);}
(async()=>{
  cli('init','--task-id','branch-browser','--mainline','Keep the whole project visible.','--stage','Define','--stage','Build','--stage','Deliver','--current','Build');
  cli('status','--done','Define');
  const baseline=cli('read');
  const child=spawn(python,['-X','utf8',script,'serve','--state',state],{stdio:'ignore',windowsHide:true});
  let browser;
  try{
    let url;
    for(let i=0;i<100;i++){try{url=JSON.parse(fs.readFileSync(path.join(run,'state.runtime.json'),'utf8')).url;if((await fetch(url+'/health')).ok)break;}catch{}await pause(50);}
    assert.ok(url);
    browser=await chromium.launch({headless:true,channel:process.env.MAINLINE_BROWSER_CHANNEL||undefined});
    const page=await browser.newPage({locale:'en-US',viewport:{width:1100,height:620},colorScheme:'light'});
    // Existing view tests cover the real polling cadence; accelerate data delivery here.
    await page.addInitScript(()=>{const timeout=window.setTimeout;window.setTimeout=(fn,ms,...args)=>timeout(fn,ms===30000?250:ms,...args);});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(url);await page.waitForFunction(()=>document.querySelector('#axis').dataset.stale==='false');
    assert.equal(await page.locator('.branch-access').count(),0);
    assert.equal(await page.locator('#route-path').isVisible(),false);
    for(const id of ['cloud','local'])cli('branch','--id',id,'--parent','Build','--name',id,'--mainline',id+' goal','--stage','Plan','--stage','Try');
    await page.getByRole('button',{name:'Build, view 2 branches',exact:true}).click();
    await page.getByRole('button',{name:'local Exploring',exact:true}).click();
    assert.equal(await page.locator('#mainline').innerText(),'local goal');
    cli('describe','--branch','local','--stage','Try','--mainline','Try the local approach.','--details','Use it in daily work.');
    cli('status','--branch','local','--done','Plan','--active','Try','--label','Fixing');
    await page.waitForFunction(()=>document.querySelector('.activity')?.textContent==='Fixing');
    await page.getByRole('button',{name:'Try, Fixing, View stage goal',exact:true}).click();
    assert.equal(await page.locator('#stage-details').innerText(),'Use it in daily work.');
    const saved=fs.readFileSync(state,'utf8');
    await page.getByRole('button',{name:'Current branch: local, switch branch',exact:true}).click();
    await page.getByRole('button',{name:'cloud Exploring',exact:true}).click();
    await page.getByRole('button',{name:'Current branch: cloud, switch branch',exact:true}).click();
    await page.getByRole('button',{name:'local Exploring',exact:true}).click();
    assert.equal(await page.locator('#mainline').innerText(),'Try the local approach.');
    assert.equal(fs.readFileSync(state,'utf8'),saved,'view changes must never write progress');
    await page.reload();await page.waitForFunction(()=>document.querySelector('#axis').dataset.stale==='false');
    assert.equal(await page.locator('#route-path').isVisible(),false,'reload starts on mainline');
    assert.equal(await page.locator('#mainline').innerText(),baseline.mainline);
    await page.setViewportSize({width:360,height:780});
    await page.waitForFunction(()=>document.querySelector('#axis').dataset.layout==='vertical');
    await page.getByRole('button',{name:'Build, view 2 branches',exact:true}).click();
    const bounds=await page.locator('#branch-picker').boundingBox();
    assert.ok(bounds.x>=0&&bounds.x+bounds.width<=360);
    await page.getByRole('button',{name:'local Exploring',exact:true}).click();
    cli('branch','--id','local','--archive');
    await page.waitForFunction(()=>document.querySelector('#route-path').hidden);
    assert.equal(await page.getByRole('button',{name:'Build, view 1 branch',exact:true}).count(),1);
    cli('branch','--id','cloud','--archive');
    await page.waitForFunction(()=>!document.querySelector('.branch-access'));
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    const final=cli('read');
    assert.deepEqual(final.stages,baseline.stages);assert.deepEqual(final.stage_statuses,baseline.stage_statuses);
    assert.equal(final.branches.local.stage_labels.Try,'Fixing');assert.deepEqual(errors,[]);
    const report={passed:true,checks:['default mainline','no controls without branches','live scoped updates','view state isolation','reload returns to mainline','narrow layout','archiving retains progress and returns to mainline'],artifacts:run};
    fs.writeFileSync(path.join(run,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  }finally{if(browser)await browser.close();child.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
