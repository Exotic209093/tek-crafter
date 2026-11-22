"""Auto-calibrate the bench/fabricator aims for one bed.

Travels to BED (exact name), then sweeps 360 degrees at several pitches. Each
structure's name prompt ("Kav Chemistry Bench" / "Kav Fabricator") is drawn at
the structure's own position, so while the crosshair stays on one structure
its prompt drifts smoothly across the screen, and it jumps when the crosshair
moves onto the next one. Those jumps split the sweep into one segment per
structure; the aim is the middle of each segment. Every aim is then checked
by actually opening it.

Saves the result into ark_chem_config.json under bed_targets[BED].

usage: python calibrate_bed.py BED LAYOUT [--here] [--pitches 900,1150,...]
"""
import argparse
import json
import time

from PIL import ImageGrab

import ark_chem as a
import ark_probe
from aimfind import find_aims

PX = 0.87          # screen px per yaw count (measured)
PY = 1.0           # screen px per pitch count (approx.)
AREA = (0, 120, 1840, 1040)

p = argparse.ArgumentParser()
p.add_argument("bed")
p.add_argument("layout")
p.add_argument("--here", action="store_true", help="already standing on BED, untouched")
p.add_argument("--pitches", default="")
p.add_argument("--step", type=int, default=100)
p.add_argument("--dry", action="store_true", help="sweep only, save raw hits")
p.add_argument("--hits", nargs="+", help="reuse saved sweep hit files instead of sweeping")
args = p.parse_args()

cfg = a.load_config()
layout = cfg["layouts"][args.layout]
pr = layout["prompt"]
pitches = ([int(x) for x in args.pitches.split(",")] if args.pitches
           else layout.get("sweep_pitches", [1000, 1650]))
ctl = a.Control(cfg["window_title"], paused=False, hotkeys=False)
bot = a.Bot(cfg, ctl)
ark_probe.focus()
bot.recover()
if not args.here:
    bot.travel_to(args.bed)
bot.yaw, bot.pitch = 0, None

t0 = time.time()
all_hits = []
for f in args.hits or []:
    all_hits.extend(json.load(open(f)))
for pitch in ([] if args.hits else pitches):
    hits = []
    bot.aim(-a.TURN // 2, pitch)
    for target in range(-a.TURN // 2, a.TURN // 2, args.step):
        # mouse smoothing is off, so plain small steps are exact
        if target != -a.TURN // 2:
            bot.turn(args.step, 0)
            bot.yaw = target
        time.sleep(0.25)
        img = ImageGrab.grab(bbox=AREA)
        s, x, y = a.find_text_hit(img, pr["template"], pr["kind"], AREA, origin=AREA[:2])
        if s >= pr["min"]:
            # where the prompt's anchor would sit if centred on screen
            hits.append((target, target + (x - 960) / PX, pitch + (540 - y) / PY, pitch,
                         int(x), int(y)))
    bot.face_home()
    print(f"pitch {pitch}: {len(hits)} hits")
    all_hits.extend(hits)
if not args.hits:
    json.dump(all_hits, open(f"shots/hits_{args.bed}.json", "w"))
if args.dry:
    bot.face_home()
    ctl.stopped = True
    raise SystemExit("dry run: hits saved")
aims = find_aims(all_hits, step=args.step)
print(f"found {len(aims)} structures in {time.time() - t0:.0f}s")


def prompt_anchor():
    """Where the visible structure prompt is anchored, in (yaw, pitch)
    counts: the same structure gives the same anchor from any aim."""
    img = ImageGrab.grab(bbox=AREA)
    sc, x, y = a.find_text_hit(img, pr["template"], pr["kind"], AREA, origin=AREA[:2])
    if sc < pr["min"]:
        return None
    return bot.yaw + (x - 960) / 0.72, bot.pitch - (y - 540) / 0.68


def opens():
    a.tap(cfg["keys"]["access"])
    ok = ctl.wait_for(lambda: bot.seen("bench_open"), 5)
    if ok:
        bot.close_bench()
    return ok


targets, anchors = [], []
for m in sorted(aims, key=lambda m: -m["steps"]):   # longest runs first
    anc = None
    for d in (0, 50, -50, 100, -100):
        bot.aim(m["yaw"] + d, m["pitch"])
        time.sleep(0.2)
        anc = prompt_anchor()
        if anc:
            m = dict(m, yaw=m["yaw"] + d)
            break
    tag = f"  yaw {m['yaw']:+5d} pitch {m['pitch']} ({m['steps']} steps): "
    if anc is None:
        print(tag + "no prompt there")
        continue
    # same bench = nearby aim in the same row whose prompt anchors together
    # (far-apart aims can't be compared: perspective skews the estimate)
    dup = next((i for i, (ay, ap) in enumerate(anchors)
                if abs(targets[i]["yaw"] - m["yaw"]) < 350
                and targets[i]["pitch"] == m["pitch"]
                and abs(ay - anc[0]) < 90 and abs(ap - anc[1]) < 120), None)
    if dup is not None:
        print(tag + f"same bench as #{dup + 1}, skipped")
        continue
    ok = opens()
    print(tag + ("OK" if ok else "did not open"))
    if ok:
        anchors.append(anc)
        targets.append({"yaw": m["yaw"], "pitch": m["pitch"],
                        "anchor": [round(anc[0]), round(anc[1])]})
# visit order: by row, then left to right
targets.sort(key=lambda t: (t["pitch"], t["yaw"]))
bot.face_home()
for i, t in enumerate(targets):
    t["name"] = f"{args.bed} #{i + 1}"

cfg_disk = json.loads(a.CONFIG_PATH.read_text()) if a.CONFIG_PATH.exists() else {}
cfg_disk.setdefault("bed_targets", {})[args.bed] = {"layout": args.layout, "targets": targets}
a.CONFIG_PATH.write_text(json.dumps(cfg_disk, indent=2))
print(f"{args.bed}: saved {len(targets)} working aims")
ctl.stopped = True
