// Capture both static and dynamically rendered actions, including form submissions.
(function(){
var activeButton=null;
document.addEventListener('click',function(e){activeButton=e.target.closest('button');},true);
function busy(button){if(!button||button.disabled)return function(){};var label=button.textContent;button.disabled=true;button.setAttribute('aria-busy','true');button.textContent='İşleniyor…';return function(){button.disabled=false;button.removeAttribute('aria-busy');button.textContent=label}}
function guard(fn){return async function(){var b=activeButton;activeButton=null;var restore=busy(b);try{return await fn.apply(this,arguments)}catch(e){toast(e.message||'İşlem tamamlanamadı. Lütfen tekrar deneyin.')}finally{restore()}}}
['demo','save','proposal','pstatus','readAll','saveSettings','saveProfile','doImp','syncChannel','disconnectChannel','connectFiverrMail','syncFiverrMail','disconnectFiverrMail','load'].forEach(function(name){if(typeof window[name]==='function')window[name]=guard(window[name])});
['sendReset','refresh'].forEach(function(id){var b=$(id);if(b&&b.onclick){var fn=b.onclick;b.onclick=function(){activeButton=b;return guard(fn).apply(this,arguments)}}});
// A fresh session token protects every mutation, not only logout. Refresh once
// on the server's CSRF rejection; other 403 responses must never be retried.
var originalApi=api;
api=async function(u,o){try{return await originalApi(u,o)}catch(e){if(/Güvenlik oturumu yenilenmeli/.test(e.message)&&o&&/^(POST|PUT|PATCH|DELETE)$/i.test(o.method||'')){var info=await originalApi('/api/session',{cache:'no-store'});csrf=info.csrf;var retry=Object.assign({},o);retry.headers=Object.assign({},o.headers||{}, {'X-CSRF-Token':csrf});return originalApi(u,retry)}throw e}};
document.addEventListener('submit',async function(e){var form=e.target;if(form.dataset.actionBusy==='1'){e.preventDefault();e.stopImmediatePropagation();return}var button=e.submitter||form.querySelector('button[type="submit"],button:not([type])');form.dataset.actionBusy='1';var label=button?button.textContent:'';if(button){button.textContent='İşleniyor…';button.setAttribute('aria-busy','true')}var restore=function(){delete form.dataset.actionBusy;if(button){button.disabled=false;button.textContent=label;button.removeAttribute('aria-busy')}};var handler=form.onsubmit;if(handler){e.preventDefault();e.stopImmediatePropagation();try{await handler.call(form,e)}catch(x){toast(x.message||'İşlem tamamlanamadı.')}finally{restore()}}else restore();},true);
window.addEventListener('unhandledrejection',function(e){toast(e.reason&&e.reason.message||'İşlem tamamlanamadı. Lütfen yeniden deneyin.');e.preventDefault()});
})();
