// Exercise actual production markup, real fonts, persisted controls and preview APIs.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),artifacts=path.resolve(root,'../analysis/deployment');
const ui=process.env.PLOTTER_TEST_UI||path.resolve(artifacts,'glyph-fallback-ui/frontend');
const jobs=path.resolve(root,'tests/.testdata/balance-ui-'+process.pid);
const python=spawn('python',['-u','-c',[
 'import pathlib,sys', 'import backend.server as service',
 'from tests.legacy_machine import TestController',
 'service.STATIC=pathlib.Path(sys.argv[1])',
 'app=service.Application(sys.argv[2],sys.argv[3],controller=TestController())',
 'server=service.create_server(app,port=0)', 'print(server.server_port,flush=True)', 'server.serve_forever()'
].join('\n'),ui,path.resolve(root,'../gcodeFonts'),jobs],{cwd:root,windowsHide:true});
let browser;
(async()=>{
 const port=await new Promise((resolve,reject)=>{let s='';python.stdout.on('data',d=>{s+=d;if(s.includes('\n'))resolve(Number(s.trim()))});python.on('error',reject);python.on('exit',code=>reject(new Error('Server exited '+code)))});
 browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[],posts=[];
 page.on('pageerror',e=>{errors.push(e.message);console.error('Browser:',e.stack)});page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname)});
 page.on('requestfailed',r=>console.error('Request failed:',r.url(),r.failure()));
 page.on('response',r=>{if(r.status()>=400)console.error('HTTP:',r.status(),r.url())});
 await page.goto('http://127.0.0.1:'+port);await page.waitForFunction(()=>fonts.length>0);await page.selectOption('#layoutMode','notebook');
 await page.evaluate(()=>{$('layoutSettings').open=true;});
 assert.equal(await page.isChecked('#smartBalance'),false);assert.equal(await page.isDisabled('#letterScale'),true);
 await page.check('#smartBalance');await page.fill('#letterScale','120');await page.fill('#digitScale','80');
 assert.equal(await page.inputValue('#letterScaleSlider'),'120');assert.equal(await page.inputValue('#digitScaleSlider'),'80');
 assert.deepEqual(await page.evaluate(()=>{const p=paperSettings();return [p.smart_balance,p.letter_scale,p.digit_scale]}),[true,120,80]);
 await page.fill('#presetName','英数均衡测试');await page.evaluate(()=>saveLayoutPreset());
 await page.waitForTimeout(500);await page.reload();await page.waitForFunction(()=>typeof fonts!=='undefined'&&fonts.length>0).catch(async e=>{console.error(await page.content());throw e});
 assert.equal(await page.isChecked('#smartBalance'),true);assert.equal(await page.inputValue('#letterScale'),'120');assert.equal(await page.inputValue('#digitScale'),'80');
 await page.selectOption('#layoutMode','grid');assert.equal(await page.isChecked('#smartBalance'),false);
 await page.selectOption('#layoutMode','notebook');assert.equal(await page.isChecked('#smartBalance'),true);
 const exported=await page.evaluate(async()=>{let result;const old=saveBlob;saveBlob=async(blob)=>{result=JSON.parse(await blob.text())};$('exportDocument').click();await new Promise(r=>setTimeout(r,20));saveBlob=old;return result});
 assert.equal(exported.modeDrafts.notebook.smartBalance,true);assert.equal(exported.modeDrafts.notebook.letterScale,120);
 await page.evaluate(()=>{$('smartBalance').checked=false;$('smartBalance').dispatchEvent(new Event('change'))});
 await page.setInputFiles('#documentFile',{name:'balance.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(exported))});
 await page.waitForFunction(()=>$('smartBalance').checked&&Number($('digitScale').value)===80);
 const results=await page.evaluate(async()=>{
  const font=fonts.find(f=>f.name==='blood8真迹4_kvenjoy_blood8');if(!font)throw new Error('Real font missing');
  const base={...paperSettings(),line_sizing:'size',line_looseness:1,size:5,latin_size:5,width:160,height:160,margin_top:10,margin_bottom:10,margin_left:10,margin_right:10,font_mix:[{font_id:font.id,weight:1}],seed:'balance-ui',letter_scale:100,digit_scale:100};
  const sizes={};
  for(const char of ['A','1','a']){
   const old=(await api('/api/preview',{...base,text:char,smart_balance:false})).pages[0];
   const next=(await api('/api/preview',{...base,text:char,smart_balance:true})).pages[0];
   const height=p=>p.metadata.bounds[3]-p.metadata.bounds[1];
   sizes[char]={ratio:height(next)/height(old),calibration:next.metadata.font_balance.fonts[0]};
  }
  documentResult=await api('/api/preview',{...base,smart_balance:true,text:'中文字形与英数大小均衡\nEnglish ABC abc 0123456789\n光功率 P1 = 20 mW，损耗 0.5 dB\n$$\\alpha=-10\\log\\frac{P_2}{P_1}$$\n记录实验结果，计算平均值。'});
  outputIndex=0;showOutputPage(0);return {sizes,document:documentResult};
 });
 for(const char of ['A','1','a']){const item=results.sizes[char],group=char==='1'?'digits':'letters';assert(Math.abs(item.ratio-item.calibration[group].scale)<.002);}
 for(const p of results.document.pages){const rows=p.metadata.line_layout;for(let i=1;i<rows.length;i++)assert(rows[i].top_mm-rows[i-1].bottom_mm>=rows[i].safety_gap_mm-.001);}
 assert.match(await page.textContent('#fontUsage'),/英数实际缩放/);
 await page.evaluate(()=>{$('layoutSettings').open=true});await page.locator('.font-balance').screenshot({path:path.resolve(artifacts,'font-balance-controls.png')});
 await page.click('#zoomPreview');await page.locator('#zoomStage').screenshot({path:path.resolve(root,'docs/font-balance-preview.png')});await page.keyboard.press('Escape');
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.deepEqual(errors,[]);assert(posts.every(p=>['/api/font-previews','/api/preview','/api/coordinate-preview','/api/line-pitch'].includes(p)),posts.join(','));
 fs.writeFileSync(path.resolve(artifacts,'font-balance-ui.json'),JSON.stringify({passed:true,sizes:results.sizes,errors,no_machine_actions:true},null,2));
 console.log('PASS: real per-font calibration, independent controls, preset reload, mode drafts, document round trip, formula safety, responsive controls; no machine actions');
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{
 if(browser)await browser.close();python.kill();await new Promise(resolve=>python.exitCode!==null?resolve():python.once('exit',resolve));
 assert.equal(path.dirname(jobs),path.resolve(root,'tests/.testdata'));fs.rmSync(jobs,{recursive:true,force:true});
});
