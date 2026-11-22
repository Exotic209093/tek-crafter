"""Compare camera end positions for different move shapes."""
import time

from PIL import Image, ImageDraw, ImageGrab

import ark_chem as a
import ark_probe

cfg = a.load_config()
bot = a.Bot(cfg, None)
ark_probe.focus()
tiles = []


def shot(label):
    time.sleep(0.6)
    im = ImageGrab.grab().convert("RGB").resize((480, 270))
    d = ImageDraw.Draw(im)
    d.line((230, 135, 250, 135), fill="red", width=2)
    d.line((240, 125, 240, 145), fill="red", width=2)
    d.text((5, 5), label, fill="yellow", font_size=20)
    tiles.append(im)


bot.look_down(); bot.turn(0, -1000); shot("A: pitch only")
bot.look_down(); bot.turn(0, -1000); shot("A again")
bot.look_down(); bot.turn(1446, -1000); shot("B: combined"); bot.turn(-1446, 0)
bot.look_down(); bot.turn(1446, 0); bot.turn(0, -1000); shot("C: yaw then pitch"); bot.turn(-1446, 0)
bot.look_down(); bot.turn(0, -1000); shot("A after")
cfg["look"]["chunk_delay_s"] = 0.012
bot.look_down(); bot.turn(0, -1000); shot("A slow chunks")
g = Image.new("RGB", (960, 810))
for i, t in enumerate(tiles):
    g.paste(t, ((i % 2) * 480, (i // 2) * 270))
g.save("shots/pitch_test.png")
