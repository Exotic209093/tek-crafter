const o = document.getElementById("o");
const e = (s) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
let keys = { start_key: "F9", stop_key: "F10" };
tek.on((ev) => {
  if (ev.ev === "state") keys = ev.keys;
  if (ev.ev !== "status") return;
  if (ev.calibrating && !ev.running) { o.innerHTML = `<div class="y">Calibrating</div><div class="w">(hands off the mouse)</div>`; return; }
  if (!ev.running) { o.innerHTML = ""; return; }
  const p = ev.progress;
  let state = `<span class="y">${ev.paused ? "Paused" : ev.stopping ? "Stopping" : "Crafting"}</span>`;
  if (ev.next_run && !ev.paused) {
    const s = Math.max(0, Math.round(ev.next_run - Date.now() / 1000));
    state = `<span class="y">Next run in ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}</span>`;
  }
  o.innerHTML =
    `<div>${state}</div>` +
    `<div class="c">[${e(keys.start_key)}] : ${ev.paused ? "Resume" : "Pause"} &nbsp; [${e(keys.stop_key)}] : Stop</div>` +
    (p ? `<div class="g">${e(p.station)} (${e(p.bed)}) : ${p.done} / ${p.total}` +
         (p.failed ? ` <span class="r">(${p.failed} missed)</span>` : "") + ` &nbsp;<span class="w">Cycle ${p.cycle}</span></div>` +
         `<div class="bar"><div style="width:${p.total ? (100 * p.visited / p.total) : 0}%"></div></div>` : "");
});

