const assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync('web/index.html','utf8');
(async()=>{let nodes=new Map(),handlers={},calls=[],failCsrf=true;const node=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'Original',disabled:false,style:{},classList:{add(){},remove(){},toggle(){}},setAttribute(){},removeAttribute(){},value:'',dataset:{}});return nodes.get(id)};
const context=vm.createContext({document:{getElementById:node,querySelectorAll:()=>[],addEventListener:(type,fn)=>handlers[type]=fn},location:{search:'',pathname:'/',reload(){}},history:{replaceState(){}},URLSearchParams,URL,AbortController,setInterval(){},setTimeout(){},clearTimeout(){},console,fetch:async(u,o)=>{calls.push({u,o});if(u==='/api/settings'&&o.method==='PUT'&&failCsrf){failCsrf=false;return {ok:false,status:403,json:async()=>({error:'Güvenlik oturumu yenilenmeli. Sayfayı yenileyin.'})}}return {ok:true,json:async()=>u==='/api/session'?{csrf:'fresh',google_ready:false}:u==='/api/me'?{authenticated:false}:{ok:true}}}});
context.window=context;context.addEventListener=(type,fn)=>handlers[type]=fn;
vm.runInContext(html.split('<script>')[1].split('</script>')[0],context);await new Promise(r=>setImmediate(r));
vm.runInContext(fs.readFileSync('web/hub.js','utf8'),context);
context.demo=async()=>{throw Error('Visible failure')};context.saveProfile=async()=>{assert.equal(node('button').disabled,true)};
vm.runInContext(fs.readFileSync('web/actions.js','utf8'),context);
assert.ok(!fs.readFileSync('web/hub.js','utf8').toLowerCase().includes('fiverr'));
// Every registered async action restores state even when an operation fails.
handlers.click({target:{closest:()=>node('button')}});await context.demo();assert.equal(node('button').disabled,false);assert.equal(node('button').textContent,'Original');assert.match(node('toast').textContent,/Visible failure/);
handlers.click({target:{closest:()=>node('button')}});await context.saveProfile();assert.equal(node('button').disabled,false);
// The shared API retries only expired CSRF and uses the new token.
await context.api('/api/settings',{method:'PUT',body:'{}'});const writes=calls.filter(x=>x.u==='/api/settings');assert.equal(writes.length,2);assert.equal(writes[1].o.headers['X-CSRF-Token'],'fresh');
// Dynamically installed submit handlers get consistent progress and recovery.
const form={dataset:{},querySelector:()=>node('submit'),onsubmit:async()=>{throw Error('Form failure')}};await handlers.submit({target:form,submitter:node('submit'),preventDefault(){},stopImmediatePropagation(){}});assert.equal(form.dataset.actionBusy,undefined);assert.equal(node('submit').disabled,false);assert.match(node('toast').textContent,/Form failure/);
// Logout keeps its existing state machine rather than being pre-disabled.
await node('logout').onclick();assert.equal(node('logout').disabled,false);
console.log('Fiverr removal, shared busy/error handling, CSRF recovery, dynamic forms and logout passed');})().catch(e=>{console.error(e);process.exitCode=1});
