// Run with Node and a path to the installed Playwright package as argument 2.
// HTTP is mocked: this exercises the real firmware page without sending IR.
const {chromium} = require(process.argv[2] || 'playwright');
const fs = require('fs'), path = require('path'), assert = require('assert');
(async()=>{
 const pageSource=fs.readFileSync(path.join(__dirname,'learning_page.h'),'utf8').split('R"HTML(')[1].split(')HTML";')[0].replace('__SESSION__','test-session-token');
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:800,height:900}});
  let ready=false; const requests=[];
  await page.route('http://revgen-emitter.local/**',async route=>{
   const request=route.request(), url=new URL(request.url());
   if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:pageSource});
   assert.equal(request.headers()['x-learn-token'],'test-session-token');
   if(url.pathname==='/api/status')return route.fulfill({contentType:'application/json',body:JSON.stringify({ready,version:7,message:ready?'Two matches':'Waiting',code:ready?{protocol:'nec_raw',raw:123}:null,entries:[{device_name:'<img src=x onerror=alert(1)>',name:'Volume up',synced:true}]})});
   requests.push([url.pathname,request.postDataJSON()]);
   if(url.pathname==='/api/capture')ready=true;
   return route.fulfill({contentType:'application/json',body:'{"message":"Saved locally"}'});
  });
  let alerts=0;
  page.on('dialog',async dialog=>{if(dialog.type()==='alert')alerts++;await dialog.accept();});
  await page.goto('http://revgen-emitter.local/');
  await page.waitForFunction(()=>document.querySelector('#entries li'));
  assert(await page.locator('#test').isDisabled());
  assert(await page.locator('#save').isDisabled());
  assert.equal(await page.locator('#entries img').count(),0);
  await page.locator('#capture').click();
  await page.waitForFunction(()=>!document.querySelector('#save').disabled);
  await page.locator('#test').click();
  await page.locator('#save').click();
  await page.waitForFunction(()=>document.querySelector('#message').textContent==='Saved locally');
  await page.locator('#channel_id').fill('news_hd');await page.locator('#channel_name').fill('News HD');await page.locator('#channel_number').fill('101');await page.locator('#channel').click();
  await page.waitForTimeout(100);
  assert(requests.some(([p,d])=>p==='/api/save'&&d.device==='tv'&&d.action==='volume_up'&&d.version===7));
  assert(requests.some(([p,d])=>p==='/api/test'&&d.version===7));
  assert(requests.some(([p,d])=>p==='/api/channel'&&d.device==='stb'&&d.channel_number==='101'));
  assert.equal(alerts,0);
  fs.mkdirSync(path.join(__dirname,'build'),{recursive:true});
  await page.screenshot({path:path.join(__dirname,'build/learning-ui.png'),fullPage:true});
  await page.locator('#exit').click();
  console.log('PASS: session token, capture gating, captured version, save, channel mapping, XSS-safe names, exit.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
