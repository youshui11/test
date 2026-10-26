/* Markdown 渲染边界测试：解析后必须清理 HTML；依赖失败时退回文本。 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function load(dependencies = {}) {
  let routes;
  const app = { use: () => app, mount() {} };
  vm.runInNewContext(fs.readFileSync(require.resolve('../../fronted/app.js'), 'utf8'), {
    ...dependencies, api: {}, Date, JSON, setTimeout: () => 0, clearTimeout() {},
    sessionStorage: { getItem: () => null },
    Vue: { createApp: () => app, ref: value => ({ value }), computed: fn => ({ get value() { return fn(); } }), watch() {}, nextTick: async () => {}, onMounted() {}, onBeforeUnmount() {} },
    VueRouter: { createRouter: options => { routes = options.routes; return { beforeEach() {} }; }, createWebHashHistory() {}, useRouter() {} }
  });
  const chat = routes.find(route => route.path === '/chat').component;
  const admin = routes.find(route => route.path === '/admin').component;
  assert.ok(chat.components.MarkdownContent, 'chat must register the Markdown component');
  assert.equal(chat.components.MarkdownContent, admin.components.MarkdownContent);
  return chat.components.MarkdownContent;
}

test('AI HTML passes through parser then sanitizer; streaming content updates the result', () => {
  const calls = [];
  const component = load({
    marked: { parse: (text, options) => { calls.push(['parse', text, options]); return '<h2>' + text + '</h2>'; } },
    DOMPurify: { sanitize: (html, options) => { calls.push(['sanitize', html, options]); return 'clean:' + html; } }
  });
  const props = { content: '标题' };
  const state = component.setup(props);
  assert.equal(state.html.value, 'clean:<h2>标题</h2>');
  assert.equal(calls[0][0], 'parse'); assert.equal(calls[1][0], 'sanitize');
  assert.equal(calls[0][2].gfm, true);
  assert.ok(calls[1][2].ALLOWED_TAGS.includes('table'));
  assert.ok(!calls[1][2].ALLOWED_TAGS.includes('script'));
  assert.ok(!calls[1][2].ALLOWED_ATTR.includes('onclick'));
  assert.ok(!calls[1][2].ALLOWED_ATTR.includes('style'));
  props.content += '\n更多内容';
  assert.match(state.html.value, /更多内容/);
});

test('missing CDN dependency never renders unsanitized HTML', () => {
  const component = load({ marked: { parse: () => '<script>bad()</script>' } });
  assert.equal(component.setup({ content: '<img onerror="bad()">' }).html.value, null);
  assert.match(component.template, /v-else/);
  assert.match(component.template, /\{\{\s*content\s*\}\}/);
});

test('parser failures fall back to original text instead of breaking the chat', () => {
  const component = load({ marked: { parse() { throw new Error('parse failed'); } }, DOMPurify: { sanitize: value => value } });
  assert.equal(component.setup({ content: '原始回复' }).html.value, null);
});
