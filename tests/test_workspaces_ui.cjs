// Isolated browser contexts and simulated controller; no real device actions.
const assert=require('node:assert/strict'),path=require('node:path');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),jobs=path.join(root,'tests/.testdata/workspaces-ui-'+process.pid);
const python=spawn('python',['-u','-c',[
 'import sys','from backend.server import Application,create_server',
 'from tests.legacy_machine import TestController',
 'app=Application(sys.argv[1],sys.argv[2],controller=TestController())',
 'server=create_server(app,port=0)','print(server.server_port,flush=True)','server.serve_forever()'
].join('\n'),path.join(root,'tests/fixtures'),jobs],{cwd:root,windowsHide:true});
let browser;
(async()=>{
 const port=await new Promise((resolve,reject)=>{let s='';python.stdout.on('data',d=>{s+=d;if(s.includes('\n'))resolve(Number(s.trim()))});python.on('error',reject);python.on('exit',c=>reject(new Error('server exited '+c)))});
 browser=await chromium.launch({channel:'msedge',headless:true});
 const desktop=await browser.newContext(),mobile=await browser.newContext({viewport:{width:390,height:844}});
 const a=await desktop.newPage(),b=await mobile.newPage(),errors=[],posts=[];
 for(const p of [a,b]){p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname)});}
 const base='http://127.0.0.1:'+port;
 const ready=async p=>p.waitForFunction(()=>window.sharedWorkspace?.ready&&!busy);
 await a.goto(base);await ready(a);await b.goto(base);await ready(b);
 await a.selectOption('#layoutMode','grid');await a.fill('#text','AB');
 await b.waitForFunction(()=>$('text').value==='AB'&&layoutMode==='grid');
 await a.evaluate(async()=>{await sharedWorkspace.save();});
 await a.click('#preview');await a.waitForFunction(()=>!busy&&!!documentResult);
 const original=await a.evaluate(()=>({id:documentResult.document_id,svg:documentResult.pages[0].svg,job:currentJob}));
 await b.waitForFunction(id=>documentResult?.document_id===id,original.id);
 assert.equal(await b.evaluate(()=>documentResult.pages[0].svg),original.svg);
 assert.equal(await b.evaluate(()=>currentJob),original.job);
 const count=posts.filter(p=>p==='/api/preview').length;
 await a.reload();await ready(a);
 assert.equal(await a.inputValue('#text'),'AB');
 assert.equal(await a.evaluate(()=>documentResult.document_id),original.id);
 assert.equal(await a.evaluate(()=>documentResult.pages[0].svg),original.svg);
 assert.equal(posts.filter(p=>p==='/api/preview').length,count);
 await b.fill('#text','BA');await a.waitForFunction(()=>$('text').value==='BA');
 assert.equal(await a.evaluate(()=>documentResult),null);
 await b.reload();await ready(b);assert.equal(await b.inputValue('#text'),'BA');
 // A separate controller port has an independent workspace, and reset is shared.
 const key=await a.evaluate(()=>profilePort||'default');
 const primary=await (await desktop.request.get(base+'/api/workspaces/'+encodeURIComponent(key))).json();
 const other=await desktop.request.post(base+'/api/workspaces/SECOND',{data:{revision:0,draft:{...primary.draft,pages:['SECOND']}}});assert(other.ok());
 await a.click('#refreshInterface');await a.waitForFunction(()=>!busy&&$('text').value==='');
 await b.waitForFunction(()=>$('text').value===''&&layoutMode==='');
 const second=await (await desktop.request.get(base+'/api/workspaces/SECOND')).json();assert.deepEqual(second.draft.pages,['SECOND']);
 await a.reload();await ready(a);assert.equal(await a.inputValue('#text'),'');
 assert.deepEqual(errors,[]);
 assert(!posts.some(p=>/\/api\/(start|connect|jog|pen|stop|disconnect)$/.test(p)));
 console.log('PASS: desktop/mobile bidirectional draft and SVG sync, reload retains exact output, edit invalidates preview, explicit shared reset, device isolation, no machine commands');
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{if(browser)await browser.close();python.kill();});
