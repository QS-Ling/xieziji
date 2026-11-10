const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const context=vm.createContext({window:{}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/notebook-sizing.js'),'utf8'),context);
const compute=context.window.NotebookSizing.compute;
const values={height:100,marginTop:10,marginBottom:10,rows:4,size:5,latinSize:5};
let result=compute(values,'rows',2);
assert.equal(result.rows,4);assert.equal(result.size,10);assert.equal(result.pitch,20);
result=compute(values,'rows',4);assert.equal(result.rows,4);assert.equal(result.size,5);
result=compute(values,'size',2);assert.equal(result.rows,8);assert.equal(result.size,5);
result=compute(values,'size',3);assert.equal(result.rows,5);assert.equal(result.pitch,15);
assert.throws(()=>compute({...values,rows:200},'rows',4));
assert.throws(()=>compute({...values,size:20,height:50},'size',4));
assert.throws(()=>compute(values,'other',2));
assert.throws(()=>compute(values,'rows',NaN));
const elements=new Map();
function $(id){
  if(!elements.has(id)){
    const label={firstChild:{textContent:''}};
    elements.set(id,{value:'',title:'',readOnly:false,closest:()=>label});
  }
  return elements.get(id);
}
Object.assign(context,{$,layoutMode:'notebook',currentLayout:()=>Object.fromEntries(Object.entries(values).map(([k,v])=>[k,Number($(k).value||v)]))});
for(const [key,value] of Object.entries(values))$(key).value=value;
const app=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8');
vm.runInContext(app.slice(app.indexOf('function allowOverlap()'),app.indexOf('function coordinateChanged()')),context);
vm.runInContext('restoreNotebookSizing({values:currentLayout()})',context);
assert.equal($('lineSizing').value,'rows');assert.equal($('size').readOnly,true);assert.equal($('rows').readOnly,false);
vm.runInContext("restoreNotebookSizing({values:currentLayout(),lineSizing:'size',lineLooseness:2})",context);
assert.equal($('size').readOnly,false);assert.equal($('rows').readOnly,true);assert.equal($('rows').value,8);
context.layoutMode='grid';vm.runInContext('syncNotebookSizing()',context);
assert.equal($('rows').readOnly,false);assert.equal($('size').readOnly,false);
console.log('PASS: linked row/height sizing, looseness, rounding, invalid geometry');
