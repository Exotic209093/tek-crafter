"""Rename the bed you're standing on. Safe: only releases E when the
'Rename Bed' slice (bottom-right of the radial) is highlighted; otherwise
moves the selector back to the centre (cancel) before releasing.
usage: python rename_here.py NEWNAME"""
import sys
import time

import numpy as np
from PIL import ImageGrab

import ark_chem as a
import ark_probe

name = sys.argv[1]
cfg = a.load_config()
ctl = a.Control(cfg["window_title"], paused=False, hotkeys=False)
bot = a.Bot(cfg, ctl)
ark_probe.focus()
bot.recover()
if not bot.face_bed():
    sys.exit("no bed prompt under crosshair")


def highlighted(box):
    """Mean blue-minus-red of a radial slice: ~66 highlighted, ~10-13 not."""
    rgb = np.asarray(ImageGrab.grab(bbox=box).convert("RGB")).astype(int)
    return float((rgb[..., 2] - rgb[..., 0]).mean())


RENAME_BOX = (1060, 640, 1340, 820)    # bottom-right slice of the radial
DEMOLISH_BOX = (580, 360, 860, 520)    # top-left slice (must stay dark)
a.key_down("e")
try:
    time.sleep(1.3)
    for _ in range(6):
        a.mouse_rel(25, 25)
        time.sleep(0.03)
    time.sleep(0.4)
    hr, hd = highlighted(RENAME_BOX), highlighted(DEMOLISH_BOX)
    print(f"rename slice {hr:.0f}, demolish slice {hd:.0f}")
    ok = hr > 50 and hd < 40 and hr - hd > 30
    if not ok:
        for _ in range(6):
            a.mouse_rel(-25, -25)
            time.sleep(0.03)
        time.sleep(0.3)
finally:
    a.key_up("e")
if not ok:
    sys.exit("Rename Bed not highlighted - released at centre, nothing selected")
time.sleep(1.2)
a.click(960, 436)
time.sleep(0.2)
for _ in range(12):
    a.tap("backspace", hold=0.01)
a.type_text(name)
time.sleep(0.3)
a.click(960, 676)  # ACCEPT
time.sleep(1.0)
time.sleep(1.5)
bot.turn(0, -600)
time.sleep(0.4)
bot.turn(0, 600)
time.sleep(1.0)
ImageGrab.grab(bbox=(600, 500, 1320, 900)).save(f"shots/renamed_{name}.png")
print("done; check shots/renamed_%s.png" % name)
ctl.stopped = True


