/* 用途：真实 HTTP API 适配，保留页面方法签名并解析 POST SSE。 */
(() => {
  'use strict';
  const base = window.API_BASE_URL || '';
  function headers(json = false) {
    const result = {};
    const token = sessionStorage.getItem('token');
    if (token) result.Authorization = 'Bearer ' + token;
    if (json) result['Content-Type'] = 'application/json';
    return result;
  }
  async function check(response) {
    if (response.ok) return response;
    let detail;
    try { detail = (await response.json()).detail; } catch {}
    if (Array.isArray(detail)) detail = detail.map(item => item.msg).join('；');
    throw new Error(typeof detail === 'string' ? detail : '请求失败（' + response.status + '）');
  }
  async function request(path, method = 'GET', body) {
    const options = { method, headers: headers(body !== undefined && !(body instanceof FormData)) };
    if (body !== undefined) options.body = body instanceof FormData ? body : JSON.stringify(body);
    return (await check(await fetch(base + path, options))).json();
  }
  const sessionPath = id => '/api/sessions/' + encodeURIComponent(id) + '/messages';
  window.api = {
    register: (username, password) => request('/api/users', 'POST', { username, password }),
    login: (username, password) => request('/api/login', 'POST', { username, password }),
    getSessions: () => request('/api/sessions'),
    createSession: () => request('/api/sessions', 'POST', {}),
    getMessages: id => request(sessionPath(id)),
    getAllSessions: () => request('/api/admin/sessions'),
    deleteSession: id => request('/api/admin/sessions/' + encodeURIComponent(id), 'DELETE'),
    uploadFile(file) {
      if (file.size > 20 * 1024 * 1024) return Promise.reject(new Error('单个附件不能超过 20 MB'));
      const data = new FormData(); data.append('file', file);
      return request('/api/upload', 'POST', data);
    },
    async downloadFile(file) {
      const response = await check(await fetch(base + '/api/files/' + encodeURIComponent(file.fileId), {headers: headers()}));
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a'); link.href = url; link.download = file.fileName;
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
    async sendMessage(id, content, fileIds = [], onDelta) {
      const response = await check(await fetch(base + sessionPath(id), {
        method: 'POST', headers: headers(true), body: JSON.stringify({ content, fileIds })
      }));
      if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream')) {
        throw new Error('服务未返回有效的流式响应');
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = ''; let result; let doneReceived = false;
      function consume() {
        let boundary;
        while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
          const event = buffer.slice(0, boundary.index).replace(/\r\n/g, '\n');
          buffer = buffer.slice(boundary.index + boundary[0].length);
          let type = 'message'; const data = [];
          for (const line of event.split('\n')) {
            if (line.startsWith('event:')) type = line.slice(6).trim();
            if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
          }
          if (!data.length) continue;
          const payload = JSON.parse(data.join('\n'));
          if (type === 'error') throw new Error(payload.message || '生成回复失败');
          if (type === 'delta' && onDelta) onDelta(payload.content || '');
          if (type === 'done') { result = payload; doneReceived = true; }
        }
      }
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) { buffer += decoder.decode(); consume(); break; }
          buffer += decoder.decode(value, { stream: true }); consume();
          if (doneReceived) break;
        }
        if (!doneReceived) throw new Error('回复连接已中断，请刷新会话确认结果后重试');
        return result;
      } finally {
        await reader.cancel().catch(() => {});
        reader.releaseLock();
      }
    }
  };
})();
