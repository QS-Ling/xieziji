// Import replaces one page only after validation; new defaults reach real preview G-code.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),artifacts=path.resolve(root,'../analysis/deployment');
const jobs=path.resolve(root,'tests/.testdata/import-ui-'+process.pid);
const python=spawn('python',['-u','-c',[
 'import pathlib,sys','import backend.server as service','from tests.legacy_machine import TestController',
 'service.STATIC=pathlib.Path(sys.argv[1])',
 'app=service.Application(sys.argv[2],sys.argv[3],controller=TestController())',
 'server=service.create_server(app,port=0)','print(server.server_port,flush=True)','server.serve_forever()'
].join('\n'),path.resolve(artifacts,'glyph-fallback-ui/frontend'),path.resolve(root,'tests/fixtures'),jobs],{cwd:root,windowsHide:true});
let browser;
(async()=>{
 const port=await new Promise((resolve,reject)=>{let s='';python.stdout.on('data',d=>{s+=d;if(s.includes('\n'))resolve(Number(s.trim()))});python.on('error',reject);python.on('exit',code=>reject(new Error('Server exited '+code)))});
 browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage(),errors=[],posts=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname)});
 await page.goto('http://127.0.0.1:'+port);await page.waitForFunction(()=>typeof fonts!=='undefined'&&fonts.length>0&&profileLoaded);await page.selectOption('#layoutMode','notebook');
 assert.equal(await page.inputValue('#feed'),'10000');assert.equal(await page.inputValue('#moveFeed'),'10000');
 assert.equal(await page.getAttribute('#feed','max'),'12000');
 const upload=async(name,text)=>{await page.setInputFiles('#textFile',{name,mimeType:'text/plain',buffer:Buffer.from(text)});await page.waitForFunction(()=>!busy);};
 await upload('first.txt','\uFEFFHello\r\nWorld');
 assert.deepEqual(await page.evaluate(()=>({pages:sourcePages,index:sourceIndex,text:$('text').value})),{pages:['Hello\nWorld'],index:0,text:'Hello\nWorld'});
 await page.evaluate(()=>{sourcePages=['keep page one','old English example'];sourceIndex=1;renderSourcePages();});
 await upload('second.md','# New\nABC');
 assert.deepEqual(await page.evaluate(()=>sourcePages),['keep page one','# New\nABC']);assert.equal(await page.inputValue('#inputFormat'),'markdown');
 await upload('invalid.exe','not text');assert.deepEqual(await page.evaluate(()=>sourcePages),['keep page one','# New\nABC']);
 await page.setInputFiles('#textFile',[]);await page.waitForFunction(()=>!busy);assert.equal(await page.inputValue('#text'),'# New\nABC');
 await page.evaluate(()=>{sourcePages=['A'.repeat(29990),'unchanged'];sourceIndex=1;renderSourcePages();});
 await upload('too-long.txt','B'.repeat(20));assert.equal(await page.inputValue('#text'),'unchanged');
 await page.evaluate(()=>{sourcePages=Array.from({length:100},()=> 'A');sourceIndex=99;renderSourcePages();});
 await upload('at-page-limit.txt','B');assert.equal(await page.evaluate(()=>sourcePages.length),100);assert.equal(await page.inputValue('#text'),'B');
 await page.evaluate(()=>{sourcePages=['A'.repeat(30000)];sourceIndex=0;renderSourcePages();});
 await upload('short.txt','Hello');assert.deepEqual(await page.evaluate(()=>sourcePages),['Hello']);
 const result=await page.evaluate(async()=>{
  const basic=await api('/api/preview',{font_id:fonts[0].id,text:'Hello'});
  const notebook=await api('/api/preview',{...paperSettings(),font_mix:selectedFonts,text:'Hello'});
  const gcode=await (await request('/api/jobs/'+notebook.pages[0].job_id+'/gcode')).text();
  return {basic:basic.metadata,notebook:notebook.pages[0].metadata,gcode};
 });
 assert.equal(result.basic.feed,10000);assert.equal(result.basic.move_feed,10000);assert.equal(result.notebook.feed,10000);assert.equal(result.notebook.move_feed,10000);assert.match(result.gcode,/G1 Z10 F10000/);
 await page.selectOption('#layoutMode','grid');assert.equal(await page.inputValue('#feed'),'10000');assert.equal(await page.inputValue('#moveFeed'),'10000');
 assert.deepEqual(errors,[]);assert(posts.every(p=>['/api/font-previews','/api/preview','/api/coordinate-preview','/api/line-pitch'].includes(p)),posts.join(','));
 const saved={passed:true,replace_current_page:true,other_pages_preserved:true,validation_preserves_original:true,all_100_pages_importable:true,draw_feed:result.notebook.feed,move_feed:result.notebook.move_feed,no_machine_actions:true};
 fs.writeFileSync(path.resolve(artifacts,'import-defaults-ui.json'),JSON.stringify(saved,null,2));console.log(JSON.stringify(saved));
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{
 if(browser)await browser.close();python.kill();await new Promise(resolve=>python.exitCode!==null?resolve():python.once('exit',resolve));
 assert.equal(path.dirname(jobs),path.resolve(root,'tests/.testdata'));fs.rmSync(jobs,{recursive:true,force:true});
});
