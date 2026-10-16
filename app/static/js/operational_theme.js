/* Terceiro modelo: aplica somente as cores do perfil autenticado. */
(function(){'use strict';
const roles=new Set(['EQUIPE_ADMINISTRATIVA','COORDENADOR','MINISTRANTE','MONITOR_EXTENSIONISTA']);
async function init(){
 const token=localStorage.getItem('fe_token')||'';if(!token)return;
 try{
 const user=window.feEffectiveAdminAccess || (window.feAdminAccessPromise ? await window.feAdminAccessPromise : await (async()=>{const response=await fetch('/api/admin/acesso',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token}),cache:'no-store'});if(!response.ok)return null;return response.json()})());
 if(!user)return;if(!user.sucesso||!roles.has(user.categoria))return;
 const result=await fetch('/api/operacional/tema',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token}),cache:'no-store'});
 if(!result.ok)return;const data=await result.json();if(!data.sucesso)return;
 for(const [key,value] of Object.entries(data.cores))document.body.style.setProperty('--op-'+key.replaceAll('_','-'),value);
 document.body.classList.add('fe-operational');
 }catch(e){console.warn('Tema operacional indisponível',e)}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
