const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const context=vm.createContext({window:{}});
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../frontend/preset-store.js'),'utf8'),context);
const Store=context.window.PresetStore;
const key='plotter.layout-presets.v1';
function storage(){const data=new Map();return {data,getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v)};}
(async()=>{
  const local=storage(),original=JSON.stringify({presets:[{id:'old',name:'test'}],selected:'old'});
  local.setItem(key,original);
  const groups={layout:{revision:1,presets:[{id:'imported',name:'test'}]},font:{revision:0,presets:[]},grid:{revision:0,presets:[]}};
  let fail=false,calls=[];
  const api=async(path,data)=>{
    calls.push({path,data});
    if(fail)throw new Error('offline');
    if(path.endsWith('/migrate'))return {groups:structuredClone(groups),selected:{layout:'imported'},imported:1};
    if(data){assert.equal(data.revision,groups[data.kind].revision);groups[data.kind]={revision:data.revision+1,presets:data.presets};}
    return {groups:structuredClone(groups)};
  };
  const store=new Store(api,local);await store.init();
  assert.equal(store.read(key).selected,'imported');assert.equal(local.getItem(key),original);
  await store.save(key,[{id:'new',name:'new'}],'new');
  assert.equal(store.read(key).presets[0].id,'new');assert.equal(local.getItem(key),original);
  const count=calls.length;store.selection(key,'other');assert.equal(calls.length,count);
  fail=true;
  await assert.rejects(()=>store.save(key,[],'none'),/offline/);
  assert.equal(store.read(key).presets.length,1);assert.equal(store.pending,false);
  assert.equal(store.read(key).selected,'other');
  const broken=storage();broken.setItem(key,'bad json');
  const empty=new Store(async()=>({groups}),broken);await empty.init();
  assert.equal(empty.read(key).presets[0].id,'new');
  const blocked=new Store(api,local);await assert.rejects(()=>blocked.init(),/offline/);
  await assert.rejects(()=>blocked.save(key,[],'none'),/服务器预设尚未载入/);
  console.log('PASS: server authority, migration backup, mapped selection, failed writes and storage recovery');
})().catch(error=>{console.error(error);process.exitCode=1;});
