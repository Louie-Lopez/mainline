// Check the real renderer in the server-free public demo, including the Pages subpath.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {chromium}=require(process.env.MAINLINE_PLAYWRIGHT||'playwright');
const run=path.join(__dirname,'.test-runs','demo-'+Date.now());fs.mkdirSync(run,{recursive:true});
const html=fs.readFileSync(path.join(__dirname,'docs/index.html'));
const server=http.createServer((req,res)=>{res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});res.end(html);});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const url='http://127.0.0.1:'+server.address().port+'/mainline/';
  let browser;
  try{
    browser=await chromium.launch({headless:true,channel:process.env.MAINLINE_BROWSER_CHANNEL||undefined});
    for(const language of ['en','zh']){
      const page=await browser.newPage({locale:language==='en'?'en-US':'zh-CN',viewport:{width:1280,height:760},colorScheme:'light'});
      const errors=[],requests=[];page.on('pageerror',error=>errors.push(String(error)));page.on('request',request=>requests.push(request.url()));
      await page.goto(url);
      assert.equal(await page.locator('html').getAttribute('lang'),language==='zh'?'zh-CN':'en');
      assert.equal(await page.locator('#axis').getAttribute('data-layout'),'horizontal');
      assert.equal(await page.locator('#axis > .stage[data-status="active"]').count(),2);
      assert.equal(await page.locator('#axis').getAttribute('data-stale'),'false');
      assert.equal(await page.locator('#view-details').innerText(),language==='zh'?'环节说明':'Stage details');
      await page.locator('#view-todos').click();
      assert.equal(await page.locator('#todo-panel').innerText(),language==='zh'?'暂无待办':'No to-dos');
      await page.locator('#view-details').click();
      const goal=await page.locator('#mainline').innerText();
      await page.locator('.scenarios button').nth(2).click();
      assert.equal(await page.locator('.activity').first().innerText(),language==='zh'?'修复错误':'Fixing');
      await page.locator('button[data-parent]').click();
      assert.equal(await page.locator('.children .stage').count(),3);
      await page.locator('.children button').nth(1).click();
      assert.notEqual(await page.locator('#mainline').innerText(),goal);
      assert.equal(await page.locator('#stage-details').isVisible(),true);
      await page.screenshot({path:path.join(run,'expanded-'+language+'.png')});
      await page.locator('.children button').nth(1).press('Enter');
      assert.equal(await page.locator('#mainline').innerText(),goal);
      await page.locator('.scenarios button').nth(3).click();
      assert.equal(await page.locator('#axis > .stage[data-status="done"]').count(),5);
      await page.locator('.scenarios button').nth(0).click();
      assert.equal(await page.locator('#axis > .stage[data-status="pending"]').count(),4);
      assert.equal(await page.locator('#axis > .stage[data-status="active"]').count(),1);
      await page.reload();
      assert.equal(await page.locator('.scenarios button[aria-pressed="true"]').innerText(),language==='zh'?'开始':'Starting');
      await page.locator('.scenarios button').nth(1).click();
      await page.screenshot({path:path.join(run,'overview-'+language+'.png')});
      await page.setViewportSize({width:360,height:800});
      await page.emulateMedia({colorScheme:'dark',reducedMotion:'reduce'});
      await page.waitForFunction(()=>document.querySelector('#axis').dataset.layout==='vertical');
      await page.locator('button[data-parent]').click();
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      await page.screenshot({path:path.join(run,'narrow-'+language+'.png'),fullPage:true});
      assert.equal(requests.some(u=>u.includes('/state')),false);
      assert.equal(requests.every(u=>u.startsWith(url)),true);
      assert.deepEqual(errors,[]);
      const other=language==='zh'?'en':'zh';
      await page.locator('#lang-'+other).click();
      assert.equal(await page.locator('html').getAttribute('lang'),other==='zh'?'zh-CN':'en');
      assert.equal(await page.locator('#axis > .stage[data-status="active"]').count(),2);
      await page.close();
    }
    const page=await browser.newPage({locale:'de-DE'});
    await page.goto(url+'?lang=invalid&step=invalid');
    assert.equal(await page.locator('html').getAttribute('lang'),'en');
    assert.equal(await page.locator('#axis > .stage[data-status="active"]').count(),2);
    console.log(JSON.stringify({result:'passed',screenshots:run,languages:2,scenarios:4}));
  }finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
