"""Draw the Tek Crafter icon (hexagon + flask) -> assets/icon.png + icon.ico."""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 1024
out = Path(__file__).with_name("assets")
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))


def hexagon(cx, cy, r):
    return [(cx + r * math.cos(math.radians(60 * i - 90)), cy + r * math.sin(math.radians(60 * i - 90)))
            for i in range(6)]


# glow
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(glow).polygon(hexagon(512, 512, 470), fill=(60, 210, 255, 170))
img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(28)))
d = ImageDraw.Draw(img)
d.polygon(hexagon(512, 512, 455), fill=(8, 34, 44, 255))
d.polygon(hexagon(512, 512, 455), outline=(110, 230, 255, 255), width=26)
d.polygon(hexagon(512, 512, 395), outline=(40, 140, 170, 255), width=8)

# flask
c = (120, 232, 255, 255)
neck_w, top, shoulder, bottom = 120, 250, 470, 760
d.rounded_rectangle((512 - neck_w // 2 - 40, top - 20, 512 + neck_w // 2 + 40, top + 22), 12, fill=c)
body = [(512 - neck_w // 2, top + 22), (512 + neck_w // 2, top + 22), (512 + neck_w // 2, shoulder),
        (512 + 250, bottom), (512 - 250, bottom), (512 - neck_w // 2, shoulder)]
d.polygon(body, outline=c, width=34)
d.line([(512 - 238, bottom - 6), (512 + 238, bottom - 6)], fill=c, width=34)
# liquid
liquid = [(512 - 150, 600), (512 + 150, 600), (512 + 218, bottom - 26), (512 - 218, bottom - 26)]
d.polygon(liquid, fill=(70, 245, 120, 255))
for x, y, r in ((470, 650, 22), (560, 690, 16), (520, 560, 12)):
    d.ellipse((x - r, y - r, x + r, y + r), fill=(200, 255, 220, 255))

out.mkdir(exist_ok=True)
img.resize((512, 512), Image.LANCZOS).save(out / "icon.png")
img.resize((256, 256), Image.LANCZOS).save(out / "icon.ico",
                                           sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon written")
