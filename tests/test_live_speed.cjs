// Isolated frontend state tests. No browser, HTTP, or hardware connection.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../frontend/app.js'), 'utf8');
const controls = new Map();
const element = id => {
  if (!controls.has(id)) controls.set(id, {value:100, addEventListener(){}});
  return controls.get(id);
};
const context = vm.createContext({$, state:null});
function $(id){return element(id);}
Object.assign(context, {setTimeout:()=>1, clearTimeout(){}, notice(){}});
vm.runInContext(`let speedTimer,speedPending=null,speedSending=false,speedJob=null,actionRevision=0;`,context);
vm.runInContext(source.slice(source.indexOf('function writing()'),source.indexOf('function renderState()')),context);
vm.runInContext('function renderState(){renderSpeed();}',context);
function run(code){return vm.runInContext(code,context);}
async function main(){
  context.state={connected:true,phase:'paused',job_id:'a',feed_override:100,feed_override_requested:100,speed_max_percent:125};
  run('renderSpeed();queueSpeed(180)');
  assert.equal(run('speedPending'),125);
  assert.equal(element('liveSpeedValue').textContent,'125%');
  let resolve;
  context.api=async(path,data)=>{
    assert.equal(path,'/api/speed');assert.equal(data.job_id,'a');assert.equal(data.percent,125);
    return new Promise(done=>{resolve=done;});
  };
  const sending=run('sendSpeed()');
  run('queueSpeed(80)');
  resolve({...context.state,feed_override_requested:125});await sending;
  assert.equal(run('speedPending'),80,'A newer drag must survive an in-flight request');
  context.api=async()=>new Promise(done=>{resolve=done;});
  const stale=run('sendSpeed()');
  context.state={...context.state,phase:'stopping'};run('actionRevision++');
  resolve({...context.state,phase:'paused',feed_override_requested:80});await stale;
  assert.equal(context.state.phase,'stopping','A speed reply must not undo a stop');
  assert.equal(element('liveSpeed').disabled,true);
  assert.equal(run('speedPending'),null);
  context.state={connected:false,phase:'idle'};run('renderSpeed()');
  assert.equal(element('resetSpeed').disabled,true);
  console.log('PASS: speed bounds, latest drag, stop race, disconnected controls');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
