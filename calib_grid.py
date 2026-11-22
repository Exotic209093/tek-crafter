"""Close-up of one view with yaw gridlines every 50 counts.
usage: python calib_grid.py yaw pitch out.png"""
import sys
import time

from PIL import ImageDraw, ImageGrab

import ark_chem as a
import ark_probe

yaw, pitch, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
PX = 0.87
cfg = a.load_config()
bot = a.Bot(cfg, None)
ark_probe.focus()
bot.look_down()
bot.turn(yaw, -pitch)
time.sleep(0.4)
im = ImageGrab.grab().convert("RGB")
bot.turn(-yaw, 0)
d = ImageDraw.Draw(im)
for c in range(-1100, 1101, 50):
    x = 960 + c * PX
    major = c % 200 == 0
    d.line((x, 0, x, 1080), fill=(255, 220, 0) if major else (120, 110, 40), width=2 if major else 1)
    if major:
        d.text((x + 3, 8), str(yaw + c), fill="yellow", font_size=26)
d.line((0, 540, 1920, 540), fill="red", width=1)
im.resize((1280, 720)).save(out)
print("saved", out)
