"""Calibration helper: focus ARK, run a sequence of actions, take screenshots.

Actions (space separated):
  down              look straight down
  turn:DX:DY        relative mouse move (chunked)
  key:NAME          tap a key (scan-code name from ark_chem.SCAN)
  click:X:Y         left click at screen coords
  move:X:Y          hover at screen coords
  type:TEXT         type text
  wait:S            sleep seconds
  shot:NAME         full screenshot -> shots/NAME.png (half size)
  crop:NAME:X:Y:W:H full-res crop -> shots/NAME.png
"""
import ctypes
import sys
import time
from pathlib import Path

from PIL import ImageGrab

import ark_chem as a

SHOTS = Path(__file__).with_name("shots")
SHOTS.mkdir(exist_ok=True)


def focus(title="ARK: Survival Evolved"):
    hwnd = a.user32.FindWindowW(None, title)
    if not hwnd:
        sys.exit("ARK window not found")
    if title in a.window_title():
        return
    # Alt tap lets SetForegroundWindow succeed from a background process
    a.user32.keybd_event(0x12, 0, 0, 0)
    a.user32.keybd_event(0x12, 0, 2, 0)
    a.user32.ShowWindow(hwnd, 9)
    a.user32.SetForegroundWindow(hwnd)
    time.sleep(0.6)
    if title not in a.window_title():
        sys.exit(f"focus failed, foreground is '{a.window_title()}'")


def main():
    cfg = a.load_config()
    bot = a.Bot(cfg, None)
    focus()
    for act in sys.argv[1:]:
        parts = act.split(":")
        op = parts[0]
        if op == "down":
            bot.look_down()
        elif op == "turn":
            bot.turn(int(parts[1]), int(parts[2]))
            time.sleep(0.3)
        elif op == "key":
            a.tap(parts[1])
        elif op == "click":
            a.click(int(parts[1]), int(parts[2]))
        elif op == "move":
            a.move_to(int(parts[1]), int(parts[2]))
        elif op == "type":
            a.type_text(":".join(parts[1:]))
        elif op == "wait":
            time.sleep(float(parts[1]))
        elif op == "shot":
            img = ImageGrab.grab()
            print("screen", img.size)
            img.resize((img.width // 2, img.height // 2)).save(SHOTS / f"{parts[1]}.png")
        elif op == "crop":
            x, y, w, h = map(int, parts[2:6])
            ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(SHOTS / f"{parts[1]}.png")
        else:
            sys.exit(f"bad action {act}")
    print("ok")


if __name__ == "__main__":
    main()
