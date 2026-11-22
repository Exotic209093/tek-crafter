"""Travel to the bed whose list name is exactly FILTER (the shortest name in
the popup list), e.g. the last un-renamed 'CB2' among 'CB2A','CB2'.
usage: python travel_plain.py FILTER"""
import sys
import time

import numpy as np
from PIL import ImageGrab

import ark_chem as a
import ark_probe

flt = sys.argv[1]
cfg = a.load_config()
ui = cfg["ui"]
ctl = a.Control(cfg["window_title"], paused=False, hotkeys=False)
bot = a.Bot(cfg, ctl)
ark_probe.focus()
bot.recover()
bot.open_map()
a.click(*ui["bed_filter"])
for _ in range(8):
    a.tap("backspace", hold=0.01)
a.type_text(flt)
time.sleep(0.8)
a.click(*ui["bed_icon"])
time.sleep(0.8)
a.move_to(1000, 800)
time.sleep(0.3)
img = np.asarray(ImageGrab.grab().convert("L")).astype(int)
x0, y0 = ui["bed_list_first"]
widths = []
for i in range(4):
    y = y0 + i * ui["bed_list_step"]
    row = img[y - 10:y + 10, x0 - 110:x0 + 130]
    # row text is light; background dark teal
    cols = np.nonzero((row > 95).sum(axis=0) > 1)[0]
    # ignore the row border (first/last few px)
    cols = cols[(cols > 6) & (cols < row.shape[1] - 6)]
    w = int(cols.max() - cols.min()) if len(cols) > 5 else 0
    widths.append(w)
print("row text widths:", widths)
rows = [(w, i) for i, w in enumerate(widths) if w > 20]
if not rows:
    sys.exit("no rows found")
w, pick = min(rows)
print(f"picking row {pick + 1} (width {w})")
a.click(x0, y0 + pick * ui["bed_list_step"])
time.sleep(0.4)
a.move_to(1000, 800)
a.click(*ui["bed_travel"])
if ctl.wait_for(lambda: not bot.seen("map_open"), 8):
    bot.wait_spawned()
    print("travelled")
else:
    print("still on map (cooldown?)")
ctl.stopped = True

