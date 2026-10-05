const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('web/index.html', 'utf8');
const script = html.split('<script>')[1].split('</script>')[0];

async function scenario(fail) {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {
      value: '', textContent: '', innerHTML: '', disabled: false, style: {},
      classList: {add() {}, remove() {}, toggle() {}},
    });
    return nodes.get(id);
  };
  const calls = [];
  let reloads = 0;
  const context = vm.createContext({
    document: {getElementById: node, querySelectorAll: () => []},
    location: {search: '', reload: () => reloads++},
    URLSearchParams, setTimeout: () => {},
    fetch: async (url, options) => {
      calls.push({url, options});
      if (url === '/api/auth/logout') {
        assert.deepEqual(JSON.parse(options.body), {});
        assert.equal(options.headers['X-CSRF-Token'], 'fresh-token');
        return {ok: !fail, json: async () => fail ? {error: 'Sunucu hatası'} : {ok: true}};
      }
      return {ok: true, json: async () => url === '/api/session'
        ? {csrf: 'fresh-token', google_ready: false} : {authenticated: false}};
    },
  });
  vm.runInContext(script, context);
  await new Promise(resolve => setImmediate(resolve));
  context.csrf = 'stale-token';
  context.S.user = {id: 1};
  node('pass').value = 'test-placeholder';
  await node('logout').onclick();
  assert.equal(calls.filter(c => c.url === '/api/auth/logout').length, 1);
  assert.equal(node('logout').disabled, false);
  if (fail) {
    assert.equal(reloads, 0);
    assert.equal(context.S.user.id, 1);
    assert.match(node('toast').textContent, /Çıkış yapılamadı.*Sunucu hatası/);
  } else {
    assert.equal(reloads, 1);
    assert.equal(context.S.user, null);
    assert.equal(node('pass').value, '');
  }
  // Other bodyless mutations use the same valid JSON envelope.
  await context.api('/api/notifications/read', {method: 'POST'});
  assert.equal(calls.at(-1).options.body, '{}');
}

(async () => {
  await scenario(false);
  await scenario(true);
  console.log('Logout success, stale token refresh, failure feedback and empty mutation regressions passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
