"""Backend for the Tek Crafter desktop app.

Talks JSON lines: commands on stdin, events on stdout.

commands  {"cmd": "state"}                         -> state event
          {"cmd": "save", "config": {...}}          -> writes ark_chem_config.json
          {"cmd": "start", "job": "loop"|"inventory", "here": BED|null}
          {"cmd": "toggle"}  {"cmd": "stop"}
          {"cmd": "calibrate", "bed": BED}
          {"cmd": "capture_key", "which": "start_key"|"stop_key"}
events    {"ev": "state", "config": {...}, "running": bool}
          {"ev": "status", ...}   (5x a second)
          {"ev": "log", "line": str}
          {"ev": "key", "which": ..., "vk": int, "name": str}

Hotkeys are polled here (GetAsyncKeyState) so mouse side buttons work and
they fire while ARK has focus. --no-hotkeys disables that (for testing).
"""
import copy
import ctypes
import json
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ark_chem as eng  # noqa: E402

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
_out = sys.__stdout__
_out_lock = threading.Lock()
LOG_DIR = HERE / "logs"


def emit(obj):
    line = json.dumps(obj, default=str)
    with _out_lock:
        _out.write(line + "\n")
        _out.flush()


def log_to_file(name, line):
    """Append to logs/<name>_YYYYMMDD.log so overnight runs leave a record."""
    try:
        LOG_DIR.mkdir(exist_ok=True)
        with open(LOG_DIR / f"{name}_{time.strftime('%Y%m%d')}.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {line}\n")
    except OSError:
        pass


class LogWriter:
    """Replaces stdout/stderr: every printed line becomes a log event."""

    def __init__(self):
        self.buf = ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            if line.strip():
                emit({"ev": "log", "line": line})
                log_to_file("bot", line)

    def flush(self):
        pass


KEY_NAMES = {0x04: "Mouse Middle", 0x05: "Mouse Back", 0x06: "Mouse Forward",
             0x08: "Backspace", 0x0D: "Enter", 0x13: "Pause", 0x14: "Caps Lock",
             0x21: "Page Up", 0x22: "Page Down", 0x23: "End", 0x24: "Home",
             0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down", 0x2D: "Insert",
             0x2E: "Delete", 0x91: "Scroll Lock", 0x6A: "Num *", 0x6B: "Num +",
             0x6D: "Num -", 0x6E: "Num .", 0x6F: "Num /", 0xC0: "`"}
KEY_NAMES.update({0x70 + i: f"F{i + 1}" for i in range(24)})
KEY_NAMES.update({0x60 + i: f"Num {i}" for i in range(10)})
KEY_NAMES.update({0x30 + i: str(i) for i in range(10)})
KEY_NAMES.update({0x41 + i: chr(0x41 + i) for i in range(26)})
GAME_KEYS = {0x1B, 0x09, 0x20} | {ord(c) for c in "WASDEFCQ"}


def key_name(vk):
    return KEY_NAMES.get(vk, f"Key 0x{vk:02X}")


class _MemStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class _ProcMem(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + \
               [(n, ctypes.c_size_t) for n in (
                   "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                   "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                   "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]


kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.GetCurrentProcess.restype = ctypes.c_void_p
kernel32.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_ProcMem), ctypes.c_ulong]
kernel32.GetProcessHandleCount.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
user32.GetGuiResources.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
user32.IsHungAppWindow.argtypes = [ctypes.c_void_p]
user32.FindWindowW.restype = ctypes.c_void_p


def proc_stats(h):
    """'priv=MB ws=MB handles=N gdi=N' for an open process handle."""
    pm = _ProcMem()
    pm.cb = ctypes.sizeof(pm)
    kernel32.K32GetProcessMemoryInfo(h, ctypes.byref(pm), pm.cb)
    hc = ctypes.c_ulong()
    kernel32.GetProcessHandleCount(h, ctypes.byref(hc))
    return (f"priv={pm.PrivateUsage >> 20}MB ws={pm.WorkingSetSize >> 20}MB "
            f"handles={hc.value} gdi={user32.GetGuiResources(h, 0)}")


def health_line(title):
    """One line: system memory, ARK process memory/hung state, this backend's memory."""
    ms = _MemStatus()
    ms.dwLength = ctypes.sizeof(ms)
    kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
    gb = 1 << 30
    parts = [f"ram_free={ms.ullAvailPhys / gb:.1f}GB "
             f"commit={(ms.ullTotalPageFile - ms.ullAvailPageFile) / gb:.1f}/{ms.ullTotalPageFile / gb:.1f}GB"]
    hwnd = user32.FindWindowW(None, title)
    if hwnd:
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        h = kernel32.OpenProcess(0x1000, False, pid.value)   # PROCESS_QUERY_LIMITED_INFORMATION
        ark = proc_stats(h) if h else "no access"
        if h:
            kernel32.CloseHandle(h)
        parts.append(f"ARK[{ark} hung={bool(user32.IsHungAppWindow(hwnd))}]")
    else:
        parts.append("ARK[no window]")
    parts.append(f"bot[{proc_stats(kernel32.GetCurrentProcess())}]")
    return " ".join(parts)


def is_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


class Server:
    def __init__(self, hotkeys=True):
        self.cfg = eng.load_config()
        app = self.cfg.setdefault("app", {})
        app.setdefault("start_key", 0x78)
        app.setdefault("stop_key", 0x79)
        app.setdefault("overlay", True)
        app.setdefault("panel_key", 0x2D)   # Insert: open/close the in-game panel
        self.ctl = None
        self.worker = None
        self.job = None
        self.calib = None
        self.capturing = None
        self.hotkeys = hotkeys

    # ------------------------------------------------------------ helpers
    def running(self):
        return self.worker is not None and self.worker.is_alive()

    def calibrating(self):
        return self.calib is not None and self.calib.poll() is None

    def write_config(self):
        # keep calibration results written by calibrate_bed.py meanwhile
        if eng.CONFIG_PATH.exists():
            disk = json.loads(eng.CONFIG_PATH.read_text())
            self.cfg["bed_targets"] = disk.get("bed_targets", self.cfg.get("bed_targets", {}))
        eng.CONFIG_PATH.write_text(json.dumps(self.cfg, indent=2))

    def send_state(self):
        emit({"ev": "state", "config": self.cfg, "running": self.running(),
              "keys": {k: key_name(self.cfg["app"][k]) for k in ("start_key", "stop_key", "panel_key")}})

    # ------------------------------------------------------------ commands
    def handle(self, msg):
        cmd = msg.get("cmd")
        if cmd == "state":
            self.send_state()
        elif cmd == "save":
            if self.running():
                print("! stop the bot before changing settings")
                return
            new = msg["config"]
            for k in ("stations", "layouts", "inventory_craft", "cycle_wait_minutes", "app"):
                if k in new:
                    self.cfg[k] = new[k]
            self.write_config()
            # no state echo: the app already shows what it sent, and a
            # re-render would wipe the box you're typing in
        elif cmd == "start":
            self.start(msg.get("job", "loop"), msg.get("here"))
        elif cmd == "toggle":
            self.toggle()
        elif cmd == "stop":
            self.stop()
        elif cmd == "calibrate":
            self.calibrate(msg["bed"])
        elif cmd == "focus_game":
            self.focus_game()
        elif cmd == "capture_key":
            if self.running():
                print("! stop the bot before changing hotkeys")
                return
            self.capturing = msg["which"]
            threading.Thread(target=self._capture_key, args=(msg["which"],), daemon=True).start()

    def start(self, job, here=None):
        if self.running() or self.calibrating():
            print("! already busy")
            return
        cfg = copy.deepcopy(self.cfg)
        self.ctl = eng.Control(cfg["window_title"], paused=False, hotkeys=False)
        ctl = self.ctl
        if job == "inventory":
            target = lambda: eng.run_inventory_loop(cfg, ctl)  # noqa: E731
        else:
            stations = eng.stations_from(cfg)
            if not stations:
                print("! none of the ticked stations has a calibrated bed")
                return
            target = lambda: eng.run_loop(cfg, stations, here, ctl)  # noqa: E731

        def work():
            try:
                target()
            except Exception:
                print("CRASHED:\n" + traceback.format_exc())
        self.job = job
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        print(f"[started {job} {time.strftime('%H:%M:%S')}] switch to ARK - the bot waits until ARK is focused")

    def toggle(self):
        if not self.running():
            self.start(self.cfg["app"].get("last_job", "loop"))
            return
        self.ctl.paused = not self.ctl.paused
        print("[paused]" if self.ctl.paused else "[resumed]")

    def stop(self):
        if self.running():
            self.ctl.stopped = True
            print("[stopping...]")
        if self.calibrating():
            self.calib.terminate()
            print("[calibration stopped]")

    def focus_game(self):
        """Bring ARK back to the foreground after the panel closes."""
        hwnd = user32.FindWindowW(None, self.cfg["window_title"])
        if not hwnd:
            return
        fg = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg, None)
        me = ctypes.windll.kernel32.GetCurrentThreadId()
        if fg_thread and fg_thread != me:
            user32.AttachThreadInput(me, fg_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            user32.AttachThreadInput(me, fg_thread, False)
        else:
            user32.SetForegroundWindow(hwnd)

    def calibrate(self, bed):
        if self.running() or self.calibrating():
            print("! busy - stop the bot first")
            return
        st = next((s for s in self.cfg["stations"] if bed in s["beds"]), None)
        if st is None:
            print(f"! unknown bed {bed}")
            return
        self.write_config()
        pitches = ",".join(str(p) for p in self.cfg["layouts"][st["layout"]]["sweep_pitches"])
        exe = sys.executable.replace("pythonw.exe", "python.exe")
        cmd = [exe, "-u", "calibrate_bed.py", bed, st["layout"], "--step", "50", "--pitches", pitches]
        print(f"calibrating {bed} - hands off the mouse")
        self.calib = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, creationflags=0x08000000)

        def pump(proc):
            for line in proc.stdout:
                if line.strip():
                    emit({"ev": "log", "line": line.rstrip()})
            proc.wait()
            disk = json.loads(eng.CONFIG_PATH.read_text())
            self.cfg["bed_targets"] = disk.get("bed_targets", {})
            print("calibration finished")
            self.send_state()
        threading.Thread(target=pump, args=(self.calib,), daemon=True).start()

    # ------------------------------------------------------------ hotkeys
    def _capture_key(self, which):
        time.sleep(0.3)
        skip = {0x01, 0x02, 0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
        deadline = time.time() + 15
        while time.time() < deadline:
            for vk in range(0x04, 0xFF):
                if vk in skip or not is_down(vk):
                    continue
                while is_down(vk):
                    time.sleep(0.02)
                self.capturing = None
                others = [self.cfg["app"][k] for k in ("start_key", "stop_key", "panel_key") if k != which]
                if vk == 0x1B:
                    emit({"ev": "key", "which": which, "vk": None, "name": "cancelled"})
                elif vk in others:
                    print("! that key is already used for another action")
                elif vk in GAME_KEYS:
                    print(f"! {key_name(vk)} is used by ARK/the bot - pick an F-key, numpad or mouse button")
                else:
                    self.cfg["app"][which] = vk
                    self.write_config()
                    print(f"{which.replace('_key', '')} hotkey set to {key_name(vk)}")
                self.send_state()
                return
            time.sleep(0.02)
        self.capturing = None
        self.send_state()

    def old_app_running(self):
        """The old tkinter app also polls F9/F10; both reacting would fight."""
        ps = ("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe'\" | "
              "Where-Object { $_.CommandLine -match 'ark_chem_app.pyw' } | Measure-Object | "
              "Select-Object -ExpandProperty Count")
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                               text=True, timeout=15, creationflags=0x08000000)
            return r.stdout.strip() not in ("", "0")
        except Exception:
            return False

    def hotkey_loop(self):
        was = {}
        blocked_until = 0.0
        warned = False
        while True:
            now = time.time()
            if now >= blocked_until:
                if self.old_app_running():
                    if not warned:
                        print("! the old Chem Bench Bot app is still open - close it; "
                              "hotkeys are off until you do (buttons still work)")
                        warned = True
                    blocked_until = now + 5
                    time.sleep(0.2)
                    continue
                if warned:
                    print("old app closed - hotkeys active")
                    warned = False
                blocked_until = float("inf")   # once closed, stop checking
            if not self.capturing:
                for which in ("start_key", "stop_key", "panel_key"):
                    vk = self.cfg["app"][which]
                    down = is_down(vk)
                    if down and not was.get(vk):
                        if which == "panel_key":
                            emit({"ev": "panel_toggle"})
                        elif which == "start_key":
                            self.toggle()
                        else:
                            self.stop()
                    was[vk] = down
            time.sleep(0.02)

    # ------------------------------------------------------------ status
    def status_loop(self):
        while True:
            st = {"ev": "status", "running": self.running(), "calibrating": self.calibrating(),
                  "job": self.job}
            if self.running():
                c = self.ctl
                st.update(paused=c.paused, stopping=c.stopped, status=c.status,
                          progress=c.progress, next_run=c.next_run,
                          focused=c.title.lower() in eng.window_title().lower())
            emit(st)
            time.sleep(0.2)

    def health_loop(self):
        """Every minute, log memory and hung state to logs/health_*.log (diagnoses overnight freezes)."""
        while True:
            try:
                line = health_line(self.cfg["window_title"])
                if self.running():
                    c = self.ctl
                    line += f" bot_status={'paused' if c.paused else c.status!r}"
                log_to_file("health", line)
            except Exception as e:
                log_to_file("health", f"error: {e!r}")
            time.sleep(60)

    def serve(self):
        if self.hotkeys:
            threading.Thread(target=self.hotkey_loop, daemon=True).start()
        threading.Thread(target=self.status_loop, daemon=True).start()
        threading.Thread(target=self.health_loop, daemon=True).start()
        self.send_state()
        for line in sys.stdin:
            line = line.strip().lstrip("﻿")
            if not line:
                continue
            try:
                self.handle(json.loads(line))
            except Exception:
                print("! " + traceback.format_exc().splitlines()[-1])
        self.stop()


if __name__ == "__main__":
    sys.stdout = sys.stderr = LogWriter()
    Server(hotkeys="--no-hotkeys" not in sys.argv).serve()
