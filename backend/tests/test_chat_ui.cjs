/* 实际调用 Chat.setup/send，验证收到 done 后刷新失败不会恢复已提交草稿。 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setupChat(api) {
  let routes;
  const app = { use: () => app, mount: () => {} };
  const context = {
    api, Date, JSON, setTimeout: () => 0, clearTimeout: () => {},
    sessionStorage: {getItem: key => key === 'token' ? 'token' : JSON.stringify({username: 'alice', role: 'user'})},
    Vue: {
      createApp: () => app, ref: value => ({value}), computed: fn => ({get value() {return fn();}}),
      watch: () => {}, nextTick: async () => {}, onMounted: () => {}, onBeforeUnmount: () => {}
    },
    VueRouter: {
      createRouter: options => {routes = options.routes; return {beforeEach: () => {}};},
      createWebHashHistory: () => {}, useRouter: () => ({})
    }
  };
  vm.runInNewContext(fs.readFileSync(require.resolve('../../fronted/app.js'), 'utf8'), context);
  return routes.find(route => route.path === '/chat').component.setup();
}

test('successful send followed by refresh failure keeps input cleared and confirmed reply', async () => {
  const chat = setupChat({
    createSession: async () => ({sessionId: 's1'}),
    sendMessage: async (id, text, ids, delta) => {delta('回答'); return {msgId: 'm1', role: 'ai', content: '回答', files: [], time: '2026-10-21'};},
    getMessages: async () => {throw new Error('refresh failed');}
  });
  chat.draft.value = '问题';
  await chat.send();
  assert.equal(chat.draft.value, '');
  assert.equal(chat.attachments.value.length, 0);
  assert.equal(chat.messages.value.at(-1).content, '回答');
});

test('unconfirmed send failure restores input and removes temporary reply', async () => {
  const chat = setupChat({createSession: async () => ({sessionId: 's1'}), sendMessage: async () => {throw new Error('failed');}});
  chat.draft.value = '问题';
  await chat.send();
  assert.equal(chat.draft.value, '问题');
  assert.equal(chat.messages.value.length, 0);
});
