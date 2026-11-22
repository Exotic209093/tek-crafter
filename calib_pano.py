"""360 panorama from the spawn direction with yaw gridlines (0.87 px/count)."""
import sys
import time

from PIL import Image, ImageDraw, ImageGrab

import ark_chem as a
import ark_probe

pitch = int(sys.argv[1]) if len(sys.argv) > 1 else 1330
cfg = a.load_config()
bot = a.Bot(cfg, None)
ark_probe.focus()
PX = 0.87
tiles = []
for yaw in range(0, 5000, 1000):
    bot.look_down()
    bot.turn(yaw, 0)
    bot.turn(0, -pitch)
    time.sleep(0.45)
    im = ImageGrab.grab().convert("RGB")
    bot.turn(-yaw, 0)
    d = ImageDraw.Draw(im)
    for c in range(-1000, 1001, 100):
        x = 960 + c * PX
        major = c % 500 == 0
        d.line((x, 0, x, 1080), fill=(255, 60, 60) if c == 0 else ((255, 220, 0) if major else (90, 90, 40)),
               width=3 if major else 1)
        if major:
            d.text((x + 4, 12), str(yaw + c), fill="yellow", font_size=28)
    d.line((0, 540, 1920, 540), fill="red", width=2)
    tiles.append(im.resize((640, 360)))
g = Image.new("RGB", (640 * len(tiles), 360))
for i, t in enumerate(tiles):
    g.paste(t, (i * 640, 0))
g.save(f"shots/pano_{pitch}.png")
print("saved", g.size)

