// Tek Crafter - Electron shell around the Python bot (bot_server.py).
const { app, BrowserWindow, ipcMain, screen } = require("electron");
const { spawn, spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const readline = require("readline");

const ROOT = path.resolve(__dirname, "..");          // ark-chem-bot
const ICON = path.join(__dirname, "assets", "icon.png");
const CAPTURE = process.env.TEK_CAPTURE || "";       // test mode: render to PNG and quit

let win, overlay, backend;
let lastState = null;
let overlayWanted = false;

function pythonExe() {
  const r = spawnSync("python", ["-c", "import sys;print(sys.executable)"], { windowsHide: true });
  const exe = String(r.stdout || "").trim();
  return exe && fs.existsSync(exe) ? exe : "python";
}

function startBackend() {
  const args = ["-u", path.join(ROOT, "bot_server.py")];
  if (CAPTURE) args.push("--no-hotkeys");  // never react to F9/F10 in test mode
  backend = spawn(pythonExe(), args, { cwd: ROOT, windowsHide: true });
  readline.createInterface({ input: backend.stdout }).on("line", (line) => {
    let ev;
    try { ev = JSON.parse(line); } catch { ev = { ev: "log", line }; }
    if (ev.ev === "state") lastState = ev;
    if (ev.ev === "status") {
      if (CAPTURE) return;   // keep the fake "running" status in screenshots
      updateOverlay(ev);
    }
    for (const w of [win, overlay]) if (w && !w.isDestroyed()) w.webContents.send("ev", ev);
  });
  readline.createInterface({ input: backend.stderr }).on("line", (line) => {
    if (win && !win.isDestroyed()) win.webContents.send("ev", { ev: "log", line: "! " + line });
  });
  backend.on("exit", (code) => {
    if (win && !win.isDestroyed())
      win.webContents.send("ev", { ev: "log", line: `! backend exited (${code})` });
  });
}

function send(obj) {
  if (backend && backend.stdin.writable) backend.stdin.write(JSON.stringify(obj) + "\n");
}

function updateOverlay(st) {
  const enabled = !lastState || lastState.config.app.overlay !== false;
  const want = enabled && (st.running || st.calibrating);
  if (!overlay || overlay.isDestroyed() || want === overlayWanted) return;
  overlayWanted = want;
  if (want) overlay.showInactive(); else overlay.hide();
}

function createWindows() {
  win = new BrowserWindow({
    width: 1240, height: 860, minWidth: 1040, minHeight: 720,
    frame: false, backgroundColor: "#041017", icon: ICON, title: "Tek Crafter",
    show: false,
    webPreferences: { preload: path.join(__dirname, "preload.js") },
  });
  win.loadFile(path.join(__dirname, "renderer", "index.html"));

  const wa = screen.getPrimaryDisplay().workArea;
  overlay = new BrowserWindow({
    x: wa.x + 14, y: wa.y + 30, width: 560, height: 130,
    frame: false, transparent: true, resizable: false, focusable: false,
    skipTaskbar: true, alwaysOnTop: true, show: false, hasShadow: false,
    webPreferences: { preload: path.join(__dirname, "preload.js") },
  });
  overlay.setAlwaysOnTop(true, "screen-saver");
  overlay.setIgnoreMouseEvents(true);
  overlay.loadFile(path.join(__dirname, "renderer", "overlay.html"));

  if (CAPTURE) {
    // render off-screen without ever taking focus from the game
    win.setPosition(-4000, 0);
    overlay.setPosition(-4000, 1000);
    win.once("ready-to-show", () => win.showInactive());
    setTimeout(capture, 3500);
  } else {
    win.once("ready-to-show", () => win.show());
  }
  win.on("closed", () => app.quit());
}

async function capture() {
  overlay.showInactive();
  overlay.webContents.send("ev", {
    ev: "status", running: true, job: "loop", paused: false, focused: true,
    status: "CB1B #12 (12/17)", next_run: null,
    progress: { station: "CB1", bed: "CB1B", label: "Chem benches", current: "CB1B #12",
                done: 11, failed: 0, visited: 11, total: 17, cycle: 3 },
  });
  if (!process.env.TEK_CAPTURE_IDLE) win.webContents.send("ev", { ev: "fake_status" });
  await new Promise((r) => setTimeout(r, 900));
  const shots = [[win, CAPTURE], [overlay, CAPTURE.replace(/\.png$/, "_overlay.png")]];
  for (const [w, file] of shots) fs.writeFileSync(file, (await w.webContents.capturePage()).toPNG());
  await win.webContents.executeJavaScript(`document.querySelector('.content').scrollTop = 99999`);
  await new Promise((r) => setTimeout(r, 300));
  fs.writeFileSync(CAPTURE.replace(/\.png$/, "_recipes.png"), (await win.webContents.capturePage()).toPNG());
  for (const tab of ["inventory", "calibrate", "settings"]) {
    await win.webContents.executeJavaScript(`document.querySelector('[data-tab=${tab}]').click()`);
    await new Promise((r) => setTimeout(r, 300));
    fs.writeFileSync(CAPTURE.replace(/\.png$/, `_${tab}.png`), (await win.webContents.capturePage()).toPNG());
  }
  app.quit();
}

ipcMain.on("cmd", (_e, obj) => send(obj));
ipcMain.on("win", (_e, action) => {
  if (action === "min") win.minimize();
  else if (action === "max") win.isMaximized() ? win.unmaximize() : win.maximize();
  else if (action === "close") win.close();
});

app.setAppUserModelId("TekCrafter");
if (!CAPTURE && !app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => { if (win) { win.show(); win.focus(); } });
  app.whenReady().then(() => { startBackend(); createWindows(); });
  app.on("before-quit", () => {
    try { send({ cmd: "stop" }); } catch {}
    setTimeout(() => { try { backend.kill(); } catch {} }, 300);
  });
  app.on("window-all-closed", () => app.quit());
}
