const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process');const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),jobs=path.resolve(root,'tests/.testdata/notifications-ui-'+process.pid);
const python=spawn('python',['-u','-c',[
 'import sys',
 'from backend.server import Application,create_server',
 'from tests.legacy_machine import TestController',
 'app=Application(sys.argv[1],sys.argv[2],controller=TestController())',
 'server=create_server(app,port=0)',
 'print(server.server_port,flush=True)',
 'server.serve_forever()'
].join('\n'),path.resolve(root,'tests/fixtures'),jobs],{cwd:root,windowsHide:true});
let browser;
(async()=>{
 const port=await new Promise((resolve,reject)=>{let out='';python.stdout.on('data',d=>{out+=d;if(/^\d+\r?\n/.test(out))resolve(Number(out.trim()));});python.on('error',reject);python.on('exit',c=>reject(Error('server exited '+c)));});
 const origin='http://127.0.0.1:'+port;
 browser=await chromium.launch({headless:true,channel:'msedge'});const context=await browser.newContext({permissions:['notifications'],viewport:{width:1280,height:1000}});
 let state={connected:false,port:'COM5',phase:'idle',mode:'simulation',total:0,acknowledged:0},errors=[],posts=[];
 await context.route('**/api/state',r=>r.fulfill({json:state}));
 await context.route('**/api/ports',r=>r.fulfill({json:{ports:[{device:'COM5',description:'USB'}]}}));
 await context.addInitScript(()=>{
   window.__notifications=[];
   ServiceWorkerRegistration.prototype.showNotification=async function(title,options){window.__notifications.push({title,options});};
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname);});
 await page.goto(origin);await page.waitForSelector('#enablePageNotifications');
 await page.click('#enablePageNotifications');await page.waitForFunction(()=>document.querySelector('#enablePageNotifications').textContent.includes('关闭'));
 await page.click('#testPageNotification');await page.waitForFunction(()=>window.__notifications.length===1);
 assert.equal(await page.evaluate(async()=>!!(await navigator.serviceWorker.getRegistration('/'))?.active),true);
 state={...state,connected:true,phase:'running',job_id:'page-a',total:10,acknowledged:1,operation_type:'writing'};
 await page.waitForFunction(()=>document.querySelector('#phase').textContent==='正在写字');
 await page.evaluate(s=>window.pageReminders.remember(s,{page:1,pages:2,device:'书桌写字机'}),state);
 state={...state,phase:'draining',acknowledged:10};await page.waitForTimeout(1000);assert.equal(await page.evaluate(()=>window.__notifications.length),1);
 state={...state,phase:'complete',operation_type:null};await page.waitForFunction(()=>window.__notifications.length===2);
 assert.match(await page.textContent('#pageCompletion'),/第 1 \/ 2 页/);
 await page.waitForTimeout(1000);assert.equal(await page.evaluate(()=>window.__notifications.length),2);
 await page.reload();await page.waitForTimeout(1100);assert.equal(await page.evaluate(()=>window.__notifications.length),0,'Reload must not repeat');
 state={...state,job_id:'page-b',phase:'running',operation_type:'writing',acknowledged:0};await page.waitForFunction(()=>document.querySelector('#phase').textContent==='正在写字');
 await page.evaluate(s=>window.pageReminders.remember(s,{page:2,pages:2}),state);
 state={...state,phase:'complete',operation_type:null,acknowledged:10};await page.waitForFunction(()=>window.__notifications.length===1);
 assert.match(await page.textContent('#pageCompletion'),/最后一页/);
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.deepEqual(errors,[]);assert.ok(posts.every(p=>['/api/coordinate-preview','/api/font-previews','/api/device-profiles'].includes(p)||p.startsWith('/api/workspaces/')),posts.join(','));
 console.log('PASS: real page and service worker, permission/test controls, completion polling, two pages, reload dedup, mobile layout; no OS notifications or machine movements sent');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();python.kill();await new Promise(resolve=>python.exitCode!==null?resolve():python.once('exit',resolve));if(path.dirname(jobs)===path.resolve(root,'tests/.testdata'))fs.rmSync(jobs,{recursive:true,force:true});});
