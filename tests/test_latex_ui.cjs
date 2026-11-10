// Real fonts and production markup; verify actual page coordinates and cached bytes.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),artifacts=path.resolve(root,'../analysis/deployment');
const jobs=path.resolve(root,'tests/.testdata/latex-ui-'+process.pid);
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
  selectedFonts=[2,3,4].map(n=>({font_id:fonts.find(f=>f.name===`blood8真迹${n}_kvenjoy_blood8`).id,weight:1,scope:'all'}));renderFontMix();
  const text=String.raw`矩阵与行列式
$$\begin{pmatrix} a & b \\ c & d \end{pmatrix}\quad\det A=ad-bc$$
分段函数
$$f(x)=\begin{cases}\sqrt[3]{x}&x\ge0\\-\sqrt{-x}&x<0\end{cases}$$
多行对齐
$$\begin{aligned}y&=\frac{x+1}{2}\\z&=\left[\frac{a}{b}\right]^2\end{aligned}$$
算子上下限与向量
$$\sum_{i=1}^n i=\frac{n(n+1)}{2}\quad\vec{F}=m\vec{a}$$
集合与逻辑
$$\forall x\in A,\quad A\subseteq B\Rightarrow x\in B$$
注释与重音
$$\underbrace{a+\cdots+a}_{n}=na\quad\hat{x},\dot{x},\ddot{x}$$`;
  const settings={...paperSettings(),layout_mode:'notebook',line_placement:'ink',line_sizing:'size',line_looseness:1,size:4.2,latin_size:4.2,width:170,height:220,margin_top:10,margin_bottom:10,margin_left:10,margin_right:10,font_mix:selectedFonts,seed:'latex-extended',smart_balance:true,humanization:{enabled:false}};
  documentResult=await api('/api/preview',{...settings,text});outputIndex=0;showOutputPage(0);
  const repeat=await api('/api/preview',{...settings,text});
  const first=await (await request('/api/jobs/'+documentResult.pages[0].job_id+'/gcode')).text();
  const again=await (await request('/api/jobs/'+repeat.pages[0].job_id+'/gcode')).text();
  const grid=await api('/api/preview',{...settings,layout_mode:'grid',rows:6,grid:{columns:10},text:String.raw`A$\begin{bmatrix}a&b\\c&d\end{bmatrix}$B`});
  let invalid;
  try{await api('/api/preview',{...settings,text:String.raw`$\begin{matrix}a\end{cases}$`})}catch(e){invalid=e.message}
  return {document:documentResult,grid,identical:first===again,gcode:first,invalid};
 });
 assert(result.identical);assert.equal(result.document.page_count,1);assert.match(result.invalid,/不匹配/);
 assert.equal(result.document.pages[0].metadata.formula_count,6);assert.equal(result.grid.pages[0].metadata.formula_count,1);
 for(const p of [...result.document.pages,...result.grid.pages]){
  const m=p.metadata,b=m.bounds;assert(b[0]>=9.999&&b[1]>=9.999&&b[2]<=160.001&&b[3]<=210.001);
  for(const group of m.repeat_distribution.groups)assert.equal(group.used_fonts,Math.min(group.occurrences,group.available_fonts));
  if(m.line_layout)for(let i=1;i<m.line_layout.length;i++){const a=m.line_layout[i-1],b=m.line_layout[i];assert(b.top_mm-a.bottom_mm>=b.safety_gap_mm-.001)}
 }
 await page.click('#zoomPreview');await page.locator('#zoomStage').screenshot({path:path.resolve(root,'docs/latex-preview.png')});await page.keyboard.press('Escape');
 const detail=await browser.newPage({viewport:{width:1200,height:1500}});
 await detail.setContent(result.document.pages[0].svg);
 await detail.evaluate(()=>{const svg=document.querySelector('svg'),ink=svg.querySelector('#writing-paths'),b=ink.getBBox();
 const clone=ink.cloneNode(true);svg.replaceChildren(clone);svg.setAttribute('viewBox',`${b.x-2} ${b.y-2} ${b.width+4} ${b.height+4}`);
 svg.setAttribute('width','900');svg.setAttribute('height',String(900*(b.height+4)/(b.width+4)));document.body.style.margin='0';document.body.style.background='white'});
 await detail.locator('svg').screenshot({path:path.resolve(root,'docs/latex-preview.png')});await detail.close();
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.deepEqual(errors,[]);assert(posts.every(p=>['/api/font-previews','/api/preview','/api/coordinate-preview','/api/line-pitch'].includes(p)),posts.join(','));
 const saved={passed:true,pages:result.document.page_count,formula_count:6,cached_bytes_identical:result.identical,grid:true,mixed_fonts:true,bounds_safe:true,invalid_rejected:true,errors,no_machine_actions:true};
 fs.writeFileSync(path.resolve(artifacts,'latex-ui.json'),JSON.stringify(saved,null,2));console.log(JSON.stringify(saved));
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{
 if(browser)await browser.close();python.kill();await new Promise(resolve=>python.exitCode!==null?resolve():python.once('exit',resolve));
 assert.equal(path.dirname(jobs),path.resolve(root,'tests/.testdata'));fs.rmSync(jobs,{recursive:true,force:true});
});
