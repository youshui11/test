/* 验证 API 适配层跨块中文 SSE、异常和认证头。 */
const test = require('node:test');
const assert = require('node:assert/strict');
global.window = global;
global.addEventListener = () => {};
global.sessionStorage = { getItem: () => 'test-token' };
require('../../fronted/api.js');

function response(text, chunkSize = 1) {
  const bytes = new TextEncoder().encode(text);
  return new Response(new ReadableStream({ start(controller) {
    for (let i = 0; i < bytes.length; i += chunkSize) controller.enqueue(bytes.slice(i, i + chunkSize));
    controller.close();
  } }), {headers: {'Content-Type': 'text/event-stream'}});
}

test('POST streams Chinese text across byte boundaries and returns done message', async () => {
  global.fetch = async (url, options) => {
    assert.equal(url, '/api/sessions/session1/messages');
    assert.equal(options.headers.Authorization, 'Bearer test-token');
    assert.deepEqual(JSON.parse(options.body), {content: '问题', fileIds: []});
    return response('event: delta\r\ndata: {"content":"你好"}\r\n\r\nevent: delta\ndata: {"content":"世界"}\n\nevent: done\ndata: {"msgId":"m1","content":"你好世界"}\n\n');
  };
  let content = '';
  const result = await api.sendMessage('session1', '问题', [], delta => content += delta);
  assert.equal(content, '你好世界');
  assert.equal(result.msgId, 'm1');
});

test('SSE error and interrupted streams reject', async () => {
  global.fetch = async () => response('event: error\ndata: {"message":"模型失败"}\n\n');
  await assert.rejects(api.sendMessage('s1', 'test'), /模型失败/);
  global.fetch = async () => response('event: delta\ndata: {"content":"partial"}\n\n');
  await assert.rejects(api.sendMessage('s1', 'test'), /中断/);
});

test('HTTP errors become readable messages', async () => {
  global.fetch = async () => Response.json({detail: '需要管理员权限'}, {status: 403});
  await assert.rejects(api.getAllSessions(), /需要管理员权限/);
});
