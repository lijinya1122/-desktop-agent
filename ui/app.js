/* Mini Cursor 前端：三栏（文件树 / 文件与 diff / 对话与工具调用）。
   只做两件事：把用户输入发到 WebSocket，把后端事件流画出来。Key 不在这里。 */

const $ = (id) => document.getElementById(id);
const state = { ws: null, busy: false, file: null, settings: null, pendingId: null };

/* ------------------------------------------------------------------ 连接 */
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  state.ws = new WebSocket(`${proto}://${location.host}/ws`);
  state.ws.onopen = () => {
    sys('已连接到本地后端');
    $('btnStop').disabled = true;
  };
  state.ws.onclose = () => {
    sys('连接断开，3 秒后重连…');
    setTimeout(connect, 3000);
  };
  state.ws.onmessage = (e) => onEvent(JSON.parse(e.data));
}

function send(obj) {
  if (state.ws && state.ws.readyState === 1) state.ws.send(JSON.stringify(obj));
}

/* ------------------------------------------------------------ 事件渲染 */
function onEvent(ev) {
  switch (ev.type) {
    case 'hello':
      $('modelBadge').textContent = '模型 ' + (ev.model || '未配置');
      renderMcp(ev.mcp || []);
      break;
    case 'status':
      sys(ev.text);
      break;
    case 'step':
      $('stepInfo').textContent = `第 ${ev.index}/${ev.max} 步`;
      break;
    case 'token':
      appendAssistant(ev.text);
      break;
    case 'answer':
      appendAssistant(ev.text, true);
      break;
    case 'tool_call':
      addToolCard(ev);
      break;
    case 'tool_result':
      fillToolCard(ev);
      break;
    case 'confirm_request':
      addConfirmCard(ev);
      break;
    case 'warning':
      sys('⚠ ' + ev.text);
      break;
    case 'error':
      sys('✖ ' + ev.text);
      break;
    case 'done':
      state.busy = false;
      $('btnStop').disabled = true;
      $('stepInfo').textContent = ev.reason === 'done' ? '完成' : '结束 · ' + ev.reason;
      if (ev.reason !== 'done') sys('结束原因：' + ev.reason);
      refreshTree();
      break;
  }
  const chat = $('chat');
  chat.scrollTop = chat.scrollHeight;
}

function sys(text) {
  const d = document.createElement('div');
  d.className = 'msg system';
  d.textContent = text;
  $('chat').appendChild(d);
}

function appendAssistant(text, fresh) {
  let el = $('chat').querySelector('.msg.assistant.streaming');
  if (!el || fresh) {
    el = document.createElement('div');
    el.className = 'msg assistant streaming';
    $('chat').appendChild(el);
  }
  el.textContent += text;
  if (fresh) el.classList.remove('streaming');
}

const cards = new Map();

function argSummary(args) {
  if (!args) return '';
  const s = JSON.stringify(args);
  return s.length > 220 ? s.slice(0, 220) + '…' : s;
}

function addToolCard(ev) {
  const card = document.createElement('div');
  card.className = 'card' + (ev.mcp ? ' mcpcard' : '');
  card.innerHTML = `
    <div class="hd">
      <span class="nm">${esc(ev.name)}</span>
      ${ev.mcp ? '<span class="tag mcp">MCP</span>' : '<span class="tag">内置</span>'}
      <span class="st">执行中…</span>
    </div>
    <div class="bd"><div class="args">${esc(argSummary(ev.arguments))}</div><pre></pre></div>`;
  $('chat').appendChild(card);
  cards.set(ev.id, card);
}

function fillToolCard(ev) {
  const card = cards.get(ev.id);
  if (!card) return;
  card.classList.toggle('err', !ev.ok);
  card.querySelector('.st').outerHTML =
    `<span class="st ${ev.ok ? 'ok' : 'err'}">${ev.ok ? '完成' : '失败'} · ${ev.ms}ms</span>`;
  const pre = card.querySelector('pre');
  const body = [];
  if (ev.diff) body.push(diffHtml(ev.diff));
  if (ev.text) body.push('<div>' + esc(ev.text) + '</div>');
  pre.innerHTML = body.join('');
  if (ev.diff) {
    const btn = document.createElement('button');
    btn.textContent = '在中间栏看 diff';
    btn.style.margin = '0 10px 8px';
    btn.onclick = () => showDiff(ev.name, ev.diff);
    card.appendChild(btn);
  }
}

function addConfirmCard(ev) {
  const card = document.createElement('div');
  card.className = 'card confirm';
  card.innerHTML = `
    <div class="hd"><span class="nm">需要确认：${esc(ev.name)}</span>
      <span class="st">diff 预览</span></div>
    <div class="bd"><div class="args">${esc(argSummary(ev.arguments))}</div>
      <pre>${ev.diff ? diffHtml(ev.diff) : esc('（无 diff 预览）')}</pre></div>`;
  const act = document.createElement('div');
  act.className = 'actions';
  const ok = document.createElement('button');
  ok.className = 'primary';
  ok.textContent = '执行';
  ok.onclick = () => { send({ type: 'confirm', accept: true }); act.remove(); };
  const no = document.createElement('button');
  no.className = 'danger';
  no.textContent = '拒绝';
  no.onclick = () => { send({ type: 'confirm', accept: false }); act.remove(); };
  act.appendChild(ok); act.appendChild(no);
  card.appendChild(act);
  $('chat').appendChild(card);
}

function diffHtml(diff) {
  return diff.split('\n').map((l) => {
    let c = '';
    if (l.startsWith('+++') || l.startsWith('---')) c = 'hunk';
    else if (l.startsWith('@@')) c = 'hunk';
    else if (l.startsWith('+')) c = 'add';
    else if (l.startsWith('-')) c = 'del';
    return `<div class="diff-line ${c}">${esc(l || ' ')}</div>`;
  }).join('');
}

function showDiff(name, diff) {
  $('fileTitle').textContent = name + ' · diff';
  $('fileMode').textContent = '预览';
  $('editor').innerHTML = '<div class="editor">' + diffHtml(diff) + '</div>';
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ------------------------------------------------------------ 文件树 */
async function refreshTree() {
  const r = await fetch('/api/tree?depth=4').then((x) => x.json());
  $('wsPath').textContent = r.root || '';
  const host = $('tree');
  host.innerHTML = '';
  (r.nodes || []).forEach((n) => host.appendChild(nodeEl(n)));
}

function nodeEl(n) {
  const row = document.createElement('div');
  row.className = 'row';
  row.innerHTML = `<span class="ico">${n.type === 'dir' ? '▸' : '·'}</span>
                   <span class="nm">${esc(n.name)}</span>`;
  if (n.type === 'dir') {
    const box = document.createElement('div');
    box.style.marginLeft = '12px';
    (n.children || []).forEach((c) => box.appendChild(nodeEl(c)));
    row.onclick = (e) => {
      e.stopPropagation();
      box.style.display = box.style.display === 'none' ? 'block' : 'none';
      row.querySelector('.ico').textContent = box.style.display === 'none' ? '▸' : '▾';
    };
    const wrap = document.createElement('div');
    wrap.appendChild(row); wrap.appendChild(box);
    return wrap;
  }
  row.onclick = () => openFile(n.path);
  return row;
}

async function openFile(path) {
  const r = await fetch('/api/file?path=' + encodeURIComponent(path)).then((x) => x.json());
  if (r.error) { sys('打不开 ' + path + '：' + r.error); return; }
  state.file = path;
  $('fileTitle').textContent = path;
  $('fileMode').textContent = r.content.split('\n').length + ' 行';
  $('editor').innerHTML = r.content.split('\n').map(
    (l, i) => `<div class="ln"><span class="no">${i + 1}</span>${esc(l)}</div>`
  ).join('');
}

/* ------------------------------------------------------------ MCP 面板 */
function renderMcp(list) {
  const host = $('mcpList');
  host.innerHTML = '';
  (list || []).forEach((m) => {
    const d = document.createElement('div');
    d.className = 'mcp-item';
    d.innerHTML = `<span>${esc(m.name)}</span><span class="st">${esc(m.status || '')}</span>`;
    d.title = (m.tools || []).join(', ');
    host.appendChild(d);
  });
  const ok = (list || []).filter((m) => (m.status || '').startsWith('ok')).length;
  const badge = $('mcpBadge');
  badge.textContent = ok ? `MCP ${ok} 个已连接` : 'MCP 未连接';
  badge.className = 'badge ' + (ok ? 'mcp' : '');
}

/* ------------------------------------------------------------ 设置 */
function openSettings() {
  const s = state.settings || {};
  const host = $('modalHost');
  host.innerHTML = `
    <div class="modal-bg"><div class="modal">
      <h3>设置</h3>
      <div class="field"><label>API Key</label>
        <input id="s_key" type="password" placeholder="${s.api_key_set ? '已保存：' + esc(s.api_key_hint) : '粘贴你的 Key'}" /></div>
      <div class="field"><label>Base URL</label><input id="s_url" value="${esc(s.base_url || '')}" /></div>
      <div class="field"><label>模型</label><input id="s_model" value="${esc(s.model || '')}" /></div>
      <div class="field"><label>工作区</label><input id="s_ws" value="${esc(s.workspace || '')}" /></div>
      <div class="field"><label>温度</label><input id="s_temp" type="number" step="0.1" value="${s.temperature ?? 0.2}" /></div>
      <div class="field"><label>步数上限</label><input id="s_steps" type="number" value="${s.max_steps ?? 12}" /></div>
      <div class="field check"><label><input id="s_confirm" type="checkbox" ${s.confirm_writes ? 'checked' : ''} /> 写操作先给 diff 再执行</label></div>
      <div class="field check"><label><input id="s_demo" type="checkbox" ${s.demo_mode ? 'checked' : ''} /> 演示模式（离线回放，不需要 Key，链路完整）</label></div>
      <div class="hint">Key 保存在 ~/.desktop-agent/settings.json，不进仓库、不下发给前端明文。</div>
      <div class="foot">
        <button id="s_cancel">取消</button>
        <button class="primary" id="s_save">保存</button>
      </div>
    </div></div>`;
  $('s_cancel').onclick = () => (host.innerHTML = '');
  $('s_save').onclick = async () => {
    const body = {
      base_url: $('s_url').value.trim(),
      model: $('s_model').value.trim(),
      workspace: $('s_ws').value.trim(),
      temperature: parseFloat($('s_temp').value || '0.2'),
      max_steps: parseInt($('s_steps').value || '12', 10),
      confirm_writes: $('s_confirm').checked,
      demo_mode: $('s_demo').checked,
    };
    const k = $('s_key').value.trim();
    if (k) body.api_key = k;
    const r = await fetch('/api/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then((x) => x.json());
    state.settings = r.settings;
    $('modelBadge').textContent = '模型 ' + (r.settings.model || '');
    host.innerHTML = '';
    refreshTree();
    sys('设置已保存');
  };
}

/* ------------------------------------------------------------ 交互 */
function doSend() {
  const el = $('input');
  const text = el.value.trim();
  if (!text || state.busy) return;
  el.value = '';
  const d = document.createElement('div');
  d.className = 'msg user';
  d.textContent = text;
  $('chat').appendChild(d);
  state.busy = true;
  $('btnStop').disabled = false;
  send({ type: 'chat', text });
}

function init() {
  $('btnSend').onclick = doSend;
  $('btnStop').onclick = () => { send({ type: 'stop' }); $('btnStop').disabled = true; };
  $('btnSettings').onclick = openSettings;
  $('btnReloadMcp').onclick = async () => {
    const r = await fetch('/api/mcp/reload', { method: 'POST' }).then((x) => x.json());
    renderMcp(r.mcp || []);
    sys('MCP 已重载');
  };
  $('input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSend(); }
  });
  fetch('/api/settings').then((x) => x.json()).then((r) => {
    state.settings = r.settings;
    $('modelBadge').textContent = '模型 ' + (r.settings.model || '未配置');
    renderMcp(r.mcp || []);
  });
  refreshTree();
  connect();
}

init();
