"""ARK: Survival Evolved chem bench crafting loop.

Per area (one bed name, 6 chem benches around it: right/back/left x low/high):
  aim -> F -> wait for the bench grid -> click item -> A x10 -> Esc
Then find the bed under you -> E -> filter the bed name -> click the bed icon
-> Travel (retries while the bed is on cooldown). After every area has been
visited once, wait, then repeat. With one bed (--beds CB1) it re-travels to a
CB1 bed each cycle, which also re-anchors the camera.

Speed: there are no fixed "wait N seconds" pauses for UI. Every step polls the
screen and moves on the moment the expected thing appears. Lag only makes a
step wait longer (up to its timeout), it doesn't break the sequence.

Safety: keys that could do damage only fire when the screen proves it's safe:
  E    only with the cyan "[E] : Fast Travel" prompt on screen
       (straight down can hit the Tek Ceiling, whose E prompt is "Pickup").
  A    only while the bench inventory is open (A = strafe left in the world).
  Esc  only while the bench inventory is open (otherwise it opens the menu).
  F    is never re-pressed while a slow-loading bench might still be opening.

Errors: a failed step is retried. After `max_consecutive_failures` failures in
a row (lag spike, disconnect, someone moved you) the bot beeps and pauses;
fix things in game and press F9 to resume.

Commands:
  python ark_chem.py run [--beds CB1 CB2] [--here] [--wait MIN] [--now]
  python ark_chem.py test-bench N     run one bench (0-5) once
  python ark_chem.py test-travel BED  travel to BED once
  python ark_chem.py calibrate-look   nudge each bench aim with the numpad
  F9 start/pause, F10 stop.
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np

import slotpick
from PIL import Image, ImageGrab

CONFIG_PATH = Path(__file__).with_name("ark_chem_config.json")
TEMPLATES = Path(__file__).with_name("templates")

DEFAULT_CONFIG = {
    "window_title": "ARK: Survival Evolved",
    # From Input.ini: AccessInventory=F, Use=E
    "keys": {"access": "f", "use": "e", "close": "esc", "craft": "a", "inventory": "tab"},
    # Stops visited in order, forever. Each has a main bed and spares (used
    # when the main one is on cooldown); every bed has its own calibrated
    # aims in "bed_targets" (made by calibrate_bed.py).
    "stations": [
        {"name": "CB1", "layout": "chem", "beds": ["CB1A", "CB1B"], "enabled": True},
        # (a 4th CB2 bed exists but is never selectable on the map)
        {"name": "CB2", "layout": "chem", "beds": ["CB2C", "CB2A"], "enabled": True},
        {"name": "F1", "layout": "fab", "beds": ["F1A", "F1B", "F1C"], "enabled": True},
    ],
    "bed_targets": {},
    "cycle_wait_minutes": 20,
    # Crafting from your own inventory (Tab -> CRAFTING tab). Runs as its own
    # job with no travelling: fast travel drops your items.
    "inventory_craft": {
        "wait_minutes": 5,
        "recipes": [
            {"name": "Stone Arrow", "search": "stone arrow", "pull_amount": "100", "presses": 1, "enabled": True},
            {"name": "Bola", "search": "bola", "pull_amount": "100", "presses": 1, "enabled": True},
            {"name": "Net Projectile", "search": "net projectile", "pull_amount": "100", "presses": 1, "enabled": True},
        ],
    },
    # Room layouts. Yaw/pitch are mouse counts (~5000 per full turn). Pitch
    # is measured UP from "looking straight down". Yaw is in the layout's
    # reference frame: on arrival the bot matches a 360 strip of the room
    # against templates/<ref> to find which way it's facing (duplicate beds
    # spawn you facing different ways).
    "layouts": {
        "chem": {
            "label": "Chem benches",
            "prompt": {"template": "turn_off", "kind": "cyan", "min": 0.78},
            "sweep_pitches": [1000, 1650],   # low + high row
            "refs": ["room_chem.npy", "room_chem_day.npy"],
            "empty_yaw": -700,          # open side: nothing to open here
            "ready_check": "grid_ready",
            "search": "",
            "item": [1568, 372],        # Gunpowder (Charcoal 4 + Sparkpowder 4)
            "pull_amount": "1000",      # typed into the amount box; "" = no pull
            "craft_presses": 10,        # each A queues 100
            # walls A/B/C x columns 1-3 x low/high = 18
            "targets": [
            {"name": "A1 lo", "yaw": -175, "pitch": 1000},
            {"name": "A1 hi", "yaw": -175, "pitch": 1650},
            {"name": "A2 lo", "yaw": 225, "pitch": 1000},
            {"name": "A2 hi", "yaw": 225, "pitch": 1650},
            {"name": "A3 lo", "yaw": 660, "pitch": 1000},
            {"name": "A3 hi", "yaw": 660, "pitch": 1650},
            {"name": "B1 lo", "yaw": 1010, "pitch": 1000},
            {"name": "B1 hi", "yaw": 1010, "pitch": 1650},
            {"name": "B2 lo", "yaw": 1446, "pitch": 1000},
            {"name": "B2 hi", "yaw": 1446, "pitch": 1650},
            {"name": "B3 lo", "yaw": 1900, "pitch": 1000},
            {"name": "B3 hi", "yaw": 1900, "pitch": 1650},
            {"name": "C1 lo", "yaw": 2210, "pitch": 1000},
            {"name": "C1 hi", "yaw": 2210, "pitch": 1650},
            {"name": "C2 lo", "yaw": 2663, "pitch": 1000},
            {"name": "C2 hi", "yaw": 2663, "pitch": 1650},
            {"name": "C3 lo", "yaw": 3110, "pitch": 1000},
            {"name": "C3 hi", "yaw": 3110, "pitch": 1650},
            ],
        },
        "fab": {
            "label": "Fabricators",
            "prompt": {"template": "turn_off", "kind": "cyan", "min": 0.78},
            "sweep_pitches": [900, 1150, 1650, 1775],   # low row + high row
            "refs": ["room_fab.npy"],
            "ready_check": None,
            # typed in the fabricator's search box; leaves exactly one item
            "search": "advanced rifle",
            "item": [1290, 278],        # first slot after searching
            "pull_amount": "1000",
            "craft_presses": 10,
            "targets": [],              # calibrated at F1
        },
    },
    "look": {
        "down_reset_counts": 4000,
        # Keep these: bigger/faster chunks drift (ARK mouse smoothing).
        "chunk": 40,
        "chunk_delay_s": 0.004,
        # yaw offsets tried (looking straight down) to find the bed prompt
        "bed_search_yaws": [0, 300, -300, 600, -600, 900, -900, 1200, -1200,
                            1500, -1500, 1800, -1800, 2100, -2100, 2400],
        # If no yaw finds the bed, step back (seconds held) and sweep again;
        # undone if it doesn't help. Small on purpose: bigger moves risk
        # walking off the platform.
        "bed_step_back_s": [0.12, 0.12],
        # if a target's prompt isn't under the crosshair, try these yaw offsets
        "nudges": [60, 120, 180],
    },
    # Screen positions for a 1920x1080 window.
    "ui": {
        "bed_filter": [430, 978],   # BED FILTER text box on the map
        "bed_icon": [651, 440],     # the base's bed icon on the map
        "bed_travel": [746, 976],   # TRAVEL TO button
        "map_close": [1249, 95],    # map X button
        # list of same-named beds that pops up after clicking the bed icon
        "bed_list_first": [820, 469],
        "bed_list_step": 50,
        # Structure inventory: search box, amount box, pull button (arrows in)
        "target_search": [1310, 183],
        # your own inventory (left panel)
        "inv_crafting_tab": [610, 114],
        "inv_search": [200, 182],
        "inv_first_slot": [164, 278],
        # your inventory's own amount box + pull button (top-left bar)
        "inv_amount_box": [555, 36],
        "inv_pull_button": [480, 36],
        "inv_storage_area": [117, 420, 675, 700],
        "amount_box": [1366, 36],
        "pull_button": [1440, 36],
        # region that shows the structure's stored resources (changes on a pull)
        "storage_area": [1243, 420, 1800, 700],
    },
    # name -> template file in templates/, top-left where it normally sits.
    # kind: cyan/bright = text-colour match (score = fraction of text pixels
    # found, higher is better); pixels = grayscale diff (lower is better).
    "checks": {
        # The prompt is drawn next to whatever the crosshair hits, so it can be
        # almost anywhere (seen at y 580-910, x 720-1055). Search the whole
        # play area (minus the HUD strip on the right) for that text line.
        # Measured: real prompt 0.90, "Pickup Tek Ceiling" <= 0.38.
        "bed_prompt": {"area": [0, 120, 1840, 1040], "kind": "cyan", "min": 0.7},
        # "STRUCTURE" header of any structure inventory
        "bench_open": {"x": 990, "y": 90, "kind": "cyan", "min": 0.6, "search": 8},
        # a chem bench item slot that never changes; proves the grid loaded
        "grid_ready": {"x": 1734, "y": 352, "kind": "pixels", "max_diff": 20, "search": 4},
        # the map's close X (top right); chat can't cover it, unlike BED FILTER
        # left "INVENTORY" header: some inventory (yours or a structure's) is open
        "inv_open": {"x": 116, "y": 93, "kind": "cyan", "min": 0.6, "search": 10},
        # same panel with the CRAFTING tab selected (INVENTORY header goes dim)
        "inv_crafting": {"x": 534, "y": 92, "kind": "cyan", "min": 0.6, "search": 10},
        "map_open": {"x": 1224, "y": 70, "kind": "teal", "min": 0.6, "search": 8},
    },
    "timing": {
        "settle_after_aim_s": 0.45,      # mouse smoothing: camera keeps moving briefly
        "craft_press_gap_s": 0.05,
        "pull_wait_s": 2.0,              # max wait for pulled resources to show
        "search_settle_s": 0.4,          # inventory search filter applies
        "bench_open_timeout_s": 6,       # F -> inventory visible
        "grid_ready_timeout_s": 5,       # inventory -> item grid loaded
        "close_timeout_s": 4,
        "map_open_timeout_s": 8,
        "map_leave_timeout_s": 8,        # Travel click -> map gone
        "spawn_timeout_s": 90,           # loading screen -> world visible
        "spawn_settle_s": 1.5,
        "loading_seen_timeout_s": 6,     # no loading screen by then = no travel           # let the world stream in after spawn
        "orient_min_conf": 1.2,          # strip-match confidence below this = unknown room
        "cooldown_retry_s": 30,
        "cooldown_give_up_min": 15,
        "max_consecutive_failures": 4,
        "refocus_idle_s": 60,            # ARK lost focus and no user input this long: bring it back (0 = off)
        "auto_resume_min": 5,            # paused after failures and no user input this long: retry (0 = off)
    },
}

# ---------------------------------------------------------------- Win32 input

user32 = ctypes.WinDLL("user32", use_last_error=True)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    user32.SetProcessDPIAware()

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x2, 0x8
MOUSEEVENTF_MOVE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x1, 0x2, 0x4
ULONG_PTR = wt.WPARAM


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


SCAN = {
    # extended keys carry 0xE0 in the high byte
    "end": 0xE04F, "home": 0xE047, "delete": 0xE053,
    "esc": 0x01, "backspace": 0x0E, "tab": 0x0F, "enter": 0x1C, "ctrl": 0x1D,
    "shift": 0x2A, "space": 0x39, "-": 0x0C,
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
    "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14, "y": 0x15,
    "u": 0x16, "i": 0x17, "o": 0x18, "p": 0x19,
    "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21, "g": 0x22, "h": 0x23,
    "j": 0x24, "k": 0x25, "l": 0x26,
    "z": 0x2C, "x": 0x2D, "c": 0x2E, "v": 0x2F, "b": 0x30, "n": 0x31, "m": 0x32,
}

VK_F9, VK_F10 = 0x78, 0x79
VK_NUM = {n: 0x60 + n for n in range(10)}
VK_ADD, VK_SUBTRACT = 0x6B, 0x6D


def _send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _key_event(scan, up=False):
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
    if scan > 0xFF:          # extended key (End, Home, Delete, arrows...)
        flags |= 0x1         # KEYEVENTF_EXTENDEDKEY
        scan &= 0xFF
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, scan, flags, 0, 0))


def clear_box(x, y, n=30):
    """Click a text box and empty it. The click can land mid-text, so jump
    to the end first: Backspace only deletes what's left of the cursor."""
    click(x, y)
    time.sleep(0.05)
    tap("end", hold=0.02)
    for _ in range(n):
        tap("backspace", hold=0.01)


def key_down(name):
    _send(_key_event(SCAN[name]))


def key_up(name):
    _send(_key_event(SCAN[name], up=True))


def tap(name, hold=0.03):
    key_down(name)
    time.sleep(hold)
    key_up(name)


def type_text(text):
    for ch in text:
        upper = ch.isalpha() and ch.isupper()
        if upper:
            key_down("shift")
        tap(ch.lower() if ch != " " else "space", hold=0.02)
        if upper:
            key_up("shift")
        time.sleep(0.02)


def mouse_rel(dx, dy):
    _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, 0)))


def mouse_button(down):
    flag = MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP
    _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, flag, 0, 0)))


def move_to(x, y):
    user32.SetCursorPos(int(x), int(y))
    # nudge so the game registers a hover on the new spot
    mouse_rel(1, 0)
    time.sleep(0.01)
    mouse_rel(-1, 0)
    time.sleep(0.03)


def click(x, y):
    move_to(x, y)
    mouse_button(True)
    time.sleep(0.03)
    mouse_button(False)
    time.sleep(0.05)


def key_pressed(vk):
    """True once per physical press (low bit of GetAsyncKeyState)."""
    return bool(user32.GetAsyncKeyState(vk) & 0x1)


def window_title():
    hwnd = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def game_focused(title):
    """ARK is the foreground window and not minimised (fullscreen ARK can be
    foreground yet iconic after another window stole focus)."""
    hwnd = user32.GetForegroundWindow()
    return title.lower() in window_title().lower() and not user32.IsIconic(hwnd)


class _LastInput(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds():
    """Seconds since the last keyboard/mouse input. Only meaningful while
    the bot itself isn't sending input (waiting or paused)."""
    li = _LastInput(ctypes.sizeof(_LastInput), 0)
    if not user32.GetLastInputInfo(ctypes.byref(li)):
        return 0.0
    return ((ctypes.windll.kernel32.GetTickCount() - li.dwTime) & 0xFFFFFFFF) / 1000.0


def focus_window(title):
    """Restore and foreground the window with this exact title. True if found."""
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)   # SW_RESTORE
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    me = ctypes.windll.kernel32.GetCurrentThreadId()
    attached = bool(fg_thread and fg_thread != me and user32.AttachThreadInput(me, fg_thread, True))
    user32.keybd_event(0x12, 0, 0, 0)   # an Alt tap lets a background process take the foreground
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    if attached:
        user32.AttachThreadInput(me, fg_thread, False)
    return True


def beep():
    try:
        import winsound
        for _ in range(3):
            winsound.Beep(880, 200)
            time.sleep(0.1)
    except Exception:
        pass


# ----------------------------------------------------------- screen checks

_tpl_cache = {}


def _ink_mask(rgb, kind):
    r, g, b = (rgb[..., i].astype(np.int16) for i in range(3))
    if kind == "cyan":
        return (b > 190) & (g > 170) & (r < 140)
    if kind == "teal":   # UI icons such as the map's close X (0,155,186)
        return (r < 60) & (g > 120) & (b > 150)
    if kind == "green":  # structure name line, e.g. "Kav Chemistry Bench"
        return (g > 190) & (r < 140) & (b < 140)
    return (r + g + b) > 540  # bright / white text


def _template(name, kind):
    key = (name, kind)
    if key not in _tpl_cache:
        img = Image.open(TEMPLATES / f"{name}.png").convert("RGB")
        if kind == "pixels":
            _tpl_cache[key] = np.asarray(img.convert("L"), dtype=np.int16)
        else:
            _tpl_cache[key] = _ink_mask(np.asarray(img), kind)
    return _tpl_cache[key]


def score_image(img, name, x, y, kind, search=30, search_y=None, origin=(0, 0)):
    """Score template `name` near (x, y) inside screenshot `img` (whose top
    left sits at `origin` on screen). Ink kinds: best fraction of template
    text pixels matched (0..1). pixels kind: lowest mean grayscale diff."""
    tpl = _template(name, kind)
    th, tw = tpl.shape
    sy = search if search_y is None else search_y
    ox, oy = origin
    box = (x - search - ox, y - sy - oy, x + tw + search - ox, y + th + sy - oy)
    region = img.crop(box)
    if kind == "pixels":
        arr = np.asarray(region.convert("L"), dtype=np.int16)
        best = 1e9
        for dy in range(0, 2 * sy + 1):
            for dx in range(0, 2 * search + 1):
                best = min(best, float(np.abs(arr[dy:dy + th, dx:dx + tw] - tpl).mean()))
        return best
    mask = _ink_mask(np.asarray(region.convert("RGB")), kind)
    total = int(tpl.sum())
    if not total:
        return 0.0
    best = 0
    for dy in range(0, 2 * sy + 1, 2):
        for dx in range(0, 2 * search + 1, 2):
            best = max(best, int((mask[dy:dy + th, dx:dx + tw] & tpl).sum()))
    return best / total


def find_text_line(img, name, kind, area, origin=(0, 0)):
    """Best score (0..1) for template `name` anywhere in `area`."""
    return find_text_hit(img, name, kind, area, origin)[0]


def find_text_hit(img, name, kind, area, origin=(0, 0)):
    """Find template `name` anywhere in `area` (x0, y0, x1, y1, screen coords)
    of `img`. Cheap: locate each band of text-coloured rows, then only test
    the template at each band's left edge.
    Returns (score 0..1, x, y) with x, y the screen position of the line's
    left/top edge (None, None when nothing matched)."""
    tpl = _template(name, kind)
    th, tw = tpl.shape
    total = int(tpl.sum())
    ox, oy = origin
    x0, y0, x1, y1 = area
    rgb = np.asarray(img.convert("RGB"))
    mask = _ink_mask(rgb[y0 - oy:y1 - oy, x0 - ox:x1 - ox], kind)
    rows = np.nonzero(mask.sum(axis=1) > 2)[0]
    if not len(rows) or not total:
        return 0.0, None, None
    # group rows into bands of text
    bands, start, prev = [], rows[0], rows[0]
    for r in rows[1:]:
        if r - prev > 3:
            bands.append((start, prev))
            start = r
        prev = r
    bands.append((start, prev))
    best, where = 0, (None, None)
    pad = 8
    padded = np.pad(mask, pad)
    for top, bottom in bands:
        band_cols = np.nonzero(mask[top:bottom + 1].any(axis=0))[0]
        if not len(band_cols):
            continue
        # the line can start at any text run in the band (other labels may
        # share the rows), so try each run's left edge
        starts = [band_cols[0]] + [c for p, c in zip(band_cols, band_cols[1:]) if c - p > 8]
        # other same-coloured things (lights, flasks) can stretch a band, so
        # try every height inside it, not just its top
        heights = range(top - 6, max(top + 7, bottom - th + 7), 2)
        for left in starts:
            for ty in heights:
                for dx in range(-6, 7, 2):
                    yy, xx = ty + pad - 4, left + dx + pad - 4
                    if yy < 0 or xx < 0:
                        continue
                    win = padded[yy:yy + th, xx:xx + tw]
                    if win.shape != tpl.shape:
                        continue
                    s = int((win & tpl).sum())
                    if s > best:
                        best, where = s, (x0 + left + dx, y0 + ty)
    return best / total, where[0], where[1]


def check_image(cfg, img, name, origin=(0, 0)):
    c = cfg["checks"][name]
    kind = c.get("kind", "cyan")
    if "area" in c:
        return find_text_line(img, name, kind, c["area"], origin) >= c.get("min", 0.6)
    s = score_image(img, name, c["x"], c["y"], kind, c.get("search", 30),
                    c.get("search_y"), origin)
    if kind == "pixels":
        return s <= c.get("max_diff", 20)
    return s >= c.get("min", 0.6)


def on_screen(cfg, name):
    """Grab just the region the check needs and test it."""
    c = cfg["checks"][name]
    kind = c.get("kind", "cyan")
    if "area" in c:
        box = tuple(c["area"])
        return check_image(cfg, ImageGrab.grab(bbox=box), name, origin=box[:2])
    th, tw = _template(name, kind).shape
    search = c.get("search", 30)
    sy = c.get("search_y") or search
    box = (c["x"] - search, c["y"] - sy, c["x"] + tw + search, c["y"] + th + sy)
    return check_image(cfg, ImageGrab.grab(bbox=box), name, origin=box[:2])


TURN = 5000           # mouse counts per full 360 turn (measured)
STRIP_BIN = 10        # yaw counts per strip column
STRIP_ROWS = 48
_ref_cache = {}


def _load_ref(name):
    if name not in _ref_cache:
        path = TEMPLATES / name
        if not path.exists():
            raise StepFailed(f"no room reference {name} - calibrate this layout first")
        _ref_cache[name] = np.load(path)
    return _ref_cache[name]


def capture_strip(bot, turn_counts=5000, pitch=1330, px_per_count=0.87):
    """360-degree grayscale strip of the room around you: rows x (turn/BIN)
    columns, column i = yaw i*BIN from the current facing. ~2s."""
    nb = turn_counts // STRIP_BIN
    acc = np.zeros((STRIP_ROWS, nb), dtype=np.float32)
    cnt = np.zeros(nb, dtype=np.float32)
    bot.look_down()
    bot.turn(0, -pitch)
    yaw = 0
    for target in range(0, turn_counts, 1000):
        bot.turn(target - yaw, 0)
        yaw = target
        time.sleep(0.25)
        img = ImageGrab.grab(bbox=(0, 140, 1920, 660)).convert("L").resize((480, STRIP_ROWS))
        arr = np.asarray(img, dtype=np.float32)
        for x in range(480):
            b = int(round((target + (x * 4 + 2 - 960) / px_per_count) / STRIP_BIN)) % nb
            acc[:, b] += arr[:, x]
            cnt[b] += 1
    bot.turn(-yaw, 0)
    bot.pitch = None
    # fill unseen bins by interpolating along the circle
    seen = cnt > 0
    idx = np.arange(nb)
    strip = np.empty_like(acc)
    for r in range(STRIP_ROWS):
        strip[r] = np.interp(idx, idx[seen], acc[r, seen] / cnt[seen], period=nb)
    return strip


def match_strip(ref, cur):
    """Yaw offset (counts) of the current facing in the reference frame.
    Returns (offset, confidence). Confidence = best correlation peak divided
    by the best peak at least 400 counts away from it: ~10 when lighting is
    unchanged, ~1.4 day-vs-night, ~1.0 means no idea."""
    def feat(s):
        # log + per-row standardise: survives day/night brightness changes
        lg = np.log1p(np.maximum(s, 0))
        return (lg - lg.mean(axis=1, keepdims=True)) / (lg.std(axis=1, keepdims=True) + 1e-6)
    r, c = feat(ref), feat(cur)
    corr = np.fft.ifft(np.fft.fft(r, axis=1) * np.conj(np.fft.fft(c, axis=1)), axis=1).real.sum(axis=0)
    n = len(corr)
    k = int(np.argmax(corr))
    mask = np.ones(n, bool)
    for d in range(-40, 41):
        mask[(k + d) % n] = False
    second = corr[mask].max()
    conf = float(corr[k] / second) if second > 0 else 99.0
    shift = k if k <= n // 2 else k - n
    return shift * STRIP_BIN, conf


def screen_brightness():
    """Mean brightness of the centre of the screen (0-255)."""
    img = ImageGrab.grab(bbox=(560, 240, 1360, 840)).convert("L").resize((80, 60))
    return float(np.asarray(img).mean())


# ----------------------------------------------------------- run control

class Stop(Exception):
    pass


class StepFailed(Exception):
    """A step didn't reach the expected screen state."""


class FocusLost(Exception):
    """ARK lost focus mid-step and got it back: the step's inputs may have gone
    elsewhere, so camera/UI state is unknown. Only raised when Control.unattended."""


class Control:
    """Pause/stop flags for the bot. With hotkeys=True a background thread
    polls F9 (pause toggle) and F10 (stop); the desktop app passes
    hotkeys=False and flips the flags itself.

    unattended=True (set by the run loops): bring ARK back after refocus_idle_s
    without user input, raise FocusLost once it's back, and let pause() retry
    by itself after auto_resume_min without user input."""

    def __init__(self, title, paused=True, hotkeys=True):
        self.title = title
        self.paused = paused
        self.stopped = False
        self.status = "starting"   # short human-readable state for the app
        self.next_run = None       # epoch seconds while waiting between cycles
        self.progress = None       # per-station counters for the overlay
        self.unattended = False
        self.refocus_idle_s = 0
        self._lost_focus = False
        if hotkeys:
            threading.Thread(target=self._poll, daemon=True).start()

    def _poll(self):
        key_pressed(VK_F9)  # clear stale presses
        key_pressed(VK_F10)
        while not self.stopped:
            if key_pressed(VK_F10):
                self.stopped = True
                print("\n[F10] stopping")
            if key_pressed(VK_F9):
                self.paused = not self.paused
                print("\n[F9] paused" if self.paused else "\n[F9] running")
            time.sleep(0.03)

    def pause(self, why, resume_after_s=0):
        print(f"\n!! PAUSED: {why}\n   Fix it in game, then press F9 to resume (F10 to stop).")
        if resume_after_s:
            print(f"   Retrying by itself after {resume_after_s / 60:g} min with no keyboard/mouse input.")
        beep()
        self.paused = True
        if resume_after_s:
            threading.Thread(target=self._auto_resume, args=(resume_after_s,), daemon=True).start()

    def _auto_resume(self, after_s):
        # Ends as soon as anyone resumes; a later manual pause has no timer.
        # While paused the bot sends no input, so idle time is the user's.
        start = time.time()
        while self.paused and not self.stopped:
            if time.time() - start >= after_s and idle_seconds() >= after_s:
                print(f"[auto-resume {time.strftime('%H:%M:%S')}] no input for "
                      f"{after_s / 60:g} min; retrying")
                self.paused = False
                return
            time.sleep(1)

    def check(self):
        warned = False
        last_try = 0.0
        while True:
            if self.stopped:
                raise Stop()
            focused = game_focused(self.title)
            if not self.paused and focused:
                if self._lost_focus and self.unattended:
                    self._lost_focus = False
                    raise FocusLost()
                return
            if not self.paused and not focused:
                if not warned:
                    print(f"  waiting for '{self.title}' to be the focused window... "
                          f"(foreground: '{window_title()}')")
                    warned = True
                self._lost_focus = True
                if (self.unattended and self.refocus_idle_s and time.time() - last_try >= 5
                        and idle_seconds() >= self.refocus_idle_s):
                    last_try = time.time()
                    print(f"  no input for {self.refocus_idle_s}s; bringing ARK back")
                    focus_window(self.title)
            time.sleep(0.05)

    def sleep(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.check()
            time.sleep(min(0.05, max(0, end - time.time())))

    def wait_for(self, fn, timeout, poll=0.03):
        """Poll fn() until true or timeout. Time spent paused doesn't count."""
        end = time.time() + timeout
        while True:
            t0 = time.time()
            self.check()
            end += time.time() - t0
            if fn():
                return True
            if time.time() >= end:
                return False
            time.sleep(poll)


# ----------------------------------------------------------- actions

class Bot:
    def __init__(self, cfg, ctl):
        self.cfg = cfg
        self.ctl = ctl
        self.keys = cfg["keys"]
        self.t = cfg["timing"]
        self.look = cfg["look"]
        self.ui = cfg["ui"]
        # Camera state relative to the spawn direction. pitch None = unknown
        # (re-anchor by looking straight down before the next aim).
        self.yaw = 0
        self.pitch = None

    def seen(self, name):
        return on_screen(self.cfg, name)

    # -- camera

    def turn(self, dx, dy):
        """Relative camera move, chunked so the game doesn't drop big deltas.
        Never moves both axes at once: diagonal moves lose yaw (measured)."""
        if dx and dy:
            self.turn(dx, 0)
            self.turn(0, dy)
            return
        chunk = self.look["chunk"]
        while dx or dy:
            sx = max(-chunk, min(chunk, dx))
            sy = max(-chunk, min(chunk, dy))
            mouse_rel(sx, sy)
            dx -= sx
            dy -= sy
            time.sleep(self.look["chunk_delay_s"])

    def look_down(self):
        self.turn(0, self.look["down_reset_counts"])
        time.sleep(0.05)
        self.pitch = 0

    def aim(self, yaw, pitch):
        # Always re-anchor pitch: ARK's mouse smoothing makes relative pitch
        # moves drift. Slamming the view down hits the pitch clamp, which is
        # exact. Yaw is tracked in the room's reference frame (see orient()).
        self.look_down()
        # Always go via the spawn direction with one continuous move each way:
        # ARK loses ~15% of small/isolated moves (measured), so only moves of
        # the same shape as during calibration land in the same place.
        if self.yaw:
            self.turn(-self.yaw, 0)
        self.turn(yaw, 0)
        self.turn(0, -(pitch - self.pitch))
        self.yaw, self.pitch = yaw, pitch
        # Mouse smoothing keeps the camera moving for a moment after the
        # input stops; F pressed too early targets the wrong thing.
        self.ctl.sleep(self.t["settle_after_aim_s"])

    def orient(self, layout):
        """Work out which way we're facing by matching a 360 strip of the
        room against the layout's saved reference. After this, self.yaw is
        the current facing in the reference frame."""
        cur = capture_strip(self)
        best = (0, 0.0, "")
        for name in layout["refs"]:   # e.g. a day and a night reference
            off, conf = match_strip(_load_ref(name), cur)
            if conf > best[1]:
                best = (off, conf, name)
        off, conf, name = best
        if conf < self.t["orient_min_conf"]:
            raise StepFailed(f"didn't recognise the room (confidence {conf:.2f})")
        self.yaw = ((off + TURN // 2) % TURN) - TURN // 2
        print(f"    facing {self.yaw:+d} (confidence {conf:.1f}, {name})")
        return off, conf

    def face_home(self):
        self.turn(-self.yaw, 0)
        self.yaw = 0

    def recover(self):
        """Back out of any open UI and forget the pitch (re-anchor next aim)."""
        if self.seen("bench_open"):
            # first Esc may only leave a focused search box; close_bench retries
            self.close_bench()
        if self.seen("map_open"):
            click(*self.ui["map_close"])
            self.ctl.wait_for(lambda: not self.seen("map_open"), self.t["close_timeout_s"])
        self.pitch = None

    # -- benches

    def open_bench(self):
        if self.seen("bench_open"):
            return True
        tap(self.keys["access"])
        # One press, then wait. F toggles, so pressing again while a laggy
        # bench is still loading would close it the moment it appears.
        if self.ctl.wait_for(lambda: self.seen("bench_open"), self.t["bench_open_timeout_s"]):
            return True
        # A very late open still counts: if it pops up now, use it rather than
        # turning the camera (mouse moves would go to the inventory cursor).
        return self.ctl.wait_for(lambda: self.seen("bench_open"), 1.5)

    def close_bench(self):
        for i in range(4):
            if not self.seen("bench_open"):
                return True
            tap(self.keys["close"])
            # a focused text box swallows the first Esc; don't wait long on it
            wait = 1.0 if i == 0 else self.t["close_timeout_s"]
            if self.ctl.wait_for(lambda: not self.seen("bench_open"), wait):
                return True
        return False

    def _storage_snapshot(self):
        x0, y0, x1, y1 = self.ui["storage_area"]
        img = ImageGrab.grab(bbox=(x0, y0, x1, y1)).convert("L").resize(((x1 - x0) // 4, (y1 - y0) // 4))
        return np.asarray(img, dtype=np.int16)

    def pull_resources(self, amount, own=False):
        """Type the amount into the amount box and hit the pull button, then
        wait (briefly) for the resources to land. own=True uses your own
        inventory's box/button (top-left) instead of the structure's."""
        box, btn, area, check = (("inv_amount_box", "inv_pull_button", "inv_storage_area", "inv_open")
                                 if own else ("amount_box", "pull_button", "storage_area", "bench_open"))
        clear_box(*self.ui[box], n=8)
        type_text(amount)

        def snap():
            x0, y0, x1, y1 = self.ui[area]
            img = ImageGrab.grab(bbox=(x0, y0, x1, y1)).convert("L").resize(((x1 - x0) // 4, (y1 - y0) // 4))
            return np.asarray(img, dtype=np.int16)
        before = snap()
        click(*self.ui[btn])
        if not (self.own_inv_visible() if own else self.seen(check)):
            raise StepFailed("inventory closed while pulling resources")
        # Move on as soon as the stored items change. If already stocked
        # nothing changes, so this is capped short.
        self.ctl.wait_for(lambda: np.abs(snap() - before).mean() > 3, self.t["pull_wait_s"])

    PROMPT_AREA = (0, 120, 1840, 1040)

    def prompt_visible(self, layout):
        """Is the structure's "[E] : Turn Off" prompt on screen?"""
        pr = layout["prompt"]
        box = self.PROMPT_AREA
        img = ImageGrab.grab(bbox=box)
        return find_text_line(img, pr["template"], pr["kind"], box, origin=box[:2]) >= pr["min"]

    def find_target(self, bench, layout):
        """Aim at a target; if its prompt isn't there, nudge left/right a
        little (small drift) before giving up. Never presses anything."""
        for d in [0] + [s * n for n in self.look["nudges"] for s in (1, -1)]:
            self.aim(bench["yaw"] + d, bench["pitch"])
            if self.ctl.wait_for(lambda: self.prompt_visible(layout), 0.5):
                if d:
                    print(f"    {bench['name']}: found {d:+d} counts off")
                return True
        return False

    def craft_bench(self, bench, layout):
        """Queue crafts on one target (chem bench / fabricator).
        Raises StepFailed if it can't."""
        t0 = time.time()
        if not self.find_target(bench, layout):
            raise StepFailed(f"{bench['name']}: nothing to open there")
        if not self.open_bench():
            raise StepFailed(f"{bench['name']}: inventory never opened")
        try:
            ready = layout.get("ready_check")
            if ready and not self.ctl.wait_for(lambda: self.seen(ready),
                                               self.t["grid_ready_timeout_s"]):
                raise StepFailed(f"{bench['name']}: item grid never loaded")
            done = 0
            for r in layout_recipes(layout):
                if self.craft_recipe(r, bench["name"]):
                    done += 1
            if not done:
                raise StepFailed(f"{bench['name']}: no recipe could be crafted")
        finally:
            if not self.close_bench():
                self.pitch = None
                raise StepFailed(f"{bench['name']}: inventory won't close")
        print(f"  {bench['name']}: queued ({time.time() - t0:.1f}s)")

    def _clear_search(self):
        clear_box(*self.ui["target_search"])
        self._searched = False

    def select_recipe(self, r):
        """Click the recipe's blueprint. Fixed slot if known, else search for
        it and take the first result that's a recipe (not a stored stack).
        Returns the slot (x, y) or None."""
        if r.get("slot"):
            if getattr(self, "_searched", False):
                self._clear_search()
                self.ctl.sleep(self.t["search_settle_s"])
            click(*r["slot"])
            return tuple(r["slot"])
        clear_box(*self.ui["target_search"])
        type_text(r["search"])
        self._searched = True
        self.ctl.sleep(self.t["search_settle_s"])
        move_to(1000, 900)          # keep tooltips off the grid
        time.sleep(0.15)
        rgb = np.asarray(ImageGrab.grab().convert("RGB"))
        pos = slotpick.first_recipe(rgb)
        if pos:
            click(*pos)
        return pos

    def craft_recipe(self, r, where):
        """Select, pull resources for, and queue one recipe on the open
        structure. Returns True if crafts were queued."""
        if not r.get("enabled", True):
            return False
        pos = self.select_recipe(r)
        if not pos:
            print(f"    {where}: {r['name']} not found (search '{r.get('search', '')}')")
            return False
        if r.get("pull_amount"):
            self.pull_resources(r["pull_amount"])
            click(*pos)  # back to the item, craft as normal
        pressed = 0
        for _ in range(int(r.get("presses", 1))):
            self.ctl.check()
            if not self.seen("bench_open"):  # never strafe in the world
                raise StepFailed(f"{where}: inventory closed after {pressed} presses")
            tap(self.keys["craft"])
            pressed += 1
            time.sleep(self.t["craft_press_gap_s"])
        return True

    def craft_area(self, layout, targets, progress=None):
        """Run every enabled target (each gets one retry). Assumes we just
        spawned on the bed these targets were calibrated for.
        Returns how many failed."""
        self.yaw, self.pitch = 0, None
        targets = [t for t in targets if t.get("enabled", True)]
        failed = 0
        for i, bench in enumerate(targets):
            if self.ctl:
                self.ctl.status = f"{bench['name']} ({i + 1}/{len(targets)})"
            if progress is not None:
                progress["current"] = bench["name"]
            for attempt in (1, 2):
                try:
                    self.craft_bench(bench, layout)
                    if progress is not None:
                        progress["done"] += 1
                    break
                except StepFailed as e:
                    print(f"  ! {e} (attempt {attempt})")
                    self.recover()
                    if attempt == 2:
                        failed += 1
                        if progress is not None:
                            progress["failed"] += 1
            if progress is not None:
                progress["visited"] += 1
        self.face_home()
        return failed

    # -- own inventory crafting

    def _slot_snapshot(self):
        x, y = self.ui["inv_first_slot"]
        img = ImageGrab.grab(bbox=(x - 40, y - 40, x + 40, y + 40)).convert("L")
        return np.asarray(img, dtype=np.int16)

    def _inv_search(self, text):
        clear_box(*self.ui["inv_search"])
        type_text(text)
        self.ctl.sleep(self.t["search_settle_s"])

    def own_inv_visible(self):
        return self.seen("inv_open") or self.seen("inv_crafting")

    def open_own_inventory(self):
        if self.own_inv_visible():
            return True
        tap(self.keys["inventory"])
        return self.ctl.wait_for(lambda: self.own_inv_visible(), self.t["bench_open_timeout_s"])

    def close_own_inventory(self):
        for i in range(4):
            if not self.own_inv_visible():
                return True
            tap(self.keys["close"])
            wait = 1.0 if i == 0 else self.t["close_timeout_s"]
            if self.ctl.wait_for(lambda: not self.own_inv_visible(), wait):
                return True
        return False

    def _dbg(self, tag):
        """Save a screenshot of the left half for diagnosing inventory runs."""
        if not self.cfg.get("inventory_craft", {}).get("debug_shots", True):
            return
        d = Path(__file__).with_name("shots") / "inv_debug"
        d.mkdir(parents=True, exist_ok=True)
        self._dbg_n = getattr(self, "_dbg_n", 0) + 1
        ImageGrab.grab(bbox=(0, 0, 960, 1080)).resize((480, 540)).save(d / f"{self._dbg_n:02d}_{tag}.png")

    def craft_inventory(self, recipes, progress=None):
        """Open your inventory, go to CRAFTING, and for each recipe: search,
        check something showed up, hover it and press the craft key.
        Returns how many recipes failed."""
        recipes = [r for r in recipes if r.get("enabled", True)]
        if not recipes:
            return 0
        if self.seen("bench_open"):
            self.close_bench()
        if not self.open_own_inventory():
            raise StepFailed("inventory didn't open")
        failed = 0
        self._dbg_n = 0
        d = Path(__file__).with_name("shots") / "inv_debug"
        if d.exists():
            for f in d.glob("*.png"):
                f.unlink()
        try:
            click(*self.ui["inv_crafting_tab"])
            self.ctl.sleep(0.4)
            self._dbg("crafting_tab")
            for r in recipes:
                self.ctl.check()
                if progress is not None:
                    progress["current"] = r["name"]
                if self.ctl:
                    self.ctl.status = f"crafting {r['name']}"
                self._inv_search(r["search"])
                move_to(900, 900)               # keep the tooltip off the slot
                time.sleep(0.15)
                key = r["name"].replace(" ", "")
                self._dbg(f"{key}_searched")
                if self._slot_snapshot().std() < 14:   # flat = empty slot, nothing found
                    print(f"  ! {r['name']}: no blueprint found for '{r['search']}'")
                    failed += 1
                    if progress is not None:
                        progress["failed"] += 1
                    continue
                click(*self.ui["inv_first_slot"])
                if r.get("pull_amount"):
                    self._dbg(f"{key}_selected")
                    self.pull_resources(r["pull_amount"], own=True)
                    self._dbg(f"{key}_pulled")
                    click(*self.ui["inv_first_slot"])  # back to the item
                for _ in range(int(r.get("presses", 1))):
                    self.ctl.check()
                    if not self.own_inv_visible():   # never strafe in the world
                        raise StepFailed("inventory closed while crafting")
                    tap(self.keys["craft"])
                    time.sleep(self.t["craft_press_gap_s"])
                time.sleep(0.5)
                self._dbg(f"{key}_after_A")
                print(f"  {r['name']}: queued")
                if progress is not None:
                    progress["done"] += 1
                    progress["visited"] += 1
        finally:
            if not self.close_own_inventory():
                raise StepFailed("inventory won't close")
        return failed

    # -- beds

    def _sweep_for_bed(self):
        self.look_down()
        for yaw in self.look["bed_search_yaws"]:
            self.ctl.check()
            self.turn(yaw - self.yaw, 0)
            self.yaw = yaw
            if self.ctl.wait_for(lambda: self.seen("bed_prompt"), 0.25):
                return True
        self.face_home()
        return False

    def face_bed(self):
        """Look down and sweep yaw until the bed's Fast Travel prompt shows.
        Some beds spawn you standing over the mattress, where the use-trace
        only hits the Tek Ceiling; then step off a little and sweep again."""
        if self._sweep_for_bed():
            return True
        stepped = 0.0
        for hold in self.look["bed_step_back_s"]:
            print(f"    bed not targetable here; stepping back {hold}s")
            self.face_home()
            tap("s", hold=hold)
            stepped += hold
            self.ctl.sleep(0.3)
            if self._sweep_for_bed():
                return True
        if stepped:  # didn't help: walk back to where we started
            self.face_home()
            tap("w", hold=stepped)
        return False

    def open_map(self):
        if self.ctl.wait_for(lambda: self.seen("map_open"), 0.6):
            return
        if not self.face_bed():
            raise StepFailed("no bed under the crosshair looking down")
        tap(self.keys["use"])  # face_bed just proved the prompt is the bed's
        if not self.ctl.wait_for(lambda: self.seen("map_open"), self.t["map_open_timeout_s"]):
            raise StepFailed("map didn't open")

    def wait_spawned(self):
        """After the map closes: a real fast travel goes through a white or
        black loading screen. Returns False if none shows up (the map just
        closed, e.g. the bed was unusable), True once we're in the world."""
        start = time.time()
        saw_loading = False
        good_since = None
        while time.time() - start < self.t["spawn_timeout_s"]:
            self.ctl.check()
            b = screen_brightness()
            if b <= 12 or b >= 230:
                saw_loading = True
                good_since = None
            elif not saw_loading:
                if time.time() - start > self.t["loading_seen_timeout_s"]:
                    return False
            else:
                good_since = good_since or time.time()
                if time.time() - good_since > 0.8:
                    self.ctl.sleep(self.t["spawn_settle_s"])
                    self.yaw, self.pitch = 0, None  # fresh spawn direction
                    return True
            time.sleep(0.05)
        raise StepFailed("stuck on a loading screen (disconnected?)")

    def _entry_selected(self, y):
        """A selected bed-list row has a bright white border."""
        x0 = self.ui["bed_list_first"][0] - 120
        row = np.asarray(ImageGrab.grab(bbox=(x0, y - 22, x0 + 260, y + 22)).convert("L"))
        return int((row > 215).sum()) > 250   # measured: selected 528, not <=146

    def travel_station(self, beds):
        """Travel to the first bed in `beds` that's available (main bed
        first, then spares). Returns the bed name we landed on."""
        give_up = time.time() + self.t["cooldown_give_up_min"] * 60
        while True:
            for bed in beds:
                self.ctl.check()
                if self.travel_to(bed, once=True):
                    return bed
                print(f"    {bed} not available")
            if time.time() > give_up:
                raise StepFailed(f"no bed of {', '.join(beds)} available for "
                                 f"{self.t['cooldown_give_up_min']} min")
            print(f"    all beds on cooldown; retrying in {self.t['cooldown_retry_s']}s")
            click(*self.ui["map_close"])
            self.ctl.wait_for(lambda: not self.seen("map_open"), self.t["close_timeout_s"])
            self.ctl.sleep(self.t["cooldown_retry_s"])

    def travel_to(self, bed_name, entry=None, once=False):
        print(f"  travelling to {bed_name}" + (f" (bed #{entry + 1})" if entry is not None else ""))
        give_up = time.time() + self.t["cooldown_give_up_min"] * 60
        while True:
            self.open_map()
            clear_box(*self.ui["bed_filter"], n=12)
            type_text(bed_name)
            self.ctl.sleep(0.4)  # filter applies
            click(*self.ui["bed_icon"])
            self.ctl.sleep(0.5)  # bed list pops up; ARK pre-selects a free bed
            if entry is not None:
                # Same-named beds are listed in a fixed order; pick ours so we
                # land on the bed whose aims are calibrated.
                x, y0 = self.ui["bed_list_first"]
                y = y0 + entry * self.ui["bed_list_step"]
                click(x, y)
                self.ctl.sleep(0.3)
                if not self._entry_selected(y):
                    print(f"    couldn't select {bed_name} entry {entry + 1}")
                move_to(1000, 800)
            click(*self.ui["bed_travel"])
            if self.ctl.wait_for(lambda: not self.seen("map_open"),
                                 self.t["map_leave_timeout_s"]):
                if self.wait_spawned():
                    return True
                print(f"    {bed_name}: map closed but no travel happened")
                if once:
                    return False
                continue
            if once:   # unavailable (cooldown / standing on it): leave map open
                return False
            if time.time() > give_up:
                raise StepFailed(f"{bed_name}: still on cooldown after "
                                 f"{self.t['cooldown_give_up_min']} min")
            print(f"    {bed_name} on cooldown; retrying in {self.t['cooldown_retry_s']}s")
            click(*self.ui["map_close"])
            self.ctl.wait_for(lambda: not self.seen("map_open"), self.t["close_timeout_s"])
            self.ctl.sleep(self.t["cooldown_retry_s"])


# ----------------------------------------------------------- config

def load_config():
    return ensure_recipes(_load_config())


def _load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if CONFIG_PATH.exists():
        saved = json.loads(CONFIG_PATH.read_text())
        for k, v in saved.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    print(f"saved {CONFIG_PATH}")


# ----------------------------------------------------------- commands

def _one_shot(cfg, fn, autostart):
    ctl = Control(cfg["window_title"], paused=not autostart)
    if not autostart:
        print("Focus ARK and press F9 to start. F10 stops.")
    try:
        fn(Bot(cfg, ctl))
        print("done")
    except StepFailed as e:
        print(f"FAILED: {e}")
    except Stop:
        print("stopped")
    finally:
        ctl.stopped = True


CHEM_PRESETS = {
    # blueprint slots in the Kav chemistry bench grid (1920x1080)
    "Sparkpowder": [1383, 372],
    "Cementing Paste": [1475, 372],
    "Gunpowder": [1568, 372],
}


def layout_recipes(layout):
    """The ordered recipe list for a layout. Older configs had one item per
    layout (item / search / pull_amount / craft_presses): turn that into a
    one-recipe list."""
    if layout.get("recipes"):
        return layout["recipes"]
    r = {"name": layout.get("label", "item"), "pull_amount": layout.get("pull_amount", ""),
         "presses": layout.get("craft_presses", 10), "enabled": True}
    if layout.get("search"):
        r["search"] = layout["search"]
    else:
        r["slot"] = layout.get("item")
    return [r]


def ensure_recipes(cfg):
    """Give each layout a recipe list (migrating old single-item configs)."""
    for name, lay in cfg["layouts"].items():
        if lay.get("recipes"):
            continue
        rs = layout_recipes(lay)
        if name == "chem":
            rs[0]["name"] = "Gunpowder"
            rs[0].pop("search", None)
            rs[0]["slot"] = CHEM_PRESETS["Gunpowder"]
            for n in ("Sparkpowder", "Cementing Paste"):
                rs.append({"name": n, "slot": CHEM_PRESETS[n], "pull_amount": rs[0]["pull_amount"],
                           "presses": rs[0]["presses"], "enabled": False})
        elif name == "fab":
            rs[0]["name"] = "Advanced Rifle Bullet"
        lay["recipes"] = rs
    return cfg


def calibrated_beds(cfg, station):
    """The station's beds that have calibrated targets, in priority order."""
    bt = cfg.get("bed_targets", {})
    return [b for b in station["beds"] if bt.get(b, {}).get("targets")]


def stations_from(cfg, names=None):
    """Enabled stations (or the named ones) that have at least one
    calibrated bed."""
    sts = [st for st in cfg["stations"]
           if (st["name"] in names if names else st.get("enabled", True))]
    return [st for st in sts if calibrated_beds(cfg, st)]


def cmd_run(cfg, names, autostart, here):
    ctl = Control(cfg["window_title"], paused=not autostart)
    if not autostart:
        print("Focus ARK and press F9 to start/pause, F10 to stop.")
    run_loop(cfg, stations_from(cfg, names), here, ctl)


def _unattended(ctl, cfg):
    """Loops run overnight: recover from focus theft and failure pauses."""
    ctl.unattended = True
    ctl.refocus_idle_s = cfg["timing"].get("refocus_idle_s", 0)


def _settle_after_focus(bot, ctl, cleanup=None):
    """After FocusLost: let a restored fullscreen ARK redraw, then close any UI.
    Focus lost again meanwhile just restarts the wait."""
    while True:
        try:
            ctl.sleep(2)
            (cleanup or bot.recover)()
            return
        except FocusLost:
            continue


def run_loop(cfg, stations, here, ctl):
    """The main crafting loop: visit every station, craft, wait, repeat
    forever (until ctl.stopped). Used by the CLI and the desktop app.

    here: name of the bed you're standing on right after spawning (skips
    the first travel), or None.

    ctl.progress is kept up to date for the overlay:
      station, bed, label, current, done, failed, visited, total, cycle"""
    bot = Bot(cfg, ctl)
    limit = cfg["timing"]["max_consecutive_failures"]
    layouts = cfg["layouts"]
    if not stations:
        print("Nothing to do: no enabled station has a calibrated bed.")
        ctl.status = "stopped"
        return
    for st in stations:
        print(f"Station {st['name']}: beds {', '.join(calibrated_beds(cfg, st))}")
    _unattended(ctl, cfg)

    failures = 0
    cycles = 0

    def failed(why):
        nonlocal failures
        failures += 1
        print(f"  ! {why} ({failures}/{limit} in a row)")
        bot.recover()
        if failures >= limit:
            ctl.pause(f"{failures} failures in a row; last: {why}",
                      resume_after_s=cfg["timing"].get("auto_resume_min", 0) * 60)
            failures = 0

    def travel(st):
        beds = calibrated_beds(cfg, st)
        while True:
            ctl.status = f"travelling to {st['name']}"
            try:
                return bot.travel_station(beds)
            except StepFailed as e:
                failed(str(e))
                ctl.sleep(2)

    try:
        pos = 0
        bed = here
        while True:
            try:
                # always travel, even with one station: a fresh spawn is what
                # makes the calibrated aims line up
                if bed is None:
                    bed = travel(stations[pos])
                st = stations[pos]
                layout = layouts[st["layout"]]
                targets = [t for t in cfg["bed_targets"][bed]["targets"] if t.get("enabled", True)]
                ctl.progress = {"station": st["name"], "bed": bed,
                                "label": layout.get("label", st["layout"]),
                                "current": "", "done": 0, "failed": 0, "visited": 0,
                                "total": len(targets), "cycle": cycles + 1}
                print(f"[{time.strftime('%H:%M:%S')}] {st['name']} on {bed} ({len(targets)} targets)")
                t0 = time.time()
                bad = bot.craft_area(layout, targets, ctl.progress)
                print(f"  {st['name']} done in {time.time() - t0:.0f}s: "
                      f"{len(targets) - bad}/{len(targets)} crafted")
                if targets and bad == len(targets):
                    failed(f"nothing on {bed} could be opened")
                else:
                    failures = 0
                pos = (pos + 1) % len(stations)
                bed = None
                if pos == 0:
                    cycles += 1
                    mins = cfg["cycle_wait_minutes"]
                    ctl.next_run = time.time() + mins * 60
                    nxt = time.strftime('%H:%M', time.localtime(ctl.next_run))
                    print(f"  cycle {cycles} done; waiting {mins:g} min (next run {nxt})")
                    ctl.status = f"waiting (cycle {cycles} done)"
                    ctl.sleep(mins * 60)
                    ctl.next_run = None
            except FocusLost:
                # inputs may have gone to another window mid-step: camera and UI
                # state are unknown, so close any UI and respawn at this station
                print(f"  ! [{time.strftime('%H:%M:%S')}] ARK lost focus mid-step; "
                      f"resetting at {stations[pos]['name']}")
                ctl.next_run = None
                bed = None
                _settle_after_focus(bot, ctl)
    except Stop:
        print("stopped")
    finally:
        ctl.status = "stopped"
        ctl.next_run = None


def run_inventory_loop(cfg, ctl):
    """Craft from your own inventory forever, waiting between rounds.
    No travelling (fast travel drops items)."""
    bot = Bot(cfg, ctl)
    ic = cfg["inventory_craft"]
    recipes = [r for r in ic["recipes"] if r.get("enabled", True)]
    if not recipes:
        print("Nothing to do: no recipe ticked.")
        ctl.status = "stopped"
        return
    print("Inventory crafting: " + ", ".join(r["name"] for r in recipes))
    _unattended(ctl, cfg)
    rounds = 0
    fails = 0
    limit = cfg["timing"]["max_consecutive_failures"]
    try:
        while True:
            ctl.progress = {"station": "Inventory", "bed": "you", "label": "Inventory",
                            "current": "", "done": 0, "failed": 0, "visited": 0,
                            "total": len(recipes), "cycle": rounds + 1}
            print(f"[{time.strftime('%H:%M:%S')}] inventory round {rounds + 1}")
            try:
                bot.craft_inventory(recipes, ctl.progress)
                fails = 0
            except FocusLost:
                print(f"  ! [{time.strftime('%H:%M:%S')}] ARK lost focus mid-round; retrying")
                _settle_after_focus(bot, ctl, bot.close_own_inventory)
                continue
            except StepFailed as e:
                fails += 1
                print(f"  ! {e} ({fails}/{limit} in a row)")
                bot.close_own_inventory()
                if fails >= limit:
                    ctl.pause(f"{fails} failures in a row; last: {e}",
                              resume_after_s=cfg["timing"].get("auto_resume_min", 0) * 60)
                    fails = 0
            rounds += 1
            mins = ic["wait_minutes"]
            ctl.next_run = time.time() + mins * 60
            ctl.status = f"waiting (round {rounds} done)"
            try:
                ctl.sleep(mins * 60)
            except FocusLost:
                pass   # nothing was in progress
            ctl.next_run = None
    except Stop:
        print("stopped")
    finally:
        ctl.status = "stopped"
        ctl.next_run = None


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--now", action="store_true",
                   help="start immediately instead of waiting for F9")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("test-bed", help="travel to a bed and craft all its targets once")
    t.add_argument("bed")
    t.add_argument("--here", action="store_true")
    tt = sub.add_parser("test-travel")
    tt.add_argument("bed")
    r = sub.add_parser("run")
    r.add_argument("--stations", nargs="+", metavar="NAME",
                   help="only these stations, e.g. --stations CB1 (default: enabled ones)")
    r.add_argument("--here", metavar="BED",
                   help="you just spawned on this bed; skip the first travel")
    r.add_argument("--wait", type=float, metavar="MIN",
                   help="minutes to wait after each full cycle")
    args = p.parse_args()

    cfg = load_config()
    if not CONFIG_PATH.exists():
        save_config(cfg)
    if args.cmd == "test-bed":
        entry = cfg["bed_targets"][args.bed]
        layout = cfg["layouts"][entry["layout"]]

        def one(b):
            if not args.here:
                b.travel_to(args.bed)
            prog = {"done": 0, "failed": 0, "visited": 0, "current": ""}
            b.craft_area(layout, entry["targets"], prog)
            print(f"{args.bed}: {prog['done']}/{len(entry['targets'])} crafted")
        _one_shot(cfg, one, args.now)
    elif args.cmd == "test-travel":
        _one_shot(cfg, lambda b: b.travel_to(args.bed), args.now)
    else:
        if args.wait is not None:
            cfg["cycle_wait_minutes"] = args.wait
        cmd_run(cfg, args.stations, args.now, args.here)


if __name__ == "__main__":
    main()
