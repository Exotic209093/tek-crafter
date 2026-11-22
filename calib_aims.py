"""Screenshot candidate bench aims (yaw, pitch) with a crosshair marker.
usage: python calib_aims.py out.png yaw:pitch[:label] ..."""
import sys
import time

from PIL import Image, ImageDraw, ImageGrab

import ark_chem as a
import ark_probe

out = sys.argv[1]
aims = []
for s in sys.argv[2:]:
    p = s.split(":")
    aims.append((int(p[0]), int(p[1]), p[2] if len(p) > 2 else s))
cfg = a.load_config()
bot = a.Bot(cfg, None)
ark_probe.focus()
tiles = []
for yaw, pitch, label in aims:
    bot.look_down()
    bot.turn(yaw, 0)
    bot.turn(0, -pitch)
    time.sleep(0.4)
    im = ImageGrab.grab().convert("RGB")
    bot.turn(-yaw, 0)
    d = ImageDraw.Draw(im)
    d.line((930, 540, 990, 540), fill="red", width=4)
    d.line((960, 510, 960, 570), fill="red", width=4)
    d.text((20, 40), label, fill="yellow", font_size=60)
    tiles.append(im.resize((480, 270)))
cols = 3
rows = (len(tiles) + cols - 1) // cols
g = Image.new("RGB", (480 * cols, 270 * rows))
for i, t in enumerate(tiles):
    g.paste(t, ((i % cols) * 480, (i // cols) * 270))
g.save(out)
print("saved", out)

