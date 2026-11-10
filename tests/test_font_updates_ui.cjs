// Real browser + real background analyzer, using disposable fonts and a fake controller.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const sandbox=path.join(root,'tests/.testdata/font-refresh-ui-'+process.pid);
fs.mkdirSync(path.join(sandbox,'fonts'),{recursive:true});
const fixture=path.join(root,'tests/fixtures/fixture.gfont');
fs.copyFileSync(fixture,path.join(sandbox,'fonts/first.gfont'));
const python=spawn(process.env.PYTHON||'python',['-u','-c',[
  'import sys',
  'from backend.server import Application,create_server',
  'from tests.legacy_machine import TestController',
  'app=Application(sys.argv[1],sys.argv[2],controller=TestController())',
  'server=create_server(app,port=0)',
  'print(server.server_port,flush=True)',
  'server.serve_forever()'
].join('\n'),path.join(sandbox,'fonts'),path.join(sandbox,'jobs')],{cwd:root,windowsHide:true});
let browser;
(async()=>{
  const port=await new Promise((resolve,reject)=>{
    let output='';python.stdout.on('data',data=>{output+=data;if(/^\d+\r?\n/.test(output))resolve(Number(output.trim()));});
    python.on('error',reject);python.on('exit',code=>reject(new Error('Server exited: '+code)));
  });
  browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'msedge'});
  const page=await browser.newPage({viewport:{width:1200,height:950}});
  const errors=[],posts=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if(request.method()==='POST')posts.push(new URL(request.url()).pathname);});
  await page.goto('http://127.0.0.1:'+port);
  await page.waitForFunction(()=>window.sharedWorkspace?.ready);
  await page.selectOption('#layoutMode','notebook');
  await page.locator('#fontSettings>summary').click();
  assert.equal(await page.locator('#chooseFonts').evaluate(n=>getComputedStyle(n).backgroundColor),'rgb(139, 96, 62)');
  await page.locator('#chooseFonts').screenshot({path:path.join(sandbox,'font-check-button.png')});
  await page.click('#chooseFonts');
  await page.waitForFunction(()=>document.querySelector('#fontPageInfo').textContent.includes('1 种字体'));
  await page.click('#refreshFontLibrary');
  await page.waitForFunction(()=>document.querySelector('#fontRefreshStatus').textContent.startsWith('已检查：')&&!document.querySelector('#refreshFontLibrary').disabled);
  fs.copyFileSync(fixture,path.join(sandbox,'fonts/second.gfont'));
  await page.click('#refreshFontLibrary');
  await page.waitForFunction(()=>document.querySelector('#fontPageInfo').textContent.includes('2 种字体'));
  await page.waitForFunction(()=>document.querySelector('#fontRefreshStatus').textContent.startsWith('已检查：')&&!document.querySelector('#refreshFontLibrary').disabled);
  await page.locator('#fontDialog').screenshot({path:path.join(sandbox,'font-check-dialog.png')});
  fs.unlinkSync(path.join(sandbox,'fonts/first.gfont'));
  await page.click('#refreshFontLibrary');
  await page.waitForFunction(()=>document.querySelector('#fontPageInfo').textContent.includes('1 种字体')&&document.querySelector('#font').textContent==='second');
  await page.waitForFunction(()=>document.querySelector('#fontRefreshStatus').textContent.startsWith('已检查：')&&!document.querySelector('#refreshFontLibrary').disabled);
  const status=await page.evaluate(async()=>await(await fetch('/api/font-status')).json());
  const completed=status.analyzed_at;
  await page.click('#refreshFontLibrary');
  await page.waitForFunction(()=>!document.querySelector('#refreshFontLibrary').disabled);
  const unchanged=await page.evaluate(async()=>await(await fetch('/api/font-status')).json());
  assert.equal(unchanged.analyzed_at,completed);
  assert.deepEqual(errors,[]);
  assert.ok(posts.every(p=>['/api/font-refresh','/api/font-previews','/api/coordinate-preview'].includes(p)||p.startsWith('/api/workspaces/')||p==='/api/line-pitch'),posts.join(', '));
  console.log('PASS: deep button, manual refresh, automatic analysis, new/deleted fonts without restart, unchanged skip, no machine commands');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();
  python.kill();
  await new Promise(resolve=>python.exitCode!==null?resolve():python.once('exit',resolve));
  assert.equal(path.dirname(sandbox),path.resolve(root,'tests/.testdata'));
  fs.rmSync(sandbox,{recursive:true,force:true});
});
