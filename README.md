# Tek Crafter

Crafting automation for ARK: Survival Evolved (1920x1080, first person). It
fast-travels between bed "stations", opens every chem bench / fabricator,
pulls resources and queues crafts, then waits and repeats. It can also craft
from your own inventory.

## Run

Desktop app (Electron UI + Python backend):

```
cd desktop
npm install
npx electron .
```

Hotkeys (rebindable in Settings): **F9** start / pause, **F10** stop.

Command line (no UI):

```
python ark_chem.py --now run                 # stations loop from config
python ark_chem.py --now run --stations CB1  # one station
python ark_chem.py --now test-bed CB1B        # craft one bed once
```

Needs Python 3.12+ with `numpy` and `Pillow`, and Node 20+.

## Layout

| Path | What |
|---|---|
| `ark_chem.py` | engine: input, screen checks, camera, benches, beds, loops |
| `bot_server.py` | JSON-lines backend the desktop app talks to |
| `desktop/` | Electron app (`main.js`, `renderer/`, `assets/`) |
| `calibrate_bed.py`, `aimfind.py` | sweep a room from a bed and save its bench aims |
| `slotpick.py` | tells recipe / stored stack / empty item slots apart |
| `templates/` | screen-check templates and room reference strips |
| `ark_chem_config.json` | stations, recipes, per-bed calibrated aims, hotkeys |
| `ark_chem_app.pyw` | old tkinter app (superseded by `desktop/`) |
| other `*_test.py`, `calib_*.py` | calibration / diagnosis helpers |

## Requirements in game

- ARK `Input.ini`, under `[/Script/Engine.InputSettings]`:
  `bEnableMouseSmoothing=False` and `bViewAccelerationEnabled=False`.
  With smoothing on, camera turns are not repeatable and aims drift.
- Keep the in-game mouse sensitivity unchanged after calibrating.
- Every bed the bot uses has a unique name (CB1A, CB1B, CB2A, ...).
