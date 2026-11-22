"""Look at the bed under you and save a crop of its name prompt; keeps facing."""
import time

from PIL import ImageGrab

import ark_chem as a
import ark_probe

cfg = a.load_config()
ctl = a.Control(cfg["window_title"], paused=False, hotkeys=False)
bot = a.Bot(cfg, ctl)
ark_probe.focus()
print("bed found", bot.face_bed())
time.sleep(0.6)
ImageGrab.grab(bbox=(560, 450, 1360, 1000)).save("shots/bed_here.png")
bot.face_home()
ctl.stopped = True
