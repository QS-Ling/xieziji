'use strict';
(()=>{
  const el=id=>document.getElementById(id);
  el('helpApiUrl').value=(window.PLOTTER_API_BASE||location.origin).replace(/\/$/,'');
  function update(){
    const command=el('helpPython').value.trim(),script=el('helpScript').value.trim().replace(/\\/g,'/'),url=el('helpApiUrl').value.trim().replace(/\/$/,'');
    const q=value=>JSON.stringify(value);
    el('helpCodex').textContent=`[mcp_servers.zhijian_plotter]\ncommand = ${q(command)}\nargs = [${q(script)}, "--api-url", ${q(url)}]\nstartup_timeout_sec = 30\ntool_timeout_sec = 180\n`;
    el('helpDSH').textContent=`- insert:\n    - id: mcp-zhijian-plotter\n      name: '@deepseek-ai/dsh-mcp-client'\n      config:\n        serverName: zhijian_plotter\n        transport: stdio\n        command: ${q(command)}\n        args: [${q(script)}, "--api-url", ${q(url)}]\n        toolCallTimeoutMs: 180000\n        env:\n          PYTHONIOENCODING: utf-8\n`;
  }
  for(const id of ['helpApiUrl','helpPython','helpScript'])el(id).addEventListener('input',update);
  for(const [button,target] of [['copyCodex','helpCodex'],['copyDSH','helpDSH']])el(button).onclick=async()=>{
    try{if(!navigator.clipboard?.writeText)throw new Error('请选中配置文本手动复制');await navigator.clipboard.writeText(el(target).textContent);el('helpCopyStatus').textContent='配置已复制';}
    catch(error){el('helpCopyStatus').textContent=error.message;}
  };
  update();
})();
