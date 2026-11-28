// Tek Crafter - in-game overlay around the Python bot (bot_server.py).
//
// The main panel is a see-through window that sits on top of ARK (windowed
// fullscreen). The panel hotkey (default Insert) or the tray icon opens it;
// Insert / Esc / the X hide it again and hand focus back to ARK. While the
// panel is open ARK isn't focused, so a running bot simply waits.
// A small click-through HUD shows progress while the bot runs.
const { app, BrowserWindow, ipcMain, screen, Tray, Menu, nativeImage } = require("electron");
const { spawn, spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const readline = require("readline");

const ROOT = path.resolve(__dirname, "..");          // ark-chem-bot
const ICON = path.join(__dirname, "assets", "icon.png");
const CAPTURE = process.env.TEK_CAPTURE || "";       // test mode: render to PNG and quit
const PANEL_W = 1240, PANEL_H = 860;
// HUD sits bottom-right: nothing the bot reads on screen is there
const HUD_W = 500, HUD_H = 118;

let panel, hud, tray, backend;
let lastState = null;
let hudWanted = false;
let quitting = false;

function pythonExe() {
  const r = spawnSync("python", ["-c", "import sys;print(sys.executable)"], { windowsHide: true });
  const exe = String(r.stdout || "").trim();
  return exe && fs.existsSync(exe) ? exe : "python";
}

function broadcast(ev) {
  for (const w of [panel, hud]) if (w && !w.isDestroyed()) w.webContents.send("ev", ev);
}

function startBackend() {
  const args = ["-u", path.join(ROOT, "bot_server.py")];
  if (CAPTURE) args.push("--no-hotkeys");  // never react to hotkeys in test mode
  backend = spawn(pythonExe(), args, { cwd: ROOT, windowsHide: true });
  readline.createInterface({ input: backend.stdout }).on("line", (line) => {
    let ev;
    try { ev = JSON.parse(line); } catch { ev = { ev: "log", line }; }
    if (ev.ev === "state") lastState = ev;
    if (ev.ev === "panel_toggle") return togglePanel();
    if (ev.ev === "status") {
      if (CAPTURE) return;   // keep the fake "running" status in screenshots
      updateHud(ev);
    }
    broadcast(ev);
  });
  readline.createInterface({ input: backend.stderr }).on("line", (line) =>
    broadcast({ ev: "log", line: "! " + line }));
  backend.on("exit", (code) => broadcast({ ev: "log", line: `! backend exited (${code})` }));
}

function send(obj) {
  if (backend && backend.stdin.writable) backend.stdin.write(JSON.stringify(obj) + "\n");
}

// ------------------------------------------------------------------ panel
function showPanel() {
  if (!panel) return;
  panel.show();
  panel.setAlwaysOnTop(true, "screen-saver");
  panel.focus();
  panel.webContents.send("ev", { ev: "panel_shown" });
}
function hidePanel() {
  if (!panel || !panel.isVisible()) return;
  panel.hide();
  send({ cmd: "focus_game" });           // give the keyboard back to ARK
}
function togglePanel() {
  if (panel && panel.isVisible()) hidePanel(); else showPanel();
}

function updateHud(st) {
  const enabled = !lastState || lastState.config.app.overlay !== false;
  const want = enabled && (st.running || st.calibrating);
  if (!hud || hud.isDestroyed() || want === hudWanted) return;
  hudWanted = want;
  if (want) { hud.showInactive(); hud.setAlwaysOnTop(true, "screen-saver"); } else hud.hide();
}

function createWindows() {
  const d = screen.getPrimaryDisplay();
  const b = d.bounds;
  panel = new BrowserWindow({
    x: Math.round(b.x + (b.width - PANEL_W) / 2), y: Math.round(b.y + (b.height - PANEL_H) / 2),
    width: PANEL_W, height: PANEL_H, frame: false, transparent: true, resizable: false,
    backgroundColor: "#00000000", hasShadow: false, skipTaskbar: true, alwaysOnTop: true,
    icon: ICON, title: "Tek Crafter", show: false,
    webPreferences: { preload: path.join(__dirname, "preload.js") },
  });
  panel.loadFile(path.join(__dirname, "renderer", "index.html"));
  panel.on("close", (e) => { if (!quitting && !CAPTURE) { e.preventDefault(); hidePanel(); } });

  hud = new BrowserWindow({
    x: b.x + b.width - HUD_W - 90, y: b.y + b.height - HUD_H - 14, width: HUD_W, height: HUD_H,
    frame: false, transparent: true, resizable: false, focusable: false,
    skipTaskbar: true, alwaysOnTop: true, show: false, hasShadow: false,
    webPreferences: { preload: path.join(__dirname, "preload.js") },
  });
  hud.setIgnoreMouseEvents(true);
  hud.loadFile(path.join(__dirname, "renderer", "overlay.html"));

  if (CAPTURE) {
    // render off-screen without ever taking focus from the game
    panel.setPosition(-4000, 0);
    hud.setPosition(-4000, 1000);
    panel.once("ready-to-show", () => panel.showInactive());
    setTimeout(capture, 3500);
    return;
  }
  panel.once("ready-to-show", () => showPanel());   // open once on launch

  tray = new Tray(nativeImage.createFromPath(ICON).resize({ width: 16, height: 16 }));
  tray.setToolTip("Tek Crafter");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open panel", click: showPanel },
    { type: "separator" },
    { label: "Quit Tek Crafter", click: () => { quitting = true; app.quit(); } },
  ]));
  tray.on("click", togglePanel);
}

async function capture() {
  hud.showInactive();
  hud.webContents.send("ev", {
    ev: "status", running: true, job: "loop", paused: false, focused: true,
    status: "CB1B #12 (12/17)", next_run: null,
    progress: { station: "CB1", bed: "CB1B", label: "Chem benches", current: "CB1B #12",
                done: 11, failed: 0, visited: 11, total: 17, cycle: 3 },
  });
  if (!process.env.TEK_CAPTURE_IDLE) panel.webContents.send("ev", { ev: "fake_status" });
  await new Promise((r) => setTimeout(r, 900));
  const shots = [[panel, CAPTURE], [hud, CAPTURE.replace(/\.png$/, "_overlay.png")]];
  for (const [w, file] of shots) fs.writeFileSync(file, (await w.webContents.capturePage()).toPNG());
  await panel.webContents.executeJavaScript(`document.querySelector('.content').scrollTop = 99999`);
  await new Promise((r) => setTimeout(r, 300));
  fs.writeFileSync(CAPTURE.replace(/\.png$/, "_recipes.png"), (await panel.webContents.capturePage()).toPNG());
  for (const tab of ["inventory", "calibrate", "settings"]) {
    await panel.webContents.executeJavaScript(`document.querySelector('[data-tab=${tab}]').click()`);
    await new Promise((r) => setTimeout(r, 300));
    fs.writeFileSync(CAPTURE.replace(/\.png$/, `_${tab}.png`), (await panel.webContents.capturePage()).toPNG());
  }
  quitting = true;
  app.quit();
}

ipcMain.on("cmd", (_e, obj) => send(obj));
ipcMain.on("win", (_e, action) => {
  if (action === "min" || action === "close" || action === "hide") hidePanel();
  else if (action === "quit") { quitting = true; app.quit(); }
});

app.setAppUserModelId("TekCrafter");
if (!CAPTURE && !app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", showPanel);
  app.whenReady().then(() => { startBackend(); createWindows(); });
  app.on("before-quit", () => {
    quitting = true;
    try { send({ cmd: "stop" }); } catch {}
    setTimeout(() => { try { backend.kill(); } catch {} }, 300);
  });
  app.on("window-all-closed", () => { if (quitting) app.quit(); });
}
