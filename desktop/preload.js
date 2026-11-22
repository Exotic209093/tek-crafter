const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("tek", {
  send: (obj) => ipcRenderer.send("cmd", obj),
  on: (fn) => ipcRenderer.on("ev", (_e, ev) => fn(ev)),
  win: (action) => ipcRenderer.send("win", action),
});
