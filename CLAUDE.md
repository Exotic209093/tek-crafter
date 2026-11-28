# Tek Crafter (ARK crafting bot)

See README.md for layout. Facts that aren't obvious from the code:

- Never drive the game while the user is playing it unasked. Test UI changes with an off-screen
  render: `$env:TEK_CAPTURE='<abs path>.png'; $env:TEK_CAPTURE_IDLE='1'; desktop\node_modules\electron\dist\electron.exe desktop`
  (backend runs with `--no-hotkeys`, writes `<name>_inventory.png` etc.).
- Camera turns are exact only with ARK mouse smoothing off (see README). ~5000 counts per 360.
- Bench/fab detection = cyan "[E] : Turn Off" template; own-inventory open = INVENTORY *or* CRAFTING
  header (the active tab's header is the bright one).
- The app is an in-game overlay: see-through panel toggled by the panel hotkey (default Insert, polled in
  bot_server.py), tray icon to open/quit, click-through HUD bottom-right. Never put overlay pixels where
  the bot reads the screen (top-left inventory headers, amount boxes, item grids).
- Text boxes: always `clear_box()` (click, End, Backspace). A click lands mid-text.
- The live app saves `ark_chem_config.json`; don't hand-edit it while the app is open.
- bot_server writes `logs/bot_YYYYMMDD.log` (every printed line) and `logs/health_YYYYMMDD.log`
  (each minute: RAM/commit, ARK private memory/handles/hung flag, backend memory). Check these first
  when an overnight run dies. ARK install is `C:\Program Files (x86)\Steam\steamapps\common\ARK`;
  Steam `logs\content_log.txt` "346110 state changed" lines give ARK start/exit times.
- Run loops set `Control.unattended`: when ARK loses focus mid-step, `check()` raises `FocusLost` once
  it's back and the loop closes UI and respawns at the station; after `refocus_idle_s` without user
  input it restores ARK itself, and failure pauses auto-resume after `auto_resume_min` idle. Any
  window popping up overnight (scheduled tasks!) used to wreck the run this way.
- Inventory crafting is still unverified in game (`shots/inv_debug/` holds per-step screenshots).

## Verify

```
python -m py_compile ark_chem.py bot_server.py calibrate_bed.py aimfind.py slotpick.py
python test_checks.py
node --check desktop/main.js; node --check desktop/renderer/app.js; node --check desktop/renderer/overlay.js
```
