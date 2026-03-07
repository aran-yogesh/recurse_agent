// @learn: Electron main process — owns the BrowserWindow lifecycle and all IPC handlers.
// The renderer process (UI) never touches Node.js APIs directly; it goes through preload.js.

const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { spawn } = require('child_process');

// logging-coverage: window reference kept module-level so IPC handlers can reach it
let win = null;

// ── Window creation ────────────────────────────────────────────────────────────

function createWindow() {
  // @learn: preload.js bridges main ↔ renderer safely via contextBridge (no nodeIntegration)
  win = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#1a1a2e',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,   // @learn: required for contextBridge — keeps renderer sandboxed
      nodeIntegration: false,   // never expose raw Node to the renderer
    },
  });

  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  // logging: open DevTools in dev for easier debugging; remove for production
  // Decision: only open DevTools when ELECTRON_DEV env var is set to avoid noise in production
  if (process.env.ELECTRON_DEV) {
    win.webContents.openDevTools();
  }
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  // Decision: on macOS apps conventionally stay alive until Cmd+Q — standard Electron pattern
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

// ── Helper: resolve the agent project root ────────────────────────────────────

// @learn: __dirname is the electron-app/ folder; the Python project is one level up
const PROJECT_ROOT = path.resolve(__dirname, '..');

function resolveTargetDir(provided) {
  // Decision: if renderer passes an explicit dir use it, otherwise fall back to project root
  // logging: we log the resolved dir so subprocess output makes sense in the chat bubble
  return provided || PROJECT_ROOT;
}

// ── IPC: get-env ──────────────────────────────────────────────────────────────

ipcMain.handle('get-env', () => {
  // @learn: reads TARGET_DIR from the .env file so the renderer can pre-fill the dir field
  // logging: intentionally silent on missing key — it's optional, renderer handles the fallback
  const envPath = path.join(PROJECT_ROOT, '.env');
  try {
    const content = fs.readFileSync(envPath, 'utf8');
    const match = content.match(/^TARGET_DIR\s*=\s*(.+)$/m);
    return match ? match[1].trim() : PROJECT_ROOT;
  } catch {
    // Decision: .env is optional; default to project root so the app still works without it
    return PROJECT_ROOT;
  }
});

// ── IPC: read-file ─────────────────────────────────────────────────────────────

ipcMain.handle('read-file', (_event, { name, targetDir }) => {
  // @learn: the sidebar calls this to show live content of memory/skills/agents md files
  const dir = resolveTargetDir(targetDir);
  const filePath = path.join(dir, name);
  // logging: log file reads so we can trace which dir is actually being read
  console.log(`[read-file] reading ${filePath}`);
  try {
    return { ok: true, content: fs.readFileSync(filePath, 'utf8') };
  } catch (err) {
    // Decision: surface the error text to the renderer so the user sees why the file is missing
    return { ok: false, content: `(file not found: ${name})` };
  }
});

// ── IPC: write-file ───────────────────────────────────────────────────────────

ipcMain.handle('write-file', (_event, { name, content, targetDir }) => {
  // @learn: called by the sidebar's Save button so the user can edit pattern files in-app
  const dir = resolveTargetDir(targetDir);
  const filePath = path.join(dir, name);
  console.log(`[write-file] writing ${filePath}`);
  try {
    fs.writeFileSync(filePath, content, 'utf8');
    return { ok: true };
  } catch (err) {
    console.error(`[write-file] error: ${err.message}`);
    return { ok: false, error: err.message };
  }
});

// ── IPC: run-agent ─────────────────────────────────────────────────────────────

ipcMain.handle('run-agent', async (_event, { type, payload, targetDir }) => {
  // @learn: we spawn `uv run python main.py ...` as a subprocess so Python env management
  // (virtualenv, pyproject deps) is handled by uv rather than requiring a global Python install.

  const dir = resolveTargetDir(targetDir);
  let args;
  let tmpFile = null;

  if (type === 'text') {
    // Decision: pass text via --text flag; no temp file needed
    // logging: log mode + dir so each run in the chat is traceable
    console.log(`[run-agent] text mode, dir=${dir}`);
    args = ['run', 'python', 'main.py', '--text', payload, '--dir', dir];
  } else {
    // Decision: write base64 image to a temp file so we can pass a file path to main.py
    // @learn: Electron renderer sends images as data-URLs; we strip the header and decode to disk
    const base64Data = payload.replace(/^data:image\/\w+;base64,/, '');
    tmpFile = path.join(os.tmpdir(), `recurse_agent_${Date.now()}.png`);
    fs.writeFileSync(tmpFile, Buffer.from(base64Data, 'base64'));
    console.log(`[run-agent] image mode, tmpFile=${tmpFile}, dir=${dir}`);
    args = ['run', 'python', 'main.py', tmpFile, '--dir', dir];
  }

  return new Promise((resolve) => {
    const child = spawn('uv', args, {
      cwd: PROJECT_ROOT,
      // Decision: inherit env so ANTHROPIC_API_KEY and other vars from the shell reach Python
      env: { ...process.env },
    });

    // logging: stream filtered stdout lines — only header + bullet summaries, not verbose LLM reasoning
    child.stdout.on('data', (data) => {
      const lines = data.toString().split('\n').filter(Boolean);
      lines.forEach((line) => {
        const trimmed = line.trim();

        // Decision: only forward the concise header lines and bullet-point log entries.
        // The verbose reflection reasoning (everything after " — " on a Reflection line) is
        // dropped here to keep the chat bubble readable. Full output is still in main process log.
        const isHeader = /^(Review Agent|  Mode|  Screenshot|  Target dir|Run log:|Done\.)/.test(line);
        const isBullet = trimmed.startsWith('•');

        if (!isHeader && !isBullet) return;

        // For Reflection/Revised lines, strip the long reasoning after " — "
        // @learn: keeps the status visible ("needs_revision=True") without the multi-paragraph explanation
        let display = line;
        if (isBullet && line.includes(' — ')) {
          const dashIdx = line.indexOf(' — ');
          display = line.substring(0, dashIdx);
        }
        console.log(`[run-agent stdout] ${display}`);
        win?.webContents.send('agent-log', display);
      });
    });

    // logging: forward stderr but filter out known harmless Python 3.14 / pydantic v1 deprecation noise
    child.stderr.on('data', (data) => {
      const lines = data.toString().split('\n').filter(Boolean);
      lines.forEach((line) => {
        // Decision: these warnings are cosmetic — pydantic v1 compatibility with Python 3.14.
        // Showing them in the UI causes alarm without providing actionable info.
        if (
          line.includes('UserWarning') ||
          line.includes('pydantic.v1') ||
          line.includes('_api/deprecation') ||
          line.includes('from pydantic')
        ) return;
        win?.webContents.send('agent-log', `[stderr] ${line}`);
      });
    });

    child.on('close', (code) => {
      // logging: log exit code so we know if the agent succeeded or failed
      console.log(`[run-agent] process exited with code ${code}`);

      // Clean up temp file if we created one
      if (tmpFile) {
        try { fs.unlinkSync(tmpFile); } catch { /* ignore cleanup errors */ }
      }

      win?.webContents.send('agent-done', { exitCode: code });
      resolve({ exitCode: code });
    });

    child.on('error', (err) => {
      // Decision: on spawn error (e.g. uv not found) surface a clear message rather than silently failing
      console.error(`[run-agent] spawn error: ${err.message}`);
      win?.webContents.send('agent-log', `[error] ${err.message}`);
      win?.webContents.send('agent-done', { exitCode: -1, error: err.message });
      resolve({ exitCode: -1, error: err.message });
    });
  });
});
