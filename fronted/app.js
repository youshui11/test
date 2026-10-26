/* 用途：Vue 3 Composition API 页面、共享认证状态和 Vue Router 4 路由守卫。 */
(() => {
  'use strict';
  const { createApp, ref, computed, watch, nextTick, onMounted, onBeforeUnmount } = Vue;
  const { createRouter, createWebHashHistory, useRouter } = VueRouter;
  function storedUser() {
    try {
      const value = JSON.parse(sessionStorage.getItem('userInfo'));
      return sessionStorage.getItem('token') && value?.username && ['admin', 'user'].includes(value.role) ? value : null;
    } catch { return null; }
  }
  const user = ref(storedUser());
  const notice = ref('');
  let toastTimer;
  function notify(message) { notice.value = message; clearTimeout(toastTimer); toastTimer = setTimeout(() => { notice.value = ''; }, 4200); }
  const formatTime = value => new Date(value).toLocaleString('zh-CN', { hour12: false });
  const formatSize = size => size < 1024 * 1024 ? (size / 1024).toFixed(1) + ' KB' : (size / 1024 / 1024).toFixed(1) + ' MB';
  function logout() {
    sessionStorage.removeItem('token'); sessionStorage.removeItem('userInfo'); user.value = null;
    router.replace('/login');
  }
  const MarkdownContent = {
    props: { content: { type: String, default: '' } },
    setup(props) {
      // 响应式解析完整累计内容，流式追加时也会更新；禁止把未清理的 HTML 交给 v-html。
      const html = computed(() => {
        if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') return null;
        try {
          const parsed = marked.parse(props.content, { gfm: true, breaks: true, async: false });
          return DOMPurify.sanitize(parsed, {
            ALLOWED_TAGS: ['p', 'br', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'em', 'del', 's', 'blockquote', 'ul', 'ol', 'li', 'pre', 'code', 'a', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td'],
            ALLOWED_ATTR: ['href', 'title', 'src', 'alt', 'start', 'align']
          });
        } catch { return null; } // CDN 或解析失败时安全回退为 Vue 文本插值。
      });
      return { html };
    },
    template: `<div v-if="html !== null" class="markdown-body" v-html="html"></div><p v-else class="markdown-fallback">{{ content }}</p>`
  };
  const FileCard = {
    props: ['file', 'removable'], emits: ['remove'], setup: () => ({ formatSize, download: file => api.downloadFile(file).catch(e => notify(e.message)) }),
    template: `<div class="file-card"><span class="file-icon">↥</span><div><button type="button" class="text-btn" @click="download(file)" :title="'下载 '+file.fileName">{{ file.fileName }}</button><small>{{ formatSize(file.size) }}</small></div><button v-if="removable" type="button" class="icon-btn" @click="$emit('remove')" :aria-label="'移除附件 '+file.fileName">×</button></div>`
  };
  const Login = {
    setup() {
      const username = ref(''); const password = ref(''); const loading = ref(false); const error = ref('');
      const registering = ref(false); const confirmPassword = ref('');
      const route = useRouter();
      function switchMode() {
        if (loading.value) return;
        registering.value = !registering.value;
        password.value = ''; confirmPassword.value = ''; error.value = '';
      }
      async function submit() {
        if (loading.value) return;
        error.value = ''; loading.value = true;
        try {
          if (registering.value) {
            if (password.value !== confirmPassword.value) throw new Error('两次输入的密码不一致');
            const result = await api.register(username.value.trim(), password.value);
            // 注册成功后回到登录表单，保留账号并清除密码，由用户登录。
            username.value = result.username; registering.value = false;
            password.value = ''; confirmPassword.value = '';
            notify('注册成功，请使用新账号登录');
            return;
          }
          const result = await api.login(username.value.trim(), password.value);
          // 只持久化 token 和公开用户信息，绝不存储密码。
          sessionStorage.setItem('token', result.token);
          sessionStorage.setItem('userInfo', JSON.stringify({ username: result.username, role: result.role }));
          user.value = { username: result.username, role: result.role };
          await route.replace('/chat');
        } catch (e) { error.value = e.message; } finally { loading.value = false; }
      }
      return { username, password, loading, error, registering, confirmPassword, switchMode, submit };
    },
    template: `<main class="login-page"><div class="login-brand"><span class="brand-symbol">查</span><span>资料查询助手 <small>RESEARCH ASSISTANT</small></span></div><section class="login-card"><span class="eyebrow">YOUR RESEARCH ASSISTANT</span><h1>{{ registering ? '注册新用户' : '让资料查询，更简单。' }}</h1><p class="muted">{{ registering ? '创建普通用户账号，开始你的资料查询。' : '登录资料查询助手，开启你的查询与探索。' }}</p><form @submit.prevent="submit"><label for="username">账号</label><input id="username" v-model="username" autocomplete="username" :placeholder="registering ? '3–32 位字母、数字或下划线' : '请输入账号'" :maxlength="registering ? 32 : 64" :minlength="registering ? 3 : undefined" :pattern="registering ? '[a-zA-Z0-9_]{3,32}' : undefined" required :disabled="loading"><label for="password">密码</label><input id="password" v-model="password" type="password" :autocomplete="registering ? 'new-password' : 'current-password'" :placeholder="registering ? '请输入 6–64 位密码' : '请输入密码'" :minlength="registering ? 6 : undefined" :maxlength="registering ? 64 : undefined" required :disabled="loading"><template v-if="registering"><label for="confirm-password">确认密码</label><input id="confirm-password" v-model="confirmPassword" type="password" autocomplete="new-password" placeholder="请再次输入密码" minlength="6" maxlength="64" required :disabled="loading"></template><p v-if="error" class="error" role="alert">{{ error }}</p><button class="primary login-submit" :disabled="loading">{{ loading ? (registering ? '正在注册…' : '正在登录…') : (registering ? '注 册 →' : '登 录 →') }}</button></form><div class="auth-switch"><span>{{ registering ? '已有账号？' : '还没有账号？' }}</span><button type="button" class="text-btn" @click="switchMode" :disabled="loading">{{ registering ? '返回登录' : '注册用户' }}</button></div><p v-if="registering" class="registration-note">注册后可保存对话与个人资料。</p><p v-else class="registration-note">请使用已注册账号，管理员由服务端创建。</p></section><p class="login-foot">让信息触手可及，让查询更有方向。<br><small>个人知识库 · 对话记录持久保存</small></p></main>`
  };
  const Chat = {
    components: { FileCard, MarkdownContent },
    setup() {
      const sessions = ref([]); const activeId = ref(''); const messages = ref([]); const draft = ref('');
      const attachments = ref([]); const sending = ref(false); const uploading = ref(false); const loading = ref(false); const creating = ref(false);
      const importing = ref(false); const importInput = ref(null); const importProgress = ref('');
      let importController = null;
      const sidebarOpen = ref(false); const fileInput = ref(null); const messageBox = ref(null); const loadError = ref('');
      let requestId = 0; let disposed = false;
      const activeTitle = computed(() => sessions.value.find(item => item.sessionId === activeId.value)?.title || '新的灵感，从这里开始');
      async function scrollDown() { await nextTick(); if (messageBox.value) messageBox.value.scrollTop = messageBox.value.scrollHeight; }
      async function refresh() { const list = await api.getSessions(); if (!disposed) sessions.value = list; }
      async function selectSession(sessionId) {
        if (sending.value || uploading.value || creating.value) return;
        const version = ++requestId;
        activeId.value = sessionId; messages.value = []; attachments.value = []; draft.value = ''; loading.value = true; loadError.value = ''; sidebarOpen.value = false;
        try {
          const list = await api.getMessages(sessionId);
          // 忽略快速切换会话后返回的旧请求，防止消息串入当前会话。
          if (!disposed && version === requestId) { messages.value = list; await scrollDown(); }
        } catch (e) { if (version === requestId) loadError.value = e.message; }
        finally { if (version === requestId) loading.value = false; }
      }
      async function newSession() {
        if (sending.value || uploading.value || creating.value) return;
        creating.value = true;
        let item;
        try { item = await api.createSession(); await refresh(); }
        catch (e) { notify(e.message); }
        finally { creating.value = false; }
        if (item && !disposed) await selectSession(item.sessionId);
      }
      async function upload(event) {
        const selected = [...event.target.files]; event.target.value = '';
        if (uploading.value || sending.value) return;
        uploading.value = true;
        try {
          for (const file of selected) {
            try { const result = await api.uploadFile(file); if (!disposed) attachments.value.push(result); }
            catch (e) { notify(file.name + '：' + e.message); }
          }
        } finally { uploading.value = false; }
      }
      async function send() {
        if (sending.value || uploading.value || loading.value || creating.value || loadError.value || (!draft.value.trim() && !attachments.value.length)) return;
        sending.value = true;
        const text = draft.value.trim(); const chosen = [...attachments.value];
        let optimistic; let committed = false;
        try {
          if (!activeId.value) { const item = await api.createSession(); activeId.value = item.sessionId; }
          optimistic = { msgId: 'pending', role: 'user', content: text, files: chosen, time: new Date().toISOString() };
          messages.value.push(optimistic); draft.value = ''; attachments.value = []; await scrollDown();
          messages.value.push({ msgId: 'streaming', role: 'ai', content: '', files: [], time: new Date().toISOString() });
          const reply = await api.sendMessage(activeId.value, text, chosen.map(file => file.fileId), delta => {
            if (disposed) return;
            const message = messages.value.find(item => item.msgId === 'streaming');
            if (message) message.content += delta;
            scrollDown();
          });
          committed = true;
          if (disposed) return;
          messages.value = messages.value.map(item => item.msgId === 'streaming' ? reply
            : item.msgId === 'pending' ? { ...item, msgId: 'sent_' + reply.msgId } : item);
          messages.value = await api.getMessages(activeId.value); await refresh(); await scrollDown();
        } catch (e) {
          if (committed) { loadError.value = '回答已保存，但刷新失败，请重新加载会话。'; notify(loadError.value); return; }
          // 保留用户输入与附件，失败时可以重新提交。
          if (optimistic) messages.value = messages.value.filter(item => !['pending', 'streaming'].includes(item.msgId));
          draft.value = text; attachments.value = chosen; notify(e.message);
        } finally { sending.value = false; }
      }
      async function importMaterials(event) {
        const selected = [...event.target.files]; event.target.value = '';
        if (importing.value || uploading.value || sending.value || !selected.length) return;
        importing.value = true;
        importController = new AbortController();
        try {
          for (const file of selected) {
            if (disposed) return;
            try {
              importProgress.value = '正在上传资料：' + file.name;
              const job = await api.ingestFile(file, importController.signal);
              if (disposed) return;
              importProgress.value = '正在转换与入库：' + file.name;
              const completed = await api.waitForIngest(job.fileId, importController.signal);
              if (disposed) return;
              importProgress.value = '导入成功，共 ' + completed.chunkCount + ' 个片段：' + file.name;
              notify(importProgress.value);
            } catch (error) {
              if (disposed || error.name === 'AbortError') return;
              importProgress.value = file.name + '：' + error.message;
              notify(importProgress.value);
            }
          }
        } finally { importing.value = false; importController = null; }
      }
      function keydown(event) {
        // 中文输入法组词期间的 Enter 不发送；Shift+Enter 用于换行。
        if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); send(); }
      }
      function prompt(text) { draft.value = text; }
      onMounted(async () => { loading.value = true; try { await refresh(); if (!disposed && sessions.value.length) await selectSession(sessions.value[0].sessionId); } catch (e) { notify(e.message); } finally { loading.value = false; } });
      onBeforeUnmount(() => { disposed = true; requestId++; importController?.abort(); });
      return { user, sessions, activeId, messages, draft, attachments, sending, uploading, loading, creating, sidebarOpen, fileInput, messageBox, loadError, activeTitle, selectSession, newSession, upload, send, keydown, prompt, logout, formatTime, importing, importInput, importProgress, importMaterials };
    },
    template: `<div class="chat-layout"><button v-if="sidebarOpen" class="scrim" aria-label="关闭导航" @click="sidebarOpen=false"></button><aside class="sidebar" :class="{open:sidebarOpen}"><a class="brand" href="#/chat"><span class="brand-symbol">查</span><span>资料查询助手<small>RESEARCH ASSISTANT</small></span></a><button class="new-chat" @click="newSession" :disabled="sending||uploading||creating">＋ <span>{{ creating ? '正在创建…' : '开启新对话' }}</span><span class="shortcut">↗</span></button><div class="history-heading">最近对话 <span>{{ sessions.length }}</span></div><nav class="history"><button v-for="item in sessions" :key="item.sessionId" :class="{active:activeId===item.sessionId}" @click="selectSession(item.sessionId)" :disabled="sending||uploading||creating"><span>◷</span><span class="truncate">{{ item.title }}</span></button><p v-if="!sessions.length" class="muted empty-history">你的灵感记录将出现在这里</p></nav><div class="sidebar-bottom"><div class="workspace-note"><span>✧</span> 让每一个想法都有回响</div><RouterLink v-if="user.role==='admin'" class="admin-link" to="/admin">⚙ 会话管理 <span>↗</span></RouterLink><div class="user-row"><div class="avatar">{{ user.username.slice(0,1).toUpperCase() }}</div><div class="user-name"><strong>{{ user.username }}</strong><small>{{ user.role==='admin' ? '管理员' : '个人空间' }}</small></div><button class="icon-btn" @click="logout" aria-label="退出登录" title="退出登录">⇥</button></div></div></aside><main class="chat-main"><header class="chat-header"><div class="header-title"><button class="icon-btn mobile-menu" @click="sidebarOpen=true" aria-label="打开导航">☰</button><span class="truncate">{{ activeTitle }}</span></div><span class="model-badge"><i></i> 资料查询助手 AI <small>· 知识库</small></span></header><div ref="messageBox" class="message-scroll" :aria-busy="loading"><div v-if="loading" class="state">正在加载对话…</div><div v-else-if="loadError" class="state error">{{ loadError }} <button class="text-btn" @click="selectSession(activeId)">重试</button></div><section v-else-if="!messages.length" class="welcome"><div class="welcome-mark">✧</div><span class="eyebrow">A LITTLE CLARITY, A NEW POSSIBILITY</span><h1>你好，{{ user.username }}<br>今天，有什么新想法？</h1><p>从一个问题、一份灵感，或一段天马行空的想象开始。</p><div class="suggestions"><button @click="prompt('帮我把一个想法变成可执行的计划')"><span>✦</span><strong>激发灵感</strong><small>让模糊的想法渐渐清晰</small><b>↗</b></button><button @click="prompt('请帮我润色一段文字')"><span>✎</span><strong>写点什么</strong><small>找到恰到好处的表达</small><b>↗</b></button><button @click="prompt('请向初学者解释 Vue 3 Composition API')"><span>⌘</span><strong>探索知识</strong><small>一起拆解复杂的问题</small><b>↗</b></button></div></section><div v-else class="messages" role="log" aria-label="对话消息" aria-live="polite"><article v-for="message in messages" :key="message.msgId" class="message" :class="message.role"><div v-if="message.role==='ai'" class="ai-avatar">✧</div><div class="message-body"><div v-if="message.role==='ai'" class="message-author">资料查询助手 <small>AI</small></div><div class="bubble"><template v-if="message.content"><MarkdownContent v-if="message.role==='ai'" :content="message.content" /><p v-else>{{ message.content }}</p></template><div v-if="message.files?.length" class="message-files"><FileCard v-for="file in message.files" :key="file.fileId" :file="file" /></div></div><time>{{ formatTime(message.time) }}</time></div></article><article v-if="sending&&!messages.some(item=>item.msgId==='streaming'&&item.content)" class="message ai"><div class="ai-avatar">✧</div><div class="thinking">正在思考<span>•••</span></div></article></div></div><div class="composer-area"><p v-if="importProgress" class="import-progress" role="status">{{ importProgress }}</p><form class="composer" @submit.prevent="send"><div v-if="attachments.length" class="attachments"><FileCard v-for="(file,index) in attachments" :key="file.fileId" :file="file" :removable="!sending" @remove="attachments.splice(index,1)" /></div><textarea v-model="draft" aria-label="消息内容" placeholder="给资料查询助手发送消息，开启无限可能…" rows="3" @keydown="keydown" :disabled="sending||loading||creating" maxlength="10000"></textarea><div class="composer-toolbar"><div class="composer-tools"><input ref="fileInput" type="file" accept=".pdf,.docx,.txt,.md" multiple hidden @change="upload"><button class="attach-btn" type="button" @click="fileInput.click()" :disabled="uploading||sending||loading||creating" aria-label="上传文件">＋ <span>{{ uploading ? '上传中…' : '添加附件' }}</span></button><input ref="importInput" type="file" accept=".pdf,.docx,.xlsx,.xls,.pptx,.txt,.md" multiple hidden @change="importMaterials"><button class="import-btn" type="button" @click="importInput.click()" :disabled="importing||uploading||sending||loading||creating" aria-label="导入资料" title="支持 PDF、Word、Excel、PowerPoint、文本、Markdown，最大 50 MB"><span aria-hidden="true">↥</span> {{ importing ? "导入中…" : "导入资料" }}</button><span class="composer-divider"></span><span class="mock-label">✧ 灵感模式</span></div><button class="send-btn" :disabled="sending||uploading||loading||creating||!!loadError||(!draft.trim()&&!attachments.length)" aria-label="发送消息">{{ sending ? '…' : '↑' }}</button></div></form><p class="composer-foot">回答由 AI 生成，请结合资料核实 <span>Enter 发送 · Shift + Enter 换行</span></p></div></main></div>`
  };
  const Admin = {
    components: { FileCard, MarkdownContent },
    setup() {
      const list = ref([]); const query = ref(''); const loading = ref(false); const error = ref(''); const expanded = ref(null); const details = ref([]); const detailLoading = ref(false); const detailError = ref(''); const deleting = ref('');
      let detailVersion = 0;
      const filtered = computed(() => list.value.filter(item => (item.username + ' ' + item.sessionId).toLowerCase().includes(query.value.trim().toLowerCase())));
      async function load() { loading.value = true; error.value = ''; try { list.value = await api.getAllSessions(); } catch (e) { error.value = e.message; } finally { loading.value = false; } }
      async function expand(item) {
        const version = ++detailVersion;
        if (expanded.value === item.sessionId) { expanded.value = null; return; }
        expanded.value = item.sessionId; details.value = []; detailError.value = ''; detailLoading.value = true;
        try { const data = await api.getMessages(item.sessionId); if (version === detailVersion) details.value = data; }
        catch (e) { if (version === detailVersion) detailError.value = e.message; }
        finally { if (version === detailVersion) detailLoading.value = false; }
      }
      async function remove(item) {
        if (deleting.value || !window.confirm('确定删除会话“' + item.sessionId + '”？此操作无法撤销。')) return;
        deleting.value = item.sessionId;
        try { await api.deleteSession(item.sessionId); if (expanded.value === item.sessionId) { expanded.value = null; detailVersion++; } await load(); notify('会话已删除'); }
        catch (e) { notify(e.message); } finally { deleting.value = ''; }
      }
      onMounted(load);
      return { list, query, loading, error, expanded, details, detailLoading, detailError, deleting, filtered, load, expand, remove, formatTime };
    },
    template: `<main class="admin-page"><header class="admin-header"><RouterLink class="brand" to="/chat"><span class="brand-symbol">查</span><span>资料查询助手</span></RouterLink><RouterLink class="secondary" to="/chat">← 返回主界面</RouterLink></header><section class="admin-content"><span class="eyebrow">WORKSPACE ADMINISTRATION</span><h1>会话管理<span class="count-badge">{{ list.length }}</span></h1><p class="muted">查看所有用户的对话记录，管理工作空间中的每一场交流。</p><div class="admin-toolbar"><label class="search-box"><span>⌕</span><input v-model="query" aria-label="按账号或会话ID筛选" placeholder="搜索用户账号 / 会话 ID"></label><button class="secondary" @click="load" :disabled="loading">{{ loading ? '加载中…' : '↻ 刷新列表' }}</button></div><p v-if="error" class="error" role="alert">{{ error }}</p><div class="table-wrap" :aria-busy="loading"><table><thead><tr><th>用户账号</th><th>会话 ID</th><th>最后一条消息</th><th>消息数</th><th>创建时间</th><th>更新时间</th><th>操作</th></tr></thead><tbody><tr v-if="loading"><td colspan="7" class="table-empty">正在加载会话…</td></tr><tr v-else-if="!filtered.length"><td colspan="7" class="table-empty">{{ query ? '未找到匹配的会话' : '暂无会话' }}</td></tr><template v-else v-for="item in filtered" :key="item.sessionId"><tr><td><span class="account-cell">{{ item.username }}</span></td><td class="session-id">{{ item.sessionId }}</td><td><div class="summary" :title="item.lastMessage">{{ item.lastMessage }}</div></td><td>{{ item.msgCount }}</td><td class="date-cell">{{ formatTime(item.createTime) }}</td><td class="date-cell">{{ formatTime(item.updateTime) }}</td><td><div class="actions"><button class="text-btn" @click="expand(item)" :aria-expanded="expanded===item.sessionId">{{ expanded===item.sessionId ? '收起' : '查看详情' }}</button><button class="text-btn danger" @click="remove(item)" :disabled="!!deleting">{{ deleting===item.sessionId ? '删除中…' : '删除' }}</button></div></td></tr><tr v-if="expanded===item.sessionId"><td colspan="7" class="detail-cell"><div v-if="detailLoading" class="state">正在加载消息…</div><p v-else-if="detailError" class="error" role="alert">{{ detailError }}</p><p v-else-if="!details.length" class="muted">该会话还没有消息</p><div v-else class="detail-messages"><article v-for="message in details" :key="message.msgId"><header><strong>{{ message.role==='ai' ? '资料查询助手 AI' : item.username }}</strong><time>{{ formatTime(message.time) }}</time></header><MarkdownContent v-if="message.role==='ai'" :content="message.content" /><p v-else>{{ message.content }}</p><div class="attachments"><FileCard v-for="file in message.files" :key="file.fileId" :file="file" /></div></article></div></td></tr></template></tbody></table></div><p class="admin-note">共 {{ filtered.length }} 个会话 · 对话记录保存在数据库中。</p></section></main>`
  };
  const router = createRouter({
    // Hash 路由由同源 FastAPI 提供页面，无需额外 history fallback。
    history: createWebHashHistory(),
    routes: [{ path: '/', redirect: '/chat' }, { path: '/login', component: Login }, { path: '/chat', component: Chat, meta: { requiresAuth: true } }, { path: '/admin', component: Admin, meta: { requiresAuth: true, admin: true } }, { path: '/:pathMatch(.*)*', redirect: '/chat' }]
  });
  router.beforeEach(to => {
    user.value = storedUser();
    if (to.meta.requiresAuth && !user.value) return '/login';
    if (to.meta.admin && user.value?.role !== 'admin') { notify('无权限：仅管理员可以访问会话管理'); return '/chat'; }
    if (to.path === '/login' && user.value) return '/chat';
  });
  createApp({ setup: () => ({ notice }), template: `<RouterView /><Transition name="toast"><div v-if="notice" class="toast" role="alert">{{ notice }}</div></Transition>` }).use(router).mount('#app');
})();
