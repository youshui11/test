/* 文件作用：验证聊天发送成功或失败时输入框、临时消息和已确认回答的状态。
 * 关联关系：通过 Node 加载 frontend/app.js 的页面逻辑，防止刷新失败破坏成功回答。
 */
/* 实际调用 Chat.setup/send，验证收到 done 后刷新失败不会恢复已提交草稿。 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setupChat(api, hooks = {}) {
  let routes;
  const app = { use: () => app, mount: () => {} };
  const context = {
    api, Date, JSON, setTimeout: () => 0, clearTimeout: () => {},
    sessionStorage: {getItem: key => key === 'token' ? 'token' : JSON.stringify({username: 'alice', role: 'user'})},
    Vue: {
      createApp: () => app, ref: value => ({value}), computed: fn => ({get value() {return fn();}}),
      watch: () => {}, nextTick: hooks.nextTick || (async () => {}), onMounted: hooks.onMounted || (() => {}), onBeforeUnmount: () => {}
    },
    VueRouter: {
      createRouter: options => {routes = options.routes; return {beforeEach: () => {}};},
      createWebHashHistory: () => {}, useRouter: () => ({})
    }
  };
  vm.runInNewContext(fs.readFileSync(require.resolve('../../frontend/app.js'), 'utf8'), context);
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

test('switching sessions scrolls after the loading placeholder is replaced by messages', async () => {
  const chat = setupChat({ getMessages: async id => [{msgId: id, role: 'ai', content: '历史消息'}] });
  chat.messageBox.value = { scrollTop: 0, get scrollHeight() { return chat.loading.value ? 40 : 1800; } };
  await chat.selectSession('first');
  assert.equal(chat.messageBox.value.scrollTop, 1800);
  chat.messageBox.value.scrollTop = 0;
  await chat.selectSession('second');
  assert.equal(chat.messageBox.value.scrollTop, 1800);
});

test('initial session load also scrolls to the latest message', async () => {
  let mounted;
  const chat = setupChat({
    getSessions: async () => [{sessionId: 'latest'}],
    getMessages: async () => [{msgId: 'last', role: 'ai', content: '最新消息'}]
  }, {onMounted: callback => {mounted = callback;}});
  chat.messageBox.value = { scrollTop: 0, get scrollHeight() { return chat.loading.value ? 40 : 2300; } };
  await mounted();
  assert.equal(chat.activeId.value, 'latest');
  assert.equal(chat.messageBox.value.scrollTop, 2300);
});
