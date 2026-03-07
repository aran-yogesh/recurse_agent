// @learn: preload.js is the only file that runs with Node.js access AND can reach the renderer.
// contextBridge.exposeInMainWorld is the safe way to give the renderer a limited API surface
// without exposing the full Node/Electron runtime (which would be a security risk).

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  // Invoke the agent subprocess; returns { exitCode } when the process exits.
  // @learn: ipcRenderer.invoke is the promise-based IPC pattern (vs send/on for fire-and-forget)
  runAgent: (opts) => ipcRenderer.invoke('run-agent', opts),

  // Read one of the .md pattern files from the target dir
  readFile: (opts) => ipcRenderer.invoke('read-file', opts),

  // Write edited content back to a .md file
  writeFile: (opts) => ipcRenderer.invoke('write-file', opts),

  // Get TARGET_DIR from the project's .env (used to pre-fill the dir field on startup)
  getEnv: () => ipcRenderer.invoke('get-env'),

  // Subscribe to streaming log lines from the running subprocess
  // @learn: we return the unsubscribe function so app.js can clean up listeners between runs
  onAgentLog: (callback) => {
    const handler = (_event, line) => callback(line);
    ipcRenderer.on('agent-log', handler);
    return () => ipcRenderer.removeListener('agent-log', handler);
  },

  // Subscribe to the agent-done event (fired once when the subprocess exits)
  onAgentDone: (callback) => {
    const handler = (_event, result) => callback(result);
    ipcRenderer.on('agent-done', handler);
    return () => ipcRenderer.removeListener('agent-done', handler);
  },
});
