// Real fonts and production markup; verify actual page coordinates and cached bytes.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),artifacts=path.resolve(root,'../analysis/deployment');
const jobs=path.resolve(root,'tests/.testdata/repeat-ui-'+process.pid);
const python=spawn('python',['-u','-c',[
 'import pathlib,sys','import backend.server as service','from tests.legacy_machine import TestController',
 'service.STATIC=pathlib.Path(sys.argv[1])',
 'app=service.Application(sys.argv[2],sys.argv[3],controller=TestController())',
 'server=service.create_server(app,port=0)','print(server.server_port,flush=True)','server.serve_forever()'
].join('\n'),path.resolve(artifacts,'glyph-fallback-ui/frontend'),path.resolve(root,'../gcodeFonts'),jobs],{cwd:root,windowsHide:true});
let browser;
(async()=>{
 const port=await new Promise((resolve,reject)=>{let s='';python.stdout.on('data',d=>{s+=d;if(s.includes('\n'))resolve(Number(s.trim()))});python.on('error',reject);python.on('exit',code=>reject(new Error('Server exited '+code)))});
 browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[],posts=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname)});
 await page.goto('http://127.0.0.1:'+port);await page.waitForFunction(()=>typeof fonts!=='undefined'&&fonts.length>0);await page.selectOption('#layoutMode','notebook');
 const result=await page.evaluate(async()=>{
  selectedFonts=[2,3,4].map((n,i)=>{const font=fonts.find(f=>f.name===`blood8真迹${n}_kvenjoy_blood8`);if(!font)throw new Error('Font missing');return {font_id:font.id,weight:[100,25,15][i],scope:'all'}});renderFontMix();
  const settings={...paperSettings(),layout_mode:'notebook',line_placement:'ink',line_sizing:'size',line_looseness:1,size:5,latin_size:5,width:90,height:70,margin_top:8,margin_bottom:8,margin_left:8,margin_right:8,font_mix:selectedFonts,seed:'repeated-human',smart_balance:true,
   humanization:{enabled:true,vertical:.1,scale:3,rotation:1,spacing:.1,baseline:.1}};
  const text=('人人人，人生与人间。人与人相处，因人而异。\n').repeat(8)+'$P_1+P_1+P_1$';
  documentResult=await api('/api/preview',{...settings,text});outputIndex=0;showOutputPage(0);
  const repeat=await api('/api/preview',{...settings,text});
  const first=await (await request('/api/jobs/'+documentResult.pages[0].job_id+'/gcode')).text();
  const again=await (await request('/api/jobs/'+repeat.pages[0].job_id+'/gcode')).text();
  const grid=await api('/api/preview',{...settings,layout_mode:'grid',rows:2,grid:{columns:5},text:'人'.repeat(27)});
  return {document:documentResult,grid,identical:first===again,gcode:first};
 });
 assert(result.identical);assert(result.document.page_count>1);assert.equal(result.grid.page_count,3);
 for(const p of [...result.document.pages,...result.grid.pages]){
  const m=p.metadata;
  for(const group of m.repeat_distribution.groups)assert.equal(group.used_fonts,Math.min(group.occurrences,group.available_fonts),JSON.stringify(group));
  const ids=new Set(m.glyph_occurrences.map(item=>item.occurrence));assert.equal(ids.size,m.glyph_occurrences.length);
  for(const item of m.glyph_occurrences){assert(item.options.includes(item.font_id));assert(item.bounds[0]>=7.999&&item.bounds[1]>=7.999);assert(item.bounds[2]<=82.001&&item.bounds[3]<=62.001);}
 }
 assert.match(await page.textContent('#fontUsage'),/本页同字分散/);
 const view=await page.locator('#paperView [data-glyph="人"]').evaluateAll(nodes=>Array.from(new Set(nodes.map(n=>n.dataset.fontId))));assert.equal(view.length,3);
 await page.locator('#fontUsage details').first().evaluate(node=>node.open=true);await page.locator('#fontUsage').screenshot({path:path.resolve(artifacts,'repeat-fonts-ui-details.png')});
 await page.click('#zoomPreview');await page.locator('#zoomStage').screenshot({path:path.resolve(root,'docs/repeat-fonts-preview.png')});await page.keyboard.press('Escape');
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.deepEqual(errors,[]);assert(posts.every(p=>['/api/font-previews','/api/preview','/api/coordinate-preview','/api/line-pitch'].includes(p)),posts.join(','));
 const saved={passed:true,pages:result.document.page_count,gridPages:result.grid.page_count,groups:result.document.pages.map(p=>p.metadata.repeat_distribution.groups),cached_bytes_identical:result.identical,errors,no_machine_actions:true};
 fs.writeFileSync(path.resolve(artifacts,'repeat-fonts-ui.json'),JSON.stringify(saved,null,2));
 console.log(JSON.stringify(saved));
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{
 if(browser)await browser.close();python.kill();await new Promise(resolve=>python.exitCode!==null?resolve():python.once('exit',resolve));
 assert.equal(path.dirname(jobs),path.resolve(root,'tests/.testdata'));fs.rmSync(jobs,{recursive:true,force:true});
});
