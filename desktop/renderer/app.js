// Tek Crafter renderer: talks to bot_server.py through window.tek
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let cfg = null;
let keys = { start_key: "F9", stop_key: "F10" };
let status = { running: false };
let calBed = null;
let capturing = null;
let saveTimer = null;

// ---------------------------------------------------------------- tabs / window
$$(".tab").forEach((t) => t.addEventListener("click", () => {
  $$(".tab").forEach((x) => x.classList.toggle("active", x === t));
  $$(".page").forEach((p) => p.classList.toggle("hidden", p.dataset.page !== t.dataset.tab));
}));
$$(".winbtn").forEach((b) => b.addEventListener("click", () => tek.win(b.dataset.win)));

// ---------------------------------------------------------------- saving
function save() {
  if (!cfg || status.running) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => tek.send({
    cmd: "save",
    config: { stations: cfg.stations, layouts: cfg.layouts, inventory_craft: cfg.inventory_craft,
              cycle_wait_minutes: cfg.cycle_wait_minutes, app: cfg.app },
  }), 350);
}
function bindNum(sel, get, set) {
  const el = $(sel);
  el.value = get();
  el.oninput = () => { const v = parseFloat(el.value); if (!isNaN(v)) { set(v); save(); } };
}
function bindText(sel, get, set) {
  const el = $(sel);
  el.value = get();
  el.oninput = () => { set(el.value.trim()); save(); };
}

// ---------------------------------------------------------------- rendering
const targetsOf = (bed) => (cfg.bed_targets?.[bed]?.targets || []).length;
const layoutLabel = (st) => cfg.layouts[st.layout]?.label || st.layout;

function renderStations() {
  $("#stations").innerHTML = cfg.stations.map((st, i) => `
    <div class="station ${st.enabled === false ? "off" : ""}">
      <label class="check"><input type="checkbox" data-st="${i}" ${st.enabled !== false ? "checked" : ""}></label>
      <div><div class="sname">${esc(st.name)}</div><div class="slabel">${esc(layoutLabel(st))}</div></div>
      <div class="beds">${st.beds.map((b, j) => {
        const n = targetsOf(b);
        return `<span class="chip ${j === 0 ? "main" : ""} ${n ? "" : "none"}" title="${j === 0 ? "main bed" : "spare"}">
          ${esc(b)} <b>${n || "–"}</b></span>`;
      }).join("")}</div>
    </div>`).join("");
  $$("#stations input[data-st]").forEach((c) => c.onchange = () => {
    cfg.stations[+c.dataset.st].enabled = c.checked; renderStations(); renderStart(); save();
  });
}

function renderStart() {
  const first = cfg.stations.find((s) => s.enabled !== false);
  const opts = [`<option value="">Travel to the first station</option>`]
    .concat((first?.beds || []).filter(targetsOf).map((b) => `<option value="${esc(b)}">I just spawned on ${esc(b)}</option>`));
  const sel = $("#f-start");
  const keep = sel.value;
  sel.innerHTML = opts.join("");
  sel.value = [...sel.options].some((o) => o.value === keep) ? keep : "";
}

// ---- station recipes (chem bench / fabricator), crafted in order
const PRESETS = {
  chem: { "Sparkpowder": { slot: [1383, 372] }, "Cementing Paste": { slot: [1475, 372] },
          "Gunpowder": { slot: [1568, 372] } },
  fab: { "Advanced Rifle Bullet": { search: "advanced rifle" }, "Advanced Sniper Bullet": { search: "advanced sniper" },
         "Advanced Simple Bullet": { search: "advanced simple" } },
};
const CUSTOM = "__custom";

function renderStationRecipes(key) {
  const lay = cfg.layouts[key];
  const rs = (lay.recipes = lay.recipes || []);
  const presets = PRESETS[key];
  const box = $(`#rec-${key}`);
  box.innerHTML = rs.map((r, i) => {
    const preset = presets[r.name] && (r.slot ? !!presets[r.name].slot : presets[r.name].search === r.search) ? r.name : CUSTOM;
    const opts = Object.keys(presets).map((n) => `<option ${n === preset ? "selected" : ""}>${esc(n)}</option>`).join("") +
                 `<option value="${CUSTOM}" ${preset === CUSTOM ? "selected" : ""}>Other (search)…</option>`;
    return `<div class="srec ${r.enabled === false ? "off" : ""}">
      <div class="order">${i + 1}</div>
      <div class="slot ${r.enabled !== false ? "on" : ""}" data-i="${i}" title="click to turn on/off">
        <span class="qty">x${r.presses * 100}</span>
        <svg><use href="#${key === "fab" ? "i-bullet" : "i-flask"}"/></svg></div>
      <div class="field"><label>Item</label><select data-i="${i}" data-k="preset">${opts}</select></div>
      <div class="field"><label>Search text</label><input data-i="${i}" data-k="search" value="${esc(r.search || "")}"
        ${r.slot ? 'disabled placeholder="fixed slot"' : ""}></div>
      <div class="field"><label>Pull</label><input data-i="${i}" data-k="pull_amount" value="${esc(r.pull_amount || "")}" placeholder="none"></div>
      <div class="field"><label>A presses</label><input type="number" min="1" max="50" data-i="${i}" data-k="presses" value="${r.presses}"></div>
      <button class="iconbtn mv" data-mv="-1" data-i="${i}" ${i === 0 ? "disabled" : ""} title="earlier"><svg><use href="#i-up"/></svg></button>
      <button class="iconbtn mv" data-mv="1" data-i="${i}" ${i === rs.length - 1 ? "disabled" : ""} title="later"><svg><use href="#i-down"/></svg></button>
      <button class="iconbtn" data-del="${i}" title="remove"><svg><use href="#i-trash"/></svg></button>
    </div>`;
  }).join("");
  const on = rs.filter((r) => r.enabled !== false).map((r) => r.name);
  $(`#sum-${key}`).textContent = on.length ? "→ " + on.join(" → ") : "→ nothing selected";
  const redo = () => { renderStationRecipes(key); save(); };
  box.querySelectorAll(".slot").forEach((s) => s.onclick = () => { const r = rs[+s.dataset.i]; r.enabled = r.enabled === false; redo(); });
  box.querySelectorAll("select").forEach((sel) => sel.onchange = () => {
    const r = rs[+sel.dataset.i];
    delete r.slot; delete r.search;
    if (sel.value === CUSTOM) { r.name = "Custom"; r.search = ""; }
    else { r.name = sel.value; Object.assign(r, JSON.parse(JSON.stringify(presets[sel.value]))); }
    redo();
  });
  box.querySelectorAll("input").forEach((el) => el.oninput = () => {
    const r = rs[+el.dataset.i], k = el.dataset.k;
    if (k === "presses") { const v = parseInt(el.value); if (v > 0) r.presses = v; }
    else if (k === "search") { r.search = el.value; if (!presets[r.name]) r.name = el.value || "Custom"; }
    else r[k] = el.value.trim();
    save();
  });
  box.querySelectorAll("[data-mv]").forEach((b) => b.onclick = () => {
    const i = +b.dataset.i, j = i + +b.dataset.mv;
    [rs[i], rs[j]] = [rs[j], rs[i]]; redo();
  });
  box.querySelectorAll("[data-del]").forEach((b) => b.onclick = () => { rs.splice(+b.dataset.del, 1); redo(); });
}
$$("[data-addrec]").forEach((b) => b.onclick = () => {
  const key = b.dataset.addrec;
  const first = Object.keys(PRESETS[key])[0];
  cfg.layouts[key].recipes.push({ name: first, ...JSON.parse(JSON.stringify(PRESETS[key][first])),
                                  pull_amount: "1000", presses: 10, enabled: true });
  renderStationRecipes(key); save();
});

function recipeIcon(r) {
  const n = (r.name + " " + r.search).toLowerCase();
  return n.includes("arrow") || n.includes("bullet") ? "i-bullet" : n.includes("net") ? "i-target" : "i-bag";
}
// Items craftable from your own inventory (full in-game names). The search
// text is the full name, so the first result is the right blueprint.
const INV_ITEMS = [
  "Stone Arrow", "Tranquilizer Arrow", "Bola", "Net Projectile", "Spear", "Wooden Club",
  "Slingshot", "Bow", "Torch", "Stone Pick", "Stone Hatchet", "Sickle", "Pike",
  "Wooden Shield", "Grappling Hook", "Flame Arrow", "Paintbrush", "Simple Bed",
  "Campfire", "Hide Sleeping Bag", "Cloth Shirt", "Cloth Pants", "Cloth Hat",
  "Cloth Gloves", "Cloth Boots", "Hide Shirt", "Hide Pants", "Hide Hat",
  "Hide Gloves", "Hide Boots", "Wooden Raft",
];
const ALIAS = { "net": "Net Projectile", "arrow": "Stone Arrow", "tranq arrow": "Tranquilizer Arrow" };

function recipeIcon(r) {
  const n = (r.name + " " + r.search).toLowerCase();
  return n.includes("arrow") || n.includes("bullet") || n.includes("spear") || n.includes("pike") ? "i-bullet"
       : n.includes("net") || n.includes("bola") ? "i-target" : "i-bag";
}
function normaliseInv(r) {
  // older entries used short names ("Net") - upgrade to the full name
  const full = ALIAS[(r.name || "").toLowerCase()] || INV_ITEMS.find((n) => n.toLowerCase() === (r.name || "").toLowerCase());
  if (full && r.custom !== true) { r.name = full; r.search = full.toLowerCase(); }
}
function renderRecipes() {
  const rs = cfg.inventory_craft.recipes;
  rs.forEach(normaliseInv);
  $("#recipes").innerHTML = rs.map((r, i) => {
    const known = !r.custom && INV_ITEMS.includes(r.name);
    const opts = INV_ITEMS.map((n) => `<option ${known && n === r.name ? "selected" : ""}>${esc(n)}</option>`).join("") +
                 `<option value="${CUSTOM}" ${known ? "" : "selected"}>Other (search)…</option>`;
    return `<div class="srec inv ${r.enabled === false ? "off" : ""}">
      <div class="order">${i + 1}</div>
      <div class="slot ${r.enabled !== false ? "on" : ""}" data-r="${i}" title="click to turn on/off">
        <span class="qty">x${r.presses}</span><svg><use href="#${recipeIcon(r)}"/></svg></div>
      <div class="field"><label>Item</label><select data-r="${i}">${opts}</select></div>
      <div class="field"><label>Search text</label><input data-k="search" data-r="${i}" value="${esc(r.search || "")}"
        ${known ? "disabled" : 'placeholder="type the item name"'}></div>
      <div class="field"><label>Pull</label><input data-k="pull_amount" data-r="${i}" value="${esc(r.pull_amount || "")}" placeholder="none"></div>
      <div class="field"><label>A presses</label><input type="number" min="1" max="50" data-k="presses" data-r="${i}" value="${r.presses}"></div>
      <button class="iconbtn mv" data-mv="-1" data-r="${i}" ${i === 0 ? "disabled" : ""} title="earlier"><svg><use href="#i-up"/></svg></button>
      <button class="iconbtn mv" data-mv="1" data-r="${i}" ${i === rs.length - 1 ? "disabled" : ""} title="later"><svg><use href="#i-down"/></svg></button>
      <button class="iconbtn" data-del="${i}" title="remove"><svg><use href="#i-trash"/></svg></button>
    </div>`;
  }).join("");
  const redo = () => { renderRecipes(); save(); };
  $$("#recipes .slot").forEach((s) => s.onclick = () => { const r = rs[+s.dataset.r]; r.enabled = r.enabled === false; redo(); });
  $$("#recipes select").forEach((sel) => sel.onchange = () => {
    const r = rs[+sel.dataset.r];
    if (sel.value === CUSTOM) { r.custom = true; r.name = r.search || "Custom"; }
    else { delete r.custom; r.name = sel.value; r.search = sel.value.toLowerCase(); }
    redo();
  });
  $$("#recipes input").forEach((el) => el.oninput = () => {
    const r = rs[+el.dataset.r], k = el.dataset.k;
    if (k === "presses") { const v = parseInt(el.value); if (v > 0) r.presses = v; }
    else if (k === "search") { r.search = el.value; r.name = el.value || "Custom"; }
    else r[k] = el.value.trim();
    el.closest(".srec").querySelector(".qty").textContent = "x" + r.presses;
    save();
  });
  $$("#recipes [data-mv]").forEach((b) => b.onclick = () => {
    const i = +b.dataset.r, j = i + +b.dataset.mv; [rs[i], rs[j]] = [rs[j], rs[i]]; redo();
  });
  $$("#recipes [data-del]").forEach((b) => b.onclick = () => { rs.splice(+b.dataset.del, 1); redo(); });
}
$("#btn-add").onclick = () => {
  cfg.inventory_craft.recipes.push({ name: "Stone Arrow", search: "stone arrow", pull_amount: "100", presses: 1, enabled: true });
  renderRecipes(); save();
};

function renderSlots() {
  const beds = cfg.stations.flatMap((st) => st.beds.map((b) => ({ b, st })));
  if (!calBed || !beds.some((x) => x.b === calBed)) calBed = beds[0]?.b;
  $("#slots").innerHTML = beds.map(({ b, st }) => {
    const n = targetsOf(b);
    return `<button class="bedslot ${b === calBed ? "sel" : ""} ${n ? "" : "none"}" data-bed="${esc(b)}">
      <span class="qty">${esc(st.name)}</span>
      <svg><use href="#${st.layout === "fab" ? "i-bullet" : "i-flask"}"/></svg>
      <span class="bname">${esc(b)}</span><span class="cnt">${n ? n + " aims" : "none"}</span></button>`;
  }).join("");
  $$(".bedslot").forEach((s) => s.onclick = () => { calBed = s.dataset.bed; renderSlots(); });
  $("#cal-name").textContent = calBed || "–";
}

function renderAll() {
  renderStations();
  renderStart();
  bindNum("#f-wait", () => cfg.cycle_wait_minutes, (v) => cfg.cycle_wait_minutes = v);
  renderStationRecipes("chem");
  renderStationRecipes("fab");
  renderRecipes();
  bindNum("#f-inv-wait", () => cfg.inventory_craft.wait_minutes, (v) => cfg.inventory_craft.wait_minutes = v);
  renderSlots();
  $("#k-start").textContent = keys.start_key;
  $("#k-stop").textContent = keys.stop_key;
  $$(".keycap").forEach((k) => k.classList.remove("wait"));
  const ov = $("#f-overlay");
  ov.checked = cfg.app.overlay !== false;
  ov.onchange = () => { cfg.app.overlay = ov.checked; save(); };
  const job = cfg.app.last_job || "loop";
  $$("input[name=job]").forEach((r) => {
    r.checked = r.value === job;
    r.onchange = () => { cfg.app.last_job = r.value; save(); };
  });
  $("#hk-hint").textContent = `${keys.start_key} start / pause  ·  ${keys.stop_key} stop`;
}

// ---------------------------------------------------------------- controls
$("#btn-go").onclick = () => {
  if (status.running) return tek.send({ cmd: "toggle" });
  const job = $("input[name=job]:checked").value;
  tek.send({ cmd: "start", job, here: job === "loop" ? ($("#f-start").value || null) : null });
};
$("#btn-stop").onclick = () => tek.send({ cmd: "stop" });
$("#btn-cal").onclick = () => calBed && tek.send({ cmd: "calibrate", bed: calBed });
for (const [id, which] of [["#k-start", "start_key"], ["#k-stop", "stop_key"]]) {
  $(id).onclick = () => {
    if (status.running) return;
    capturing = which;
    $(id).textContent = "PRESS A KEY…";
    $(id).classList.add("wait");
    tek.send({ cmd: "capture_key", which });
  };
}

function fmtLeft(t) {
  const s = Math.max(0, Math.round(t - Date.now() / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function onStatus(st) {
  status = st;
  const p = st.progress || null;
  const go = $("#btn-go");
  let title = "Idle", sub = "Ready", desc = "Pick a job and press START, or use your hotkey in game.";
  let prompt = `<span class="c">[${esc(keys.start_key)}] : Start</span>`;
  if (st.running) {
    if (st.stopping) { title = "Stopping"; sub = "finishing the current step"; }
    else if (st.paused) { title = "Paused"; sub = `press ${keys.start_key} to resume`; }
    else if (!st.focused) { title = "Waiting for ARK"; sub = "switch to the game window"; }
    else if (st.next_run) { title = "Waiting"; sub = `next run in ${fmtLeft(st.next_run)}`; }
    else { title = "Running"; sub = st.status || ""; }
    desc = st.job === "inventory" ? "Crafting from your own inventory." : "Stations loop: crafting at each bed, then waiting.";
    prompt = `<span class="c">[${esc(keys.start_key)}] : ${st.paused ? "Resume" : "Pause"}</span><br>` +
             `<span class="c">[${esc(keys.stop_key)}] : Stop</span><br>` +
             (p ? `<span class="g">${esc(p.station)} (${esc(p.bed)}) : ${p.done} / ${p.total}</span>` : "");
    go.querySelector("span").textContent = st.paused ? "RESUME" : "PAUSE";
    go.querySelector("use").setAttribute("href", st.paused ? "#i-play" : "#i-pause");
  } else if (st.calibrating) {
    title = "Calibrating"; sub = `${calBed || ""} - hands off the mouse`;
    prompt = `<span class="y">Calibrating…</span>`;
  } else {
    go.querySelector("span").textContent = "START";
    go.querySelector("use").setAttribute("href", "#i-play");
  }
  $("#st-name").textContent = title;
  $("#st-sub").textContent = sub;
  $("#st-desc").textContent = desc;
  $("#prompt").innerHTML = prompt;
  $("#r-station").textContent = p ? `${p.station} · ${p.bed}` : "–";
  $("#r-done").textContent = p ? `${p.done} / ${p.total}${p.failed ? `  (${p.failed} missed)` : ""}` : "–";
  $("#r-current").textContent = p?.current || "–";
  $("#r-cycle").textContent = p ? p.cycle : "–";
  $("#r-next").textContent = st.next_run ? fmtLeft(st.next_run) : "–";
  $("#bar-fill").style.width = p && p.total ? `${(100 * p.visited) / p.total}%` : "0%";
  const busy = st.running || st.calibrating;
  $(".content").classList.toggle("locked", !!busy);
  $("#btn-cal").disabled = !!busy;
  $$("input[name=job]").forEach((r) => (r.disabled = !!busy));
  $("#f-start").disabled = !!busy;
}

// ---------------------------------------------------------------- log
function log(line) {
  const box = $("#log");
  const div = document.createElement("div");
  const cls = /^\s*!|FAILED|CRASH|PAUSED|did not open|never/.test(line) ? "bad"
            : /queued|OK$|saved|crafted/.test(line) ? "ok"
            : /^\[|calibrat|hotkey/.test(line) ? "sys" : "";
  const t = new Date().toTimeString().slice(0, 8);
  div.innerHTML = `<span class="t">${t}</span><span class="${cls}">${esc(line)}</span>`;
  const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
  box.appendChild(div);
  while (box.childElementCount > 600) box.firstChild.remove();
  if (atBottom) box.scrollTop = box.scrollHeight;
}

// ---------------------------------------------------------------- events
tek.on((ev) => {
  if (ev.ev === "state") {
    const editing = cfg && document.activeElement?.matches?.("input, select");
    if (editing) {
      // keep the user's in-progress edits; only take server-owned data
      cfg.bed_targets = ev.config.bed_targets; keys = ev.keys; capturing = null;
      renderStations(); renderSlots();
    } else {
      cfg = ev.config; keys = ev.keys; capturing = null;
      if (!status.running) renderAll(); else { renderStations(); renderSlots(); }
    }
  } else if (ev.ev === "status") {
    onStatus(ev);
  } else if (ev.ev === "log") {
    log(ev.line);
  } else if (ev.ev === "fake_status") {   // screenshot test mode
    onStatus({ running: true, focused: true, job: "loop", status: "CB1B #12",
      progress: { station: "CB1", bed: "CB1B", current: "CB1B #12", done: 11, failed: 0, visited: 11, total: 17, cycle: 3 } });
    for (const l of ["Station CB1: beds CB1B, CB1A", "  travelling to CB1B", "[19:18:21] CB1 on CB1B (17 targets)",
                     "  CB1B #1: queued (5.7s)", "  ! CB2C #14: nothing to open there (attempt 1)", "  CB1B #11: queued (5.8s)"]) log(l);
  }
});
tek.send({ cmd: "state" });
