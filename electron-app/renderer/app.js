// @learn: This is the renderer process — pure DOM + the api object exposed by preload.js.
// No Node.js or Electron imports here; everything goes through window.api.

// ── State ─────────────────────────────────────────────────────────────────────

// @learn: we track messages as plain objects so we can re-render or update them by index
const messages = [];   // { role, text, imageUrls, logLines, status }
let pendingImages = [];    // array of data-URLs queued before sending
let isRunning = false;     // prevent sending while agent is busy
let activeTab = 'memory.md';   // which sidebar file is currently visible

// ── DOM refs ──────────────────────────────────────────────────────────────────

const messagesEl       = document.getElementById('messages');
const textInput        = document.getElementById('text-input');
const sendBtn          = document.getElementById('send-btn');
const attachBtn        = document.getElementById('attach-btn');
const fileInput        = document.getElementById('file-input');
const imageStrip       = document.getElementById('image-preview-strip');
const dirInput         = document.getElementById('dir-input');
const fileContent      = document.getElementById('file-content');
const tabBtns          = document.querySelectorAll('.tab-btn');
const refreshBtn       = document.getElementById('refresh-btn');
const saveBtn          = document.getElementById('save-btn');

// ── Init ──────────────────────────────────────────────────────────────────────

(async function init() {
  // Decision: pre-fill dir from .env so the user doesn't have to type it every time
  // logging: await ensures the dir field is set before the user can interact
  const envDir = await window.api.getEnv();
  if (envDir) dirInput.value = envDir;

  // Load the default sidebar file on startup
  await loadSidebarFile(activeTab);
})();

// ── Message rendering ──────────────────────────────────────────────────────────

function renderMessage(msg, index) {
  // @learn: we re-render specific messages (by index) rather than the whole list
  // to avoid scroll jumps during streaming updates
  const existing = messagesEl.querySelector(`[data-index="${index}"]`);

  const el = document.createElement('div');
  el.className = `message ${msg.role}`;
  el.dataset.index = index;

  // Build the bubble content
  let inner = '';

  if (msg.imageUrls && msg.imageUrls.length > 0) {
    inner += `<div class="thumb-row">` +
      msg.imageUrls.map(url =>
        `<img class="thumb" src="${url}" alt="screenshot" title="Click to enlarge" />`
      ).join('') +
    `</div>`;
  }

  if (msg.text) {
    inner += escapeHtml(msg.text);
  }

  if (msg.logLines && msg.logLines.length > 0) {
    inner += msg.logLines
      .map(l => `<div class="log-line ${l.startsWith('[stderr]') ? 'stderr' : ''}">${escapeHtml(l)}</div>`)
      .join('');
  }

  el.innerHTML = `<div class="bubble">${inner}</div>`;

  if (msg.status) {
    const badge = document.createElement('span');
    badge.className = `status-badge ${msg.status}`;
    badge.textContent = msg.status === 'running' ? '⟳ running…' : msg.status === 'done' ? '✓ done' : '✗ error';
    el.appendChild(badge);
  }

  if (existing) {
    messagesEl.replaceChild(el, existing);
  } else {
    messagesEl.appendChild(el);
  }

  // Decision: auto-scroll only when we're near the bottom to not disrupt reading
  const nearBottom = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 80;
  if (nearBottom || msg.status === 'running') {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
}

function appendMessage(msg) {
  messages.push(msg);
  renderMessage(msg, messages.length - 1);
  return messages.length - 1;
}

function updateMessage(index, patch) {
  Object.assign(messages[index], patch);
  renderMessage(messages[index], index);
}

// ── Send logic ─────────────────────────────────────────────────────────────────

// Run one agent job and return when it completes.
// Appends log lines to agentIdx bubble in real-time.
function runOneJob(opts, agentIdx) {
  return new Promise((resolve) => {
    const unsubLog = window.api.onAgentLog((line) => {
      messages[agentIdx].logLines.push(line);
      renderMessage(messages[agentIdx], agentIdx);
    });

    const unsubDone = window.api.onAgentDone(({ exitCode }) => {
      unsubLog();
      unsubDone();
      resolve(exitCode);
    });

    window.api.runAgent(opts);
  });
}

async function sendMessage() {
  if (isRunning) return;

  const text = textInput.value.trim();
  const images = [...pendingImages];   // snapshot before clearing

  if (!text && images.length === 0) return;

  isRunning = true;
  sendBtn.disabled = true;
  textInput.value = '';
  clearPendingImages();

  const targetDir = dirInput.value.trim() || undefined;

  // 1. Post the user bubble (shows all queued thumbnails + any text)
  appendMessage({
    role: 'user',
    text: text || null,
    imageUrls: images,
    logLines: [],
    status: null,
  });

  // 2. Create one agent bubble that accumulates output from all runs
  const agentIdx = appendMessage({
    role: 'agent',
    text: null,
    imageUrls: [],
    logLines: [],
    status: 'running',
  });

  // 3. Build the job list: one job per image, plus a text job if text was provided
  // @learn: each image is a separate agent invocation (main.py accepts one screenshot at a time).
  // We run them sequentially so logs stay ordered in the single agent bubble.
  const jobs = images.length > 0
    ? images.map(img => ({ type: 'image', payload: img, targetDir }))
    : [{ type: 'text', payload: text, targetDir }];

  // 4. Run jobs sequentially; any single failure marks the bubble as error
  let lastCode = 0;
  for (let i = 0; i < jobs.length; i++) {
    if (jobs.length > 1) {
      // Separator line so multi-image output is easy to read
      messages[agentIdx].logLines.push(`── image ${i + 1} / ${jobs.length} ──`);
      renderMessage(messages[agentIdx], agentIdx);
    }
    const code = await runOneJob(jobs[i], agentIdx);
    if (code !== 0) lastCode = code;
  }

  updateMessage(agentIdx, { status: lastCode === 0 ? 'done' : 'error' });

  isRunning = false;
  sendBtn.disabled = false;
  loadSidebarFile(activeTab);
}

// ── Image handling ─────────────────────────────────────────────────────────────

function readFileAsDataUrl(file) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (e) => resolve(e.target.result);
    reader.readAsDataURL(file);
  });
}

function addPendingImage(dataUrl) {
  pendingImages.push(dataUrl);
  renderImageStrip();
}

function removePendingImage(index) {
  pendingImages.splice(index, 1);
  renderImageStrip();
}

function clearPendingImages() {
  pendingImages = [];
  renderImageStrip();
  fileInput.value = '';
}

function renderImageStrip() {
  if (pendingImages.length === 0) {
    imageStrip.classList.add('hidden');
    imageStrip.innerHTML = '';
    return;
  }
  imageStrip.classList.remove('hidden');
  imageStrip.innerHTML = pendingImages.map((url, i) => `
    <div class="strip-thumb" data-index="${i}">
      <img src="${url}" alt="image ${i + 1}" />
      <button class="strip-remove" data-index="${i}" title="Remove">✕</button>
    </div>
  `).join('');

  imageStrip.querySelectorAll('.strip-remove').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      removePendingImage(Number(btn.dataset.index));
    });
  });
}

// File picker — multiple files allowed
attachBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', async () => {
  for (const file of fileInput.files) {
    const dataUrl = await readFileAsDataUrl(file);
    addPendingImage(dataUrl);
  }
  fileInput.value = '';
});

// Drag & drop — all dropped images are added
document.addEventListener('dragover', (e) => {
  e.preventDefault();
  document.body.classList.add('drag-over');
});

document.addEventListener('dragleave', (e) => {
  if (!e.relatedTarget) document.body.classList.remove('drag-over');
});

document.addEventListener('drop', async (e) => {
  e.preventDefault();
  document.body.classList.remove('drag-over');
  for (const file of e.dataTransfer.files) {
    if (file.type.startsWith('image/')) {
      const dataUrl = await readFileAsDataUrl(file);
      addPendingImage(dataUrl);
    }
  }
});

// Clipboard paste — each paste adds one image to the queue
document.addEventListener('paste', async (e) => {
  const items = Array.from(e.clipboardData.items);
  const imgItem = items.find(i => i.type.startsWith('image/'));
  if (imgItem) {
    e.preventDefault();
    const blob = imgItem.getAsFile();
    const dataUrl = await readFileAsDataUrl(blob);
    addPendingImage(dataUrl);
  }
});

// ── Composer keyboard shortcuts ────────────────────────────────────────────────

// Auto-resize textarea as content grows
textInput.addEventListener('input', () => {
  textInput.style.height = 'auto';
  textInput.style.height = Math.min(textInput.scrollHeight, 160) + 'px';
});

// Enter to send; Shift+Enter for newline
textInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

sendBtn.addEventListener('click', sendMessage);

// ── Sidebar ────────────────────────────────────────────────────────────────────

async function loadSidebarFile(name) {
  const targetDir = dirInput.value.trim() || undefined;
  fileContent.value = 'Loading…';
  const result = await window.api.readFile({ name, targetDir });
  fileContent.value = result.content;
  // Reset save button state after loading fresh content
  saveBtn.textContent = 'Save';
  saveBtn.classList.remove('saved');
  saveBtn.disabled = false;
}

tabBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    tabBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeTab = btn.dataset.file;
    loadSidebarFile(activeTab);
  });
});

refreshBtn.addEventListener('click', () => loadSidebarFile(activeTab));

saveBtn.addEventListener('click', async () => {
  const targetDir = dirInput.value.trim() || undefined;
  saveBtn.disabled = true;
  saveBtn.textContent = 'Saving…';
  const result = await window.api.writeFile({
    name: activeTab,
    content: fileContent.value,
    targetDir,
  });
  if (result.ok) {
    saveBtn.textContent = 'Saved ✓';
    saveBtn.classList.add('saved');
    // Re-enable after a moment so user can save again if they keep editing
    setTimeout(() => {
      saveBtn.textContent = 'Save';
      saveBtn.classList.remove('saved');
      saveBtn.disabled = false;
    }, 2000);
  } else {
    saveBtn.textContent = 'Error';
    saveBtn.disabled = false;
  }
});

// ── Sidebar resizer ────────────────────────────────────────────────────────────

const resizer = document.getElementById('resizer');
const sidebar = document.getElementById('sidebar');

resizer.addEventListener('mousedown', (e) => {
  e.preventDefault();
  resizer.classList.add('dragging');

  const startX = e.clientX;
  const startWidth = sidebar.offsetWidth;

  function onMove(e) {
    // Moving left (smaller X) → sidebar grows; moving right → shrinks
    const delta = startX - e.clientX;
    const newWidth = Math.max(180, Math.min(window.innerWidth * 0.8, startWidth + delta));
    sidebar.style.width = newWidth + 'px';
  }

  function onUp() {
    resizer.classList.remove('dragging');
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  }

  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
});

// ── Utility ────────────────────────────────────────────────────────────────────

// @learn: always escape HTML when inserting user/agent strings to prevent XSS in the renderer
function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
