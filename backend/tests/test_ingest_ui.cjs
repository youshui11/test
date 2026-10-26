/* 导入接口、2秒轮询、取消以及聊天页面导入与附件分离。 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function apiContext(fetch) {
  const waits = [];
  const context = {fetch, FormData, Response, TextDecoder, AbortController, DOMException,
    sessionStorage: {getItem: () => 'token'}, clearTimeout,
    setTimeout: (fn, ms) => {waits.push(ms); queueMicrotask(fn); return 1;}};
  context.window = context;
  vm.runInNewContext(fs.readFileSync(require.resolve('../../fronted/api.js'), 'utf8'), context);
  return {api: context.api, waits};
}

test('ingest uses separate multipart endpoint and polls every two seconds', async () => {
  let count = 0;
  const {api, waits} = apiContext(async (url, options) => {
    assert.equal(options.headers.Authorization, 'Bearer token');
    if (url === '/api/ingest') {
      assert.equal(options.method, 'POST');
      assert.ok(options.body instanceof FormData);
      return Response.json({fileId: 'f1', status: 'processing'}, {status: 202});
    }
    assert.equal(url, '/api/ingest/status/f1');
    count++;
    return Response.json({fileId: 'f1', status: count === 1 ? 'processing' : 'completed', chunkCount: 3});
  });
  const job = await api.ingestFile(new File(['资料'], 'sample.txt'));
  const result = await api.waitForIngest(job.fileId);
  assert.equal(result.chunkCount, 3);
  assert.deepEqual(waits, [2000, 2000]);
});

test('failed ingest reports backend error and aborted polling stops requests', async () => {
  const {api} = apiContext(async () => Response.json({status: 'failed', error: '转换失败'}));
  await assert.rejects(api.waitForIngest('f1'), /转换失败/);
  const controller = new AbortController(); controller.abort();
  await assert.rejects(api.waitForIngest('f1', controller.signal), {name: 'AbortError'});
});

function chatContext(api) {
  let routes, unmount;
  const app = {use: () => app, mount: () => {}};
  const context = {api, Date, JSON, AbortController, setTimeout: () => 0, clearTimeout: () => {},
    sessionStorage: {getItem: key => key === 'token' ? 'token' : JSON.stringify({username: 'alice', role: 'user'})},
    Vue: {createApp: () => app, ref: value => ({value}), computed: fn => ({get value() {return fn();}}),
      watch: () => {}, nextTick: async () => {}, onMounted: () => {}, onBeforeUnmount: fn => unmount = fn},
    VueRouter: {createRouter: value => {routes = value.routes; return {beforeEach: () => {}};},
      createWebHashHistory: () => {}, useRouter: () => ({})}};
  vm.runInNewContext(fs.readFileSync(require.resolve('../../fronted/app.js'), 'utf8'), context);
  return {chat: routes.find(route => route.path === '/chat').component.setup(), unmount: () => unmount()};
}

test('import creates knowledge task rather than message attachment', async () => {
  const calls = [];
  const {chat} = chatContext({ingestFile: async file => {calls.push(file.name); return {fileId: 'f1'};},
    waitForIngest: async () => ({status: 'completed', chunkCount: 4})});
  await chat.importMaterials({target: {files: [{name: 'notes.txt'}], value: 'selected'}});
  assert.deepEqual(calls, ['notes.txt']);
  assert.equal(chat.attachments.value.length, 0);
  assert.match(chat.importProgress.value, /导入成功.*4/);
  assert.equal(chat.importing.value, false);
});

test('unmount aborts active status polling', async () => {
  let signal;
  const {chat, unmount} = chatContext({ingestFile: async () => ({fileId: 'f1'}),
    waitForIngest: async (_, value) => {signal = value; await new Promise(resolve => value.addEventListener('abort', resolve));}});
  const pending = chat.importMaterials({target: {files: [{name: 'notes.txt'}], value: 'selected'}});
  await new Promise(resolve => setImmediate(resolve));
  unmount();
  await pending;
  assert.equal(signal.aborted, true);
});
