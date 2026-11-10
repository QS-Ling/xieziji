// Real browser + real vector font API; pass PLOTTER_TEST_FONT_DIR for the analyzed library.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const jobs=path.resolve(root,'tests/.testdata/font-ui-'+process.pid);
assert.equal(path.dirname(jobs),path.resolve(root,'tests/.testdata'));
const python=spawn(process.env.PYTHON||'python',['-u','-c',[
  'import sys',
  'from backend.server import Application,create_server',
  'from tests.legacy_machine import TestController',
  'app=Application(sys.argv[1],sys.argv[2],controller=TestController())',
  'server=create_server(app,port=0)',
  'print(server.server_port,flush=True)',
  'server.serve_forever()'
].join('\n'),process.env.PLOTTER_TEST_FONT_DIR||path.resolve(root,'../gcodeFonts'),jobs],{cwd:root,windowsHide:true});
let browser;
(async()=>{
  const port=await new Promise((resolve,reject)=>{
    let output='';python.stdout.on('data',data=>{output+=data;if(/^\d+\r?\n/.test(output))resolve(Number(output.trim()));});
    python.on('error',reject);python.on('exit',code=>reject(new Error('Test server exited: '+code)));
  });
  browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'msedge'});
  const page=await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[],requests=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if(request.method()==='POST')requests.push(new URL(request.url()).pathname);});
  await page.goto('http://127.0.0.1:'+port);
  await page.waitForFunction(()=>window.sharedWorkspace?.ready);
  await page.selectOption('#layoutMode','notebook');
  assert.equal(await page.locator('#fontDialog').isVisible(),false);
  await page.locator('#fontSettings>summary').click();
  await page.click('#chooseFonts');
  assert.equal(await page.locator('#fontDialog').isVisible(),true);
  await page.waitForFunction(()=>document.querySelectorAll('#fontGallery svg').length===6);
  await page.waitForFunction(()=>document.querySelectorAll('#fontRecommendation option').length>=7);
  await page.waitForFunction(()=>document.querySelector('#fontMix [data-speed-score]'));
  assert.match(await page.locator('#fontSpeedHint').textContent(),/100.*中位/);
  assert.deepEqual(await page.locator('#fontDialog h3').allTextContents(),['搜索字体','字体排序','字体列表','当前字体的预览','字形推荐']);
  assert.ok((await page.locator('#fontGallery [data-preview-text="永"]').count())===6);
  await page.selectOption('#fontSort','glyphs');
  const counts=await page.locator('#fontGallery article').evaluateAll(nodes=>nodes.map(n=>Number(n.dataset.glyphCount)));
  assert.deepEqual(counts,[...counts].sort((a,b)=>b-a));
  assert.equal(await page.locator('#fontNext').isEnabled(),true);
  await page.selectOption('#fontSort','similarity');
  const current=await page.inputValue('#font');
  const expectedNearest=await page.evaluate(async id=>{
    const catalog=await(await fetch('/api/font-recommendations')).json();
    return catalog.fonts[id].nearest.filter(n=>n.font_id!==id).sort((a,b)=>b.score-a.score).slice(0,6).map(n=>n.font_id);
  },current);
  assert.deepEqual(await page.locator('#fontGallery article').evaluateAll(nodes=>nodes.map(n=>n.dataset.fontId)),expectedNearest);
  assert.equal(await page.locator('#fontNext').isDisabled(),true);
  const similarScores=await page.locator('#fontGallery [data-similarity-score]').evaluateAll(nodes=>nodes.map(n=>Number(n.dataset.similarityScore)));
  assert.deepEqual(similarScores,[...similarScores].sort((a,b)=>b-a));
  await page.fill('#fontSearch','__no_matching_font__');
  assert.equal(await page.inputValue('#font'),current);
  assert.equal(await page.locator('#fontGallery article').count(),0);
  await page.fill('#fontSearch','');
  await page.locator('#fontSimilarList button').first().click();
  const rebased=await page.inputValue('#font');
  assert.notEqual(rebased,current);
  assert.ok(!(await page.locator('#fontGallery article').evaluateAll(nodes=>nodes.map(n=>n.dataset.fontId))).includes(rebased));
  await page.waitForFunction(()=>document.querySelectorAll('#fontGallery svg').length===6&&document.querySelector('#fontFocus svg'));
  await page.locator('#fontDialog').screenshot({path:path.join(jobs,'font-chooser-desktop.png')});
  await page.selectOption('#fontSort','speed');
  await page.waitForFunction(()=>document.querySelectorAll('#fontGallery [data-speed-score]').length===6);
  const speedScores=await page.locator('#fontGallery [data-speed-score]').evaluateAll(nodes=>nodes.map(n=>Number(n.dataset.speedScore)));
  assert.deepEqual(speedScores,[...speedScores].sort((a,b)=>b-a));
  await page.selectOption('#fontSort','name');
  assert.equal(await page.locator('#fontMix svg').count(),1);
  await page.fill('#fontSearch','blood8真迹');
  await page.waitForFunction(()=>[...document.querySelectorAll('#fontGallery .font-card-name')].every(n=>n.textContent.includes('blood8真迹')));
  assert.equal(await page.locator('#fontGallery article').count(),6);
  const searchPreview=page.locator('#fontGallery article').filter({has:page.locator('.font-card-preview[aria-pressed="false"]')}).first();
  const previewId=await searchPreview.getAttribute('data-font-id');
  const previewCard=page.locator(`#fontGallery article[data-font-id="${previewId}"]`);
  const beforePreviewCount=await page.locator('#fontMix .font-mix-row').count();
  await searchPreview.locator('.font-card-preview').click();
  await page.waitForFunction(id=>document.querySelector('#font').value===id&&document.querySelector('#fontFocus [data-font-preview]')?.dataset.fontPreview===id&&document.querySelector('#fontFocus svg'),previewId);
  assert.equal(await previewCard.locator('.font-card-preview').textContent(),'预览中');
  assert.equal(await page.locator('#fontMix .font-mix-row').count(),beforePreviewCount);
  assert.ok((await page.locator('#fontFocus .font-card-name').textContent()).includes(await previewCard.locator('.font-card-name').textContent()));
  const first=await page.locator('#fontGallery .font-card-name').first().textContent();
  await page.click('#fontNext');
  assert.notEqual(await page.locator('#fontGallery .font-card-name').first().textContent(),first);
  await page.locator('#fontGallery .font-card-add').first().click();
  assert.equal(await page.locator('#fontMix .font-mix-row').count(),2);
  await page.fill('#fontSampleText','AB😀');
  await page.waitForFunction(()=>document.querySelector('#fontFocus .font-missing')?.textContent.includes('😀'));
  // Hold a previous response to verify it cannot overwrite samples for newer text.
  await page.route('**/api/font-previews',async route=>{
    if(route.request().postDataJSON().text==='永')await new Promise(resolve=>setTimeout(resolve,500));
    await route.continue();
  });
  const previous=page.waitForRequest(request=>request.url().endsWith('/api/font-previews')&&request.postDataJSON()?.text==='永');
  await page.fill('#fontSampleText','永');await previous;
  const latest=page.waitForResponse(response=>response.url().endsWith('/api/font-previews')&&response.request().postDataJSON()?.text==='国');
  await page.fill('#fontSampleText','国');await latest;
  const expected=await page.evaluate(async()=>{
    const font_id=document.querySelector('#font').value;
    return (await (await fetch('/api/font-previews',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({font_ids:[font_id],text:'国'})})).json()).previews[0].svg;
  });
  await page.waitForTimeout(700);
  assert.equal(await page.locator('#fontFocus svg').getAttribute('viewBox'),expected.match(/viewBox="([^"]+)"/)[1]);
  assert.equal(await page.locator('#fontFocus polyline').first().getAttribute('points'),expected.match(/polyline points="([^"]+)"/)[1]);
  const saved=await page.evaluate(()=>localStorage.getItem('plotter.font-presets.v1'));
  await page.locator('.font-combination-details>summary').click();
  await page.click('#applyFontRecommendation');
  assert.deepEqual(await page.locator('#fontMix input').evaluateAll(nodes=>nodes.map(n=>Number(n.value))),[60,25,15]);
  assert.equal(await page.evaluate(()=>localStorage.getItem('plotter.font-presets.v1')),saved);
  assert.equal(await page.inputValue('#fontPresetName'),'blood8 真迹 · 自然微差');
  await page.fill('#fontSampleText','春风十里山水清音');
  await page.waitForFunction(()=>document.querySelectorAll('#fontRecommendationPreview svg').length===3&&[...document.querySelectorAll('#fontRecommendationPreview [data-font-preview]')].every(n=>n.dataset.sampleText==='春风十里山水清音'));
  await page.locator('.font-recommendations').screenshot({path:path.resolve(root,'docs/font-browser-preview.png')});
  await page.setViewportSize({width:390,height:844});
  await page.waitForFunction(()=>!document.querySelector('#fontPreviewPanel').open);
  assert.ok(await page.locator('#fontDialog').evaluate(n=>n.scrollWidth<=n.clientWidth+1));
  assert.ok(await page.locator('.font-dialog-body').evaluate(n=>n.scrollWidth<=n.clientWidth+1));
  await page.locator('#fontPreviewPanel>summary').click();
  assert.equal(await page.locator('#fontPreviewPanel').getAttribute('open'),'');
  await page.locator('#fontPreviewPanel>summary').click();
  await page.locator('#fontDialog').screenshot({path:path.join(jobs,'font-chooser-mobile.png')});
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#fontDialog').isVisible(),false);
  assert.equal(await page.locator(':focus').getAttribute('id'),'chooseFonts');
  assert.deepEqual(errors,[]);
  assert.ok(requests.every(p=>['/api/font-previews','/api/coordinate-preview'].includes(p)||p.startsWith('/api/workspaces/')||p==='/api/line-pitch'),requests.join(', '));
  console.log('PASS: five sections, glyph/speed sorts with paging, exact nearest six, stable search reference, single glyph samples, desktop/mobile, actual SVG, 60/25/15 apply and no machine actions');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();
  python.kill();
  await new Promise(resolve=>python.exitCode!==null?resolve():python.once('exit',resolve));
  fs.rmSync(jobs,{recursive:true,force:true});
});
