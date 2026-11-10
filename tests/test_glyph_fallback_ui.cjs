// Test the currently deployed HTML, including zoom and script-specific controls.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const ui=process.env.PLOTTER_TEST_UI||path.resolve(root,'../analysis/deployment/glyph-fallback-ui/frontend');
const source=[
 'import json,pathlib,sys',
 'import backend.server as service',
 'from backend.font_library import FontLibrary',
 'from tests.test_glyph_fallback import GlyphFallbackTests',
 'from tests.legacy_machine import TestController',
 'fixture=GlyphFallbackTests();fixture.setUp()',
 "app=service.Application(fixture.root,fixture.root/'jobs',controller=TestController())",
 'ids={p.stem:key for key,p in app.fonts.items()}',
 'data=json.loads(fixture.report.read_text())',
 "for item in data['fonts']:",
 " item['id']=ids[item['id']]",
 " item['fallback_rankings']=[[ids[key],distance,score] for key,distance,score in item['fallback_rankings']]",
 'fixture.report.write_text(json.dumps(data))',
 'app.font_library=FontLibrary(app.fonts,fixture.report)',
 'service.STATIC=pathlib.Path(sys.argv[1])',
 'server=service.create_server(app,port=0)',
 "print(json.dumps(dict(port=server.server_port,temp=str(fixture.root))),flush=True)",
 'server.serve_forever()'
].join('\n');
const python=spawn('python',['-u','-c',source,ui],{cwd:root,windowsHide:true});
let browser,temp;
(async()=>{
 const info=await new Promise((resolve,reject)=>{
  let output='';python.stdout.on('data',chunk=>{output+=chunk;if(output.includes('\n'))resolve(JSON.parse(output.split('\n')[0]));});
  python.on('error',reject);python.on('exit',code=>reject(new Error('Fixture server exited '+code)));
 });temp=info.temp;
 browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1450,height:1100}}),errors=[],posts=[];
 page.on('pageerror',error=>errors.push(error.message));
 page.on('request',request=>{if(request.method()==='POST')posts.push(new URL(request.url()).pathname);});
 await page.goto('http://127.0.0.1:'+info.port);
 await page.selectOption('#layoutMode','notebook');
 // Use the real preview API, then mount the exact returned document through the normal page renderer.
 await page.evaluate(async()=>{
  const all=(await api('/api/fonts')).fonts;
  const a=all.find(f=>f.name==='a');
  documentResult=await api('/api/preview',{layout_mode:'notebook',font_mix:[{font_id:a.id,weight:1}],text:'A你B你',size:5,width:100,height:100,margin:10,rows:4,seed:'ui'});
  outputIndex=0;showOutputPage(0);
 });
 assert.equal(await page.locator('#paperView [data-fallback]').count(),3);
 assert.equal(await page.locator('#paperView [data-character="你"]').count(),2);
 assert.equal(await page.locator('#fontUsage .fallback-details li').count(),2);
 assert.match(await page.locator('#fontUsage').textContent(),/next.gfont/);
 assert.match(await page.locator('#fontUsage').textContent(),/橙色/);
 await page.click('#zoomPreview');
 assert.equal(await page.locator('#zoomCanvas [data-fallback]').count(),3);
 await page.keyboard.press('Escape');
 await page.locator('.paper-stage').screenshot({path:path.resolve(root,'docs/glyph-fallback-preview.png')});
 assert.deepEqual(errors,[]);
 assert.ok(posts.every(p=>['/api/coordinate-preview','/api/line-pitch','/api/font-previews','/api/preview'].includes(p)),posts.join(','));
 console.log('PASS: actual fallback SVG, source details, zoom preserves highlights, no machine actions');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
 if(browser)await browser.close();python.kill();
 await new Promise(resolve=>python.exitCode!==null?resolve():python.once('exit',resolve));
 if(temp){const target=path.resolve(temp),base=path.resolve(root,'tests/.testdata');assert.equal(path.dirname(target),base);fs.rmSync(target,{recursive:true,force:true});}
});
