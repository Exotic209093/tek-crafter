"""Offline check of the screen templates against saved full-res screenshots."""
import time

from PIL import Image

import ark_chem as a

cfg = a.load_config()
CASES = {
    "bench.png": {"bench_open", "grid_ready"},
    "cb2full.png": {"map_open"},
    "cblistfull.png": {"map_open"},
    "map.png": {"bed_prompt"},
    "t3.png": set(),
}
bad = 0
for f, expect in CASES.items():
    img = Image.open("shots/" + f).convert("RGB")
    row = []
    for n in ["bench_open", "grid_ready", "map_open", "bed_prompt"]:
        t = time.perf_counter()
        r = a.check_image(cfg, img, n)
        ms = (time.perf_counter() - t) * 1000
        wrong = r != (n in expect)
        bad += wrong
        row.append(f"{n}={r}{' WRONG' if wrong else ''} {ms:.0f}ms")
    print(f, " | ".join(row))
print("FAILURES:", bad)
