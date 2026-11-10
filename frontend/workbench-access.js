'use strict';
window.WorkbenchAccess=(()=>{
  let status={required:true,mine:false,occupied:false},pending=false,ready=false,refreshEpoch=0;
  const panel=document.createElement('section');panel.className='workbench-access';panel.setAttribute('aria-label','AI 档口与共享工作台');
  panel.innerHTML='<div class="access-heading"><div><p class="eyebrow">YOUR WORKBENCH</p><h2>共享写字台，连接你的 AI。</h2><p id="accessStatus" role="status" aria-live="polite">正在检查工作台…</p></div><a class="secondary" href="/ai-help.html" target="_blank" rel="noopener">如何调用 AI ↗</a></div><div class="access-actions"><label>使用者名称<input id="accessName" maxlength="40" placeholder="例如：小林" autocomplete="nickname"></label><button id="claimWorkbench" class="primary" type="button">占用 AI 档口</button><button id="pairAI" class="secondary" type="button" hidden>连接我的 AI</button><button id="releaseWorkbench" class="secondary" type="button" hidden>退出 AI 占用</button><button id="emergencyStop" class="danger" type="button">紧急停止机器</button></div><details id="joinWorkbench"><summary>已在 AI 中领取？用网页配对码加入</summary><div class="access-actions"><label>网页配对码<input id="accessCode" maxlength="12" autocomplete="off" placeholder="输入 AI 提供的 12 位配对码"></label><button id="redeemWorkbench" class="secondary" type="button">加入我的工作台</button></div></details><div id="aiPairing" class="pairing-result" hidden><strong>把下面这段发给你的 AI</strong><textarea id="aiPairingPrompt" readonly rows="4" aria-label="AI 配对提示词"></textarea><button id="copyAIPrompt" class="text-button" type="button">复制配对提示词</button><p class="hint">配对码 5 分钟有效，仅能使用一次。退出 AI 占用后，本轮 AI 连接立即失效。</p></div><p id="accessError" class="access-error" role="alert" hidden></p><p class="hint">所有网页共用本机文档、预览和进度，可直接手动编辑。只有 AI 连接需要占用档口；退出不停止书写、不清空内容。</p>';
  document.querySelector('body > header').after(panel);
  const libraryPanel=document.createElement('div');libraryPanel.id='personalDocuments';libraryPanel.hidden=true;
  libraryPanel.innerHTML='<details><summary>本机共享文档 · 保存、载入与新建</summary><div class="access-actions"><label>保存名称<input id="personalTitle" maxlength="80" placeholder="例如：数学题与解答"></label><button id="savePersonalDocument" class="secondary" type="button">保存当前文档</button><button id="newPersonalDocument" class="text-button" type="button">新建空白文档</button></div><div class="access-actions"><label>已保存的共享文档<select id="personalDocumentList" aria-label="本机共享文档"></select></label><button id="loadPersonalDocument" class="secondary" type="button">载入文档</button><button id="refreshPersonalDocuments" class="text-button" type="button">刷新列表</button></div><p class="hint">载入或新建前会自动备份已有正文。同一台机器的文档库、预览和书写进度对所有网页共享。</p></details>';
  panel.append(libraryPanel);
  const browserPair=document.createElement('button');browserPair.id='pairBrowser';browserPair.className='text-button';browserPair.type='button';browserPair.textContent='连接另一网页管理 AI';browserPair.hidden=true;
  document.getElementById('pairAI').after(browserPair);
  const el=id=>document.getElementById(id);
  function storageKey(){return 'plotter.workbench.v1:'+((window.PLOTTER_API_BASE||location.origin).replace(/\/$/,''))+':'+controllerId;}
  function record(){try{return JSON.parse(localStorage.getItem(storageKey())||'{}');}catch{return {};}}
  function store(value){try{localStorage.setItem(storageKey(),JSON.stringify(value));}catch{throw new Error('浏览器无法保存使用凭证，请允许本站本地存储后重试');}}
  function headers(path=''){
    const saved=record(),result={};
    if(saved.profile_key)result['X-Workbench-Web']=saved.profile_key;
    if(path.startsWith('/api/workbench/')&&saved.key)result['X-Workbench-Key']=saved.key;
    return result;
  }
  function canEdit(){return ready;}
  function ownsSlot(){return ready&&status.mine&&status.role==='browser';}
  function render(){
    if(!ready)return;
    const mine=ownsSlot();
    libraryPanel.hidden=!status.required;
    el('accessStatus').textContent=!status.required?'当前为兼容测试模式':mine?`AI 档口由你占用 · ${status.owner_name} · 网页与进度仍共享`:status.occupied?`AI 档口：${status.owner_name} 正在使用 · 你仍可查看和编辑共享文档`:'AI 档口空闲 · 网页可直接查看、编辑和操作机器';
    el('claimWorkbench').hidden=mine;el('claimWorkbench').disabled=pending||status.occupied;
    el('accessName').disabled=pending||status.occupied;
    el('pairAI').hidden=!mine;el('releaseWorkbench').hidden=!mine;
    browserPair.hidden=!mine;browserPair.disabled=pending;
    el('pairAI').disabled=pending;el('releaseWorkbench').disabled=pending;
    el('redeemWorkbench').disabled=pending;el('joinWorkbench').hidden=mine;
    $('compose').inert=false;$('device').inert=false;$('paperView').inert=false;
    const reset=$('refreshInterface');if(reset)reset.disabled=false;
  }
  function clearView(){
    el('aiPairing').hidden=true;el('aiPairingPrompt').value='';
  }
  async function refresh(){
    const epoch=++refreshEpoch;
      const wasMine=ownsSlot(),oldSession=status.session_id,selected=controllerId;
      const next=await api('/api/workbench/status');
      if(selected!==controllerId||epoch!==refreshEpoch)return;
      status=next;ready=true;
      if(record().key&&!status.mine){store({...record(),key:''});clearView();}
      else if(wasMine&&oldSession!==status.session_id)clearView();
      if(!el('accessName').value)el('accessName').value=record().name||'';
      render();
  }
  async function perform(fn){
    if(pending)return;pending=true;el('accessError').hidden=true;render();
    try{await fn();}catch(error){el('accessError').textContent=error.message;el('accessError').hidden=false;}
    finally{pending=false;render();}
  }
  async function accept(result){
    if(result.role!=='browser')throw new Error('此码用于 AI，请让 AI 生成“网页配对码”后再加入');
    const previous=record();store({...previous,key:result.key,profile_key:result.profile_key||previous.profile_key,name:result.owner_name});
    status=result;ready=true;clearView();render();
    if(!window.sharedWorkspace?.ready)await load();await refreshLibrary();
  }
  el('claimWorkbench').onclick=()=>perform(async()=>{
    const previous=record();
    await accept(await api('/api/workbench/claim',{name:el('accessName').value.trim(),profile_key:previous.profile_key||'',role:'browser'}));
  });
  el('redeemWorkbench').onclick=()=>perform(async()=>accept(await api('/api/workbench/redeem',{code:el('accessCode').value.trim(),kind:'browser'})));
  el('pairAI').onclick=()=>perform(async()=>{
    await window.sharedWorkspace?.save();
    const result=await api('/api/workbench/pair',{kind:'ai'});
    const base=(window.PLOTTER_API_BASE||location.origin).replace(/\/$/,'');
    el('aiPairingPrompt').value=`请使用写字机 MCP，连接业务服务 ${base}，调用 pair_workbench，controller="${controllerId}"，code="${result.code}"。当前网页设备为 ${profilePort||'default'}。连接后先读取当前文档；把我要求的内容写入，按预览调整。未经我要求不要改正文事实。`;
    el('aiPairing').hidden=false;
  });
  browserPair.onclick=()=>perform(async()=>{
    const result=await api('/api/workbench/pair',{kind:'browser'});
    el('aiPairingPrompt').value=`网页配对码：${result.code}\n在另一浏览器打开同一写字台，展开“已在 AI 中领取？用网页配对码加入”，输入此码。加入后可管理同一轮 AI 档口；共享文档不受影响。5 分钟内有效。`;
    el('aiPairing').hidden=false;
  });
  el('copyAIPrompt').onclick=()=>perform(async()=>{
    if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(el('aiPairingPrompt').value);
    else{el('aiPairingPrompt').focus();el('aiPairingPrompt').select();if(!document.execCommand('copy'))throw new Error('请选中文本手动复制');}
    notice('配对提示词已复制');
  });
  el('releaseWorkbench').onclick=()=>perform(async()=>{
    await api('/api/workbench/release',{});
    store({...record(),key:''});status={required:true,mine:false,occupied:false};clearView();await refresh();
  });
  el('emergencyStop').onclick=()=>perform(async()=>{state=await api('/api/stop',{});renderState();notice('已请求终止机器动作，请等待停稳');});
  async function refreshLibrary(){
    if(!canEdit()||!status.required)return;
    const result=await api('/api/library'),select=el('personalDocumentList'),selected=select.value;
    select.replaceChildren();
    for(const item of result.documents){const option=document.createElement('option');option.value=item.id;option.textContent=item.title+' · '+new Date(item.saved_at*1000).toLocaleString();select.append(option);}
    if([...select.options].some(o=>o.value===selected))select.value=selected;
    el('loadPersonalDocument').disabled=!result.documents.length;
  }
  async function currentDocument(){await window.sharedWorkspace.save();return api('/api/workspaces/'+encodeURIComponent(profilePort||'default'));}
  el('savePersonalDocument').onclick=()=>perform(async()=>{
    const current=await currentDocument();await api('/api/library/save',{device:profilePort||'default',expected_revision:current.revision,title:el('personalTitle').value});
    await refreshLibrary();notice('已保存到本机共享文档');
  });
  async function switchDocument(path,extra={}){
    const current=await currentDocument();
    await api(path,{device:profilePort||'default',expected_revision:current.revision,...extra});
    window.sharedWorkspace.detach();await window.sharedWorkspace.open(profilePort);await refreshLibrary();
  }
  el('loadPersonalDocument').onclick=()=>perform(()=>switchDocument('/api/library/load',{id:el('personalDocumentList').value}));
  el('newPersonalDocument').onclick=()=>perform(()=>switchDocument('/api/library/new'));
  el('refreshPersonalDocuments').onclick=()=>perform(refreshLibrary);
  libraryPanel.querySelector('details').addEventListener('toggle',()=>{if(libraryPanel.querySelector('details').open)refreshLibrary().catch(error=>notice(error.message,true));});
  window.addEventListener('storage',event=>{if(event.key===storageKey())refresh().then(async()=>{if(canEdit()&&!window.sharedWorkspace?.ready)await load();}).catch(()=>{});});
  setInterval(()=>{if(ready)refresh().catch(error=>{el('accessError').textContent='工作台状态未同步：'+error.message;el('accessError').hidden=false;});},1500);
  return {init:refresh,refresh,headers,render,get canEdit(){return canEdit();},get ownsSlot(){return ownsSlot();}};
})();
