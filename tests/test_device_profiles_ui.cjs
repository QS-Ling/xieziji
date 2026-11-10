const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),jobs=path.resolve(root,'tests/.testdata/device-ui-'+process.pid);
const python=spawn('python',['-u','-c',[
 'import sys',
 'from backend.server import Application,create_server',
 'from tests.legacy_machine import TestController',
 'app=Application(sys.argv[1],sys.argv[2],controller=TestController())',
 'server=create_server(app,port=0)',
 'print(server.server_port,flush=True)',
 'server.serve_forever()'
].join('\n'),path.resolve(root,'../gcodeFonts'),jobs],{cwd:root,windowsHide:true});
let browser;
(async()=>{
 const port=await new Promise((resolve,reject)=>{let out='';python.stdout.on('data',d=>{out+=d;if(/^\d+\r?\n/.test(out))resolve(Number(out.trim()));});python.on('error',reject);python.on('exit',c=>reject(Error('server exited '+c)));});
 browser=await chromium.launch({headless:true,channel:'msedge'});
 const page=await browser.newPage({viewport:{width:1280,height:1000}}),errors=[],posts=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname);});
 await page.route('**/api/ports',r=>r.fulfill({json:{ports:[{device:'COM5',description:'USB'},{device:'COM1',description:'USB'}]}}));
 await page.goto('http://127.0.0.1:'+port);
 await page.waitForFunction(()=>document.querySelector('#port').options.length===2);
 await page.selectOption('#layoutMode','notebook');
 await page.locator('#coordinateSettings>summary').click();
 await page.fill('#deviceName','书桌设备');await page.selectOption('#controllerType','grbl');
 await page.fill('#penUpZ','-1.25');await page.fill('#penDownZ','-3.5');await page.fill('#penFeed','200');
 await page.check('#swapXY');await page.check('#reverseX');await page.selectOption('#originCorner','bottom-right');
 await page.selectOption('#port','COM1');
 await page.waitForFunction(()=>document.querySelector('#penUpZ').value==='0'&&!document.querySelector('#swapXY').checked);
 assert.equal(await page.inputValue('#deviceName'),'');
 await page.fill('#deviceName','备用设备');await page.fill('#penDownZ','2.5');
 await page.selectOption('#port','COM5');
 await page.waitForFunction(()=>document.querySelector('#deviceName').value==='书桌设备');
 assert.equal(await page.inputValue('#penUpZ'),'-1.25');assert.equal(await page.inputValue('#penDownZ'),'-3.5');
 assert.equal(await page.inputValue('#controllerType'),'grbl');assert.equal(await page.isChecked('#swapXY'),true);
 assert.equal(await page.inputValue('#originCorner'),'bottom-right');
 await page.reload();await page.waitForFunction(()=>document.querySelector('#deviceName').value==='书桌设备');
 assert.equal(await page.inputValue('#penDownZ'),'-3.5');
 const response=await page.request.get('http://127.0.0.1:'+port+'/api/device-profiles'), data=await response.json();
 assert.equal(data.profiles.COM1.name,'备用设备');assert.equal(data.profiles.COM5.device_control.pen_feed,200);
 await page.locator('.machine').screenshot({path:path.resolve(root,'docs/device-profiles-preview.png')});
 assert.deepEqual(errors,[]);assert.ok(posts.every(p=>['/api/device-profiles','/api/coordinate-preview','/api/font-previews','/api/line-pitch'].includes(p)||p.startsWith('/api/workspaces/')),posts.join(','));
 console.log('PASS: per-port names, Z and controller type, XY mapping, automatic save/restore, reload persistence; no motion requests');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();python.kill();await new Promise(resolve=>python.exitCode!==null?resolve():python.once('exit',resolve));if(path.dirname(jobs)===path.resolve(root,'tests/.testdata'))fs.rmSync(jobs,{recursive:true,force:true});});
