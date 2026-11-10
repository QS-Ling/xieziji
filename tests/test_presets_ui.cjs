// Isolated browser and simulated controller: never opens the user's Chrome profile.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const jobs=path.join(root,'tests/.testdata/presets-ui-'+process.pid);
const python=spawn('python',['-u','-c',[
 'import sys', 'from backend.server import Application,create_server',
 'from tests.legacy_machine import TestController',
 'app=Application(sys.argv[1],sys.argv[2],controller=TestController())',
 'server=create_server(app,port=0)', 'print(server.server_port,flush=True)', 'server.serve_forever()'
].join('\n'),path.join(root,'tests/fixtures'),jobs],{cwd:root,windowsHide:true});
let browser;
(async()=>{
 const port=await new Promise((resolve,reject)=>{let s='';python.stdout.on('data',d=>{s+=d;if(s.includes('\n'))resolve(Number(s.trim()))});python.on('error',reject);python.on('exit',c=>reject(new Error('Server exited '+c)))});
 browser=await chromium.launch({channel:'msedge',headless:true});
 const base='http://127.0.0.1:'+port;
 const context=await browser.newContext(),page=await context.newPage(),errors=[],posts=[];
 page.on('pageerror',e=>{errors.push(e.message);console.error('Page error:',e.message);});
 page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname)});
 const fonts=await (await context.request.get(base+'/api/fonts')).json();
 const layout={presets:[{id:'legacy-1',name:'旧排版一',values:{width:150,height:200,marginTop:0,marginBottom:0,marginLeft:0,marginRight:0,rows:20,size:5}},
                       {id:'legacy-2',name:'旧排版二',values:{width:184,height:261,marginTop:0,marginBottom:10,marginLeft:0,marginRight:10,rows:33,size:5.5}}],selected:'legacy-2'};
 const font={presets:[{id:'font-legacy',name:'旧字体',mix:[{font_id:fonts.fonts[0].id,weight:100}]}],selected:'font-legacy'};
 await page.addInitScript(({layout,font})=>{
  if(localStorage.getItem('test-seeded'))return;
  localStorage.setItem('plotter.layout-presets.v1',JSON.stringify(layout));
  localStorage.setItem('plotter.font-presets.v1',JSON.stringify(font));
  localStorage.setItem('plotter.layout-mode.v1','notebook');localStorage.setItem('test-seeded','yes');
 },{layout,font});
 async function ready(p){await p.waitForFunction(()=>typeof serverPresetUIReady!=='undefined'&&serverPresetUIReady&&fontPresetsLoaded&&profileLoaded&&window.sharedWorkspace?.ready);}
 async function groups(){return (await (await context.request.get(base+'/api/presets')).json()).groups;}
 await page.goto(base);await ready(page);
 assert.equal(await page.locator('#layoutPreset option').count(),4);
 assert.equal(await page.inputValue('#layoutPreset'),layout.selected);
 assert.equal(await page.inputValue('#fontPreset'),'font-legacy');
 assert.equal((await groups()).layout.presets.length,2);
 await page.evaluate(()=>{$('layoutSettings').open=true;});
 await page.fill('#presetName','服务器新预设');await page.click('#savePreset');
 await page.waitForFunction(()=>!busy&&layoutPresets.length===3);
 let saved=await groups();assert.equal(saved.layout.presets.length,3);
 const newId=saved.layout.presets[2].id;
 // A clean device gets shared presets without any legacy browser storage.
 const clean=await browser.newContext(),other=await clean.newPage();await other.goto(base);await ready(other);
 assert.equal(await other.locator('#layoutPreset option').count(),5);
 await page.fill('#presetName','更新名称');await page.click('#updatePreset');
 await page.waitForFunction(()=>!busy&&layoutPresets.some(p=>p.name==='更新名称'));
 const conflict=await other.evaluate(async()=>{try{await storePresets([...layoutPresets,{...layoutPresets[0],id:'stale',name:'stale'}]);return '';}catch(e){return e.message;}});
 assert.match(conflict,/其他页面已修改/);
 assert(!(await groups()).layout.presets.some(p=>p.id==='stale'));
 await page.click('#deletePreset');await page.waitForFunction(()=>!busy&&layoutPresets.length===2);
 assert.equal((await groups()).layout.presets.length,2);
 await page.click('#undoPreset');await page.waitForFunction(()=>!busy&&layoutPresets.length===3);
 assert.equal(await page.inputValue('#layoutPreset'),newId);
 // A failed delete must leave the displayed collection unchanged.
 await page.route('**/api/presets',route=>route.abort());
 await page.click('#deletePreset');await page.waitForFunction(()=>!busy);
 assert.equal(await page.evaluate(()=>layoutPresets.length),3);
 await page.unroute('**/api/presets');
 await page.selectOption('#layoutMode','grid');await page.fill('#presetName','表格云预设');await page.click('#savePreset');
 await page.waitForFunction(()=>!busy&&layoutPresets.length===1);
 assert.equal((await groups()).grid.presets.length,1);
 await page.selectOption('#layoutMode','notebook');assert.equal(await page.locator('#layoutPreset option').count(),5);
 await page.evaluate(()=>{$('fontSettings').open=true;});await page.fill('#fontPresetName','新字体');await page.click('#saveFontPreset');
 await page.waitForFunction(()=>!busy&&fontPresets.length===2);
 await page.click('#deleteFontPreset');await page.waitForFunction(()=>!busy&&fontPresets.length===1);
 await page.click('#undoFontPreset');await page.waitForFunction(()=>!busy&&fontPresets.length===2);
 assert.equal((await groups()).font.presets.length,2);
 await page.reload();await ready(page);
 assert.equal((await groups()).layout.presets.length,3);assert.equal((await groups()).font.presets.length,2);
 assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('plotter.layout-presets.v1')).presets.length),2);
 assert.deepEqual(errors,[]);
 assert(posts.every(p=>p.startsWith('/api/workspaces/')||['/api/presets/migrate','/api/presets','/api/coordinate-preview','/api/line-pitch','/api/font-previews'].includes(p)),posts.join(','));
 console.log('PASS: legacy migration, clean device, create/update/delete/undo, mode isolation, conflict, offline failure, reload and retained backups; no machine actions');
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{
 if(browser)await browser.close();python.kill();await new Promise(resolve=>python.exitCode!==null?resolve():python.once('exit',resolve));
 // Retain test artifacts for diagnostics; no browser-profile data is copied here.
});
