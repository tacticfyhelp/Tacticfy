// Tacticfy browser UI. Talks to the local Python server (src/web/server.py) over a small JSON API.
// FM27 names (roles, instruction tiles, formations, players) are shown exactly as sent; everything
// else is translated client-side from the /api/i18n bundle.
"use strict";

/* ------------------------------------------------------------------ state */
const S = {
  meta: null,
  i18n: null,                 // {lang, dir, strings, attrs}
  lang: "en",
  theme: "light",
  tab: "tactics",
  mode: "BEST",               // BEST / SECOND / DROPOFF / BENCH
  state: null,                // last /api/state payload
  selectedSlot: null,
  squadSort: { key: "ca", dir: -1 },
  squadFilter: "",
  loading: false,
  offline: false,
};

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function store(key, value) { try { localStorage.setItem("tacticfy." + key, value); } catch (e) { /* ignore */ } }
function load(key) { try { return localStorage.getItem("tacticfy." + key); } catch (e) { return null; } }

/* ------------------------------------------------------------------ html + i18n helpers */
const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ESC[c]);

/** Trusted HTML fragment (already escaped). */
class Html { constructor(s) { this.s = s; } toString() { return this.s; } }
const H = (s) => new Html(s);

/** An English FM27 name isolated so it reads correctly inside Hebrew text. */
const fm = (s) => H(`<bdi dir="ltr">${esc(s)}</bdi>`);

function str(key) {
  const t = S.i18n && S.i18n.strings;
  return (t && t[key] !== undefined) ? t[key] : key;
}
const has = (key) => !!(S.i18n && S.i18n.strings[key] !== undefined);

function argText(v) {
  if (v && typeof v === "object" && v.$t) return str(v.$t);
  if (Array.isArray(v)) return v.map(attrName).join(", ");
  return v;
}

/** Plain-text translation with {placeholders}. */
function tr(key, args = {}) {
  return str(key).replace(/\{(\w+)\}/g, (m, name) => (name in args ? String(argText(args[name])) : m));
}

/** HTML translation: the template is escaped; Html args are inserted as-is, others escaped. */
function trh(key, args = {}) {
  return esc(str(key)).replace(/\{(\w+)\}/g, (m, name) => {
    if (!(name in args)) return m;
    const v = args[name];
    return v instanceof Html ? v.s : esc(argText(v));
  });
}

const attrName = (a) => (S.i18n && S.i18n.attrs[a]) || String(a).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
const opt = (prefix, value) => (has(prefix + value) ? str(prefix + value) : value);
const trCategory = (c) => opt("category.", c);
const trFocus = (f) => opt("training.focus.", f);
const trIntensity = (i) => opt("training.intensity.", i);
const trStyle = (s) => opt("style.", s);

/** Engine reason (key + args) -> HTML; role names stay FM27 English, attribute lists are translated. */
function reasonHtml(key, args = {}) {
  if (!key) return "";
  const a = {};
  for (const [k, v] of Object.entries(args || {})) a[k] = k === "role" ? fm(v) : v;
  return trh(key, a);
}

function trainingReasonHtml(rec) {
  let html = reasonHtml(rec.reason_key, rec.reason_args);
  const attrs = (rec.reason_args && rec.reason_args.attrs) || [];
  if (rec.reason_key !== "training.reason.focus_gap" && rec.additional_focus !== "None" && attrs.length) {
    html += trh("training.reason.focus_suffix", { attrs });
  }
  return html;
}

const num = (v, d = 1) => (typeof v === "number" ? v.toFixed(d) : "—");

/* ------------------------------------------------------------------ API */
async function api(path, body) {
  const init = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Tacticfy": "1" },
    body: JSON.stringify(body),
  };
  let resp;
  try {
    resp = await fetch(path, init);
  } catch (e) {
    showOffline();
    throw e;
  }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const err = new Error("api");
    err.key = (data.error && data.error.key) || "web.error.title";
    err.args = (data.error && data.error.args) || {};
    throw err;
  }
  return data;
}

function apiErrorModal(err) {
  if (S.offline) return;
  const detail = err.args && err.args.detail ? `<p class="mt-2 text-xs text-ink-3">${esc(err.args.detail)}</p>` : "";
  const title = has(err.key + "") && err.key.endsWith(".title") ? str(err.key) : str("web.error.title");
  const body = err.key.endsWith(".title") ? detail : `<p>${trh(err.key, err.args)}</p>${detail}`;
  modal({ title, body: body || `<p>${esc(str("web.error.title"))}</p>`, actions: [{ label: str("web.ok"), primary: true }] });
}

/* ------------------------------------------------------------------ modal / toast / offline */
function modal({ title, body, actions }) {
  const dlg = $("#modal");
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = body;
  const bar = $("#modal-actions");
  bar.innerHTML = "";
  return new Promise((resolve) => {
    for (const a of actions) {
      const b = document.createElement("button");
      b.type = a.submit ? "button" : "submit";
      b.className = "btn " + (a.primary ? "btn-primary" : "");
      b.textContent = a.label;
      b.addEventListener("click", async (ev) => {
        if (a.onClick) {
          ev.preventDefault();
          const keepOpen = await a.onClick(b);
          if (keepOpen) return;
          dlg.close();
        }
        resolve(a.value);
      });
      bar.appendChild(b);
    }
    dlg.addEventListener("close", () => resolve(undefined), { once: true });
    dlg.showModal();
  });
}

let toastTimer = 0;
function toast(text, kind = "info") {
  const box = $("#toast");
  box.innerHTML = `<div class="toast toast-${kind}">${esc(text)}</div>`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.innerHTML = ""; }, 4200);
}

function showOffline(stopped = false) {
  S.offline = true;
  const el = $("#offline");
  $("#offline-title").textContent = str(stopped ? "web.stopped.title" : "web.offline.title");
  $("#offline-body").textContent = str(stopped ? "web.stopped.body" : "web.offline.body");
  el.classList.remove("hidden");
  el.classList.add("flex");
  const dlg = $("#modal");
  if (dlg.open) dlg.close();
}

/* ------------------------------------------------------------------ language / theme */
async function setLanguage(lang) {
  S.i18n = await api("/api/i18n/" + lang);
  S.lang = lang;
  store("lang", lang);
  document.documentElement.lang = lang;
  document.documentElement.dir = S.i18n.dir;
  document.title = `Tacticfy ${S.meta ? S.meta.version : ""} – ${str("app.title")}`;
  for (const el of $$("[data-i18n]")) el.textContent = str(el.dataset.i18n);
  for (const el of $$("[data-i18n-title]")) el.title = str(el.dataset.i18nTitle);
  for (const el of $$("[data-i18n-placeholder]")) el.placeholder = str(el.dataset.i18nPlaceholder);
  renderControls();
  renderTheme();
  renderAll();
}

function setTheme(theme) {
  S.theme = theme;
  store("theme", theme);
  document.documentElement.classList.toggle("dark", theme === "dark");
  renderTheme();
}

function renderTheme() {
  $("#btn-theme").textContent = tr("toolbar.theme", { name: str(S.theme === "dark" ? "theme.Dark" : "theme.Light") });
}

/* ------------------------------------------------------------------ toolbar controls */
function renderControls() {
  if (!S.meta) return;
  const st = S.state ? S.state.settings : {};
  const style = $("#sel-style");
  style.innerHTML = S.meta.styles.map((s) => `<option value="${esc(s)}">${esc(trStyle(s))}</option>`).join("");
  if (st.style) style.value = st.style;

  const form = $("#sel-formation");
  const auto = S.meta.auto_formations.map((f) => `<option value="${esc(f.value)}">${esc(str(f.key))}</option>`).join("");
  const groups = ["standard", "tactical_meta"].map((cat) => {
    const items = S.meta.formations.filter((f) => f.category === cat)
      .map((f) => `<option value="${esc(f.name)}">${esc(f.name)}</option>`).join("");
    return `<optgroup label="${esc(str("formation.category." + cat))}">${items}</optgroup>`;
  }).join("");
  form.innerHTML = auto + groups;
  if (st.formation) form.value = st.formation;

  $("#chk-important").checked = !!st.important;
  renderLoadButton();
}

function renderLoadButton() {
  const btn = $("#btn-load");
  btn.disabled = S.loading;
  $("#load-spinner").classList.toggle("hidden", !S.loading);
  $("#load-label").textContent = str(S.loading ? "toolbar.scanning" : "toolbar.load");
}

function renderStatus() {
  const el = $("#status");
  const st = S.state && S.state.status;
  if (!st) { el.textContent = ""; return; }
  const text = S.loading ? str("status.scanning") : tr(st.key, st.args).replace(/\s+/g, " ").trim();
  el.textContent = text;
  el.title = text;
  el.className = "min-w-0 flex-1 truncate text-end text-xs " + ({
    success: "text-good", warning: "text-warn", error: "text-bad", info: "text-accent-ink",
  }[st.kind] || "text-ink-3");
}

/* ------------------------------------------------------------------ tabs / modes */
function setTab(tab) {
  S.tab = tab;
  store("tab", tab);
  for (const b of $$("[data-tab]")) b.setAttribute("aria-selected", String(b.dataset.tab === tab));
  for (const v of $$("[data-view]")) v.classList.toggle("hidden", v.dataset.view !== tab);
}

function setMode(mode) {
  S.mode = mode;
  for (const b of $$("[data-mode]")) b.setAttribute("aria-selected", String(b.dataset.mode === mode));
  $("#pitches").classList.toggle("hidden", mode === "BENCH");
  $("#bench").classList.toggle("hidden", mode !== "BENCH");
  renderTactics();
}

/* ------------------------------------------------------------------ rendering */
const A = () => S.state && S.state.analysis;

function renderAll() {
  renderStatus();
  renderTactics();
  renderSquad();
  renderAdvisor();
}

function renderTactics() {
  const a = A();
  const summary = $("#summary");
  $("#btn-copy").disabled = !a;
  if (!a) {
    summary.textContent = str("tactics.prompt");
    $("#pitches").innerHTML = "";
    $("#bench").innerHTML = `<p class="text-sm text-ink-3">${esc(str("tactics.prompt"))}</p>`;
    $("#instructions").innerHTML = `<p class="text-ink-3">${esc(str("tactics.instructions_placeholder"))}</p>`;
    $("#detail").innerHTML = "";
    return;
  }
  const L = a.lineup;
  const parts = [
    `${fm(L.formation)}`,
    esc(trStyle(L.style)),
    `${esc(str("tactics.summary.synergy"))} <span class="text-accent-ink">${num(L.synergy)}</span>`,
  ];
  if (L.important) parts.push(esc(str("tactics.summary.important")));
  if (S.state.pool_key) parts.push(`<span class="font-normal text-ink-3">${esc(str(S.state.pool_key))}</span>`);
  summary.innerHTML = parts.join(" · ");

  if (S.mode === "BENCH") renderBench(a.bench);
  else renderPitches(L);
  renderInstructions(L.instructions);
  renderDetail();
}

/* ---- pitch (SVG) */
const PITCH = { w: 100, h: 128, top: 1, pad: 4 };

function layoutNodes(slots, phase, labelW, blockH) {
  const inner = { x: PITCH.pad + labelW / 2, y: PITCH.top + 6, w: PITCH.w - 2 * (PITCH.pad + labelW / 2),
                  h: PITCH.h - PITCH.top - 6 - blockH - PITCH.pad };
  const pts = slots.map((s) => {
    const [x, y] = phase === "IP" ? s.ip_xy : s.oop_xy;
    return [inner.x + (x / 100) * inner.w, inner.y + (1 - y / 100) * inner.h];
  });
  // Push apart nodes whose (circle + label) boxes would touch; same rules as the desktop pitch.
  const minDx = labelW + 1.6, minDy = blockH + 1;
  const rank = { L: 0, C: 1, R: 2 };
  for (let it = 0; it < 80; it++) {
    let moved = false;
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const dx = pts[j][0] - pts[i][0], dy = pts[j][1] - pts[i][1];
        const ox = minDx - Math.abs(dx), oy = minDy - Math.abs(dy);
        if (ox <= 0 || oy <= 0) continue;
        moved = true;
        if (ox <= oy * 1.6) {
          const sign = Math.abs(dx) < 0.1 ? ((rank[slots[j].side] ?? 1) >= (rank[slots[i].side] ?? 1) ? 1 : -1) : Math.sign(dx);
          const shift = ox / 2 + 0.1;
          pts[i][0] -= sign * shift; pts[j][0] += sign * shift;
        } else {
          const sign = dy >= 0 ? 1 : -1, shift = oy / 2 + 0.1;
          pts[i][1] -= sign * shift; pts[j][1] += sign * shift;
        }
      }
    }
    for (const p of pts) {
      p[0] = Math.min(Math.max(p[0], inner.x), inner.x + inner.w);
      p[1] = Math.min(Math.max(p[1], inner.y), inner.y + inner.h);
    }
    if (!moved) break;
  }
  return pts;
}

/** Shorten SVG label text to fit ``width`` (viewBox units) at ``size`` font units (~0.56em per glyph). */
function fit(text, width, size, bold = false) {
  const max = Math.max(3, Math.floor(width / (size * (bold ? 0.6 : 0.54))));
  return text.length > max ? text.slice(0, max - 1) + "…" : text;
}

function pitchSvg(slots, phase, dropoff, compare) {
  const r = 4.1, labelW = 22, labelH = 8.4, gap = 1, blockH = 2 * r + gap + labelH;
  const pts = layoutNodes(slots, phase, labelW, blockH);
  const { w, h, top } = PITCH;
  const ix = 3, iy = top, iw = w - 6, ih = h - top - 3;
  const lines = [
    `<rect x="${ix}" y="${iy}" width="${iw}" height="${ih}" rx="2.4" class="fill-turf stroke-turf-edge" stroke-width=".4"/>`,
    ...Array.from({ length: 5 }, (_, k) => `<rect x="${ix}" y="${iy + (2 * k) * ih / 10}" width="${iw}" height="${ih / 10}" class="fill-turf-stripe"/>`),
    `<g class="stroke-pitch-line" fill="none" stroke-width=".35">`,
    `<rect x="${ix + 2}" y="${iy + 2}" width="${iw - 4}" height="${ih - 4}"/>`,
    `<line x1="${ix + 2}" y1="${iy + ih / 2}" x2="${ix + iw - 2}" y2="${iy + ih / 2}"/>`,
    `<circle cx="${w / 2}" cy="${iy + ih / 2}" r="9"/>`,
    `<rect x="${w / 2 - 23}" y="${iy + 2}" width="46" height="17"/><rect x="${w / 2 - 11}" y="${iy + 2}" width="22" height="6"/>`,
    `<rect x="${w / 2 - 23}" y="${iy + ih - 19}" width="46" height="17"/><rect x="${w / 2 - 11}" y="${iy + ih - 8}" width="22" height="6"/>`,
    `</g>`,
  ];
  const nodes = slots.map((s, i) => {
    const [x, y] = pts[i];
    const role = (phase === "IP" ? s.ip_role : s.oop_role).split("(")[0].trim();
    const score = compare ? `-${Math.round(dropoff[s.slot_id] || 0)}` : String(Math.round(phase === "IP" ? s.ip_score : s.oop_score));
    const alert = phase === "OOP" && s.transition_alert;
    const fill = alert ? "fill-node-alert" : (phase === "IP" ? "fill-node-ip" : "fill-node-oop");
    const sel = S.selectedSlot === s.slot_id;
    return `<g class="node cursor-pointer" data-slot="${esc(s.slot_id)}" tabindex="0" role="button" aria-label="${esc(s.name)} – ${esc(role)}">
      <circle cx="${x}" cy="${y + .4}" r="${r}" class="fill-black/25"/>
      <circle cx="${x}" cy="${y}" r="${r}" class="${fill} stroke-white" stroke-width="${sel ? 1 : .55}"/>
      <text x="${x}" y="${y + 1.25}" text-anchor="middle" class="fill-white font-bold" font-size="3.4">${esc(score)}</text>
      <rect x="${x - labelW / 2}" y="${y + r + gap}" width="${labelW}" height="${labelH}" rx="1.6" class="${sel ? "fill-label-sel" : "fill-label"} stroke-label-edge" stroke-width=".25"/>
      <text x="${x}" y="${y + r + gap + 3.5}" text-anchor="middle" class="fill-label-ink font-semibold" font-size="2.8">${esc(fit(s.surname, labelW - 2, 2.8, true))}</text>
      <text x="${x}" y="${y + r + gap + 6.9}" text-anchor="middle" class="${phase === "IP" ? "fill-role-ip" : "fill-role-oop"}" font-size="2.15">${esc(fit(role, labelW - 1.6, 2.15))}</text>
    </g>`;
  });
  const title = str(phase === "IP" ? "tactics.pitch.ip" : "tactics.pitch.oop");
  return `<figure class="min-w-0"><figcaption class="mb-1 text-center text-xs font-semibold text-ink-2">${esc(title)}</figcaption>
    <svg viewBox="0 0 ${w} ${h}" class="block h-auto w-full select-none" role="img" aria-label="${esc(title)}">${lines.join("")}${nodes.join("")}</svg></figure>`;
}

function renderPitches(L) {
  const slots = S.mode === "SECOND" && L.second_xi.length ? L.second_xi : L.best_xi;
  const compare = S.mode === "DROPOFF";
  const box = $("#pitches");
  box.innerHTML = pitchSvg(slots, "IP", L.dropoff, compare) + pitchSvg(slots, "OOP", L.dropoff, compare);
}

function currentSlots() {
  const a = A();
  if (!a) return [];
  return S.mode === "SECOND" && a.lineup.second_xi.length ? a.lineup.second_xi : a.lineup.best_xi;
}

/* ---- instructions + detail */
function sectionTitle(text) {
  return `<h3 class="mt-3 mb-1 text-[10px] font-semibold tracking-wide text-accent-ink uppercase">${esc(text)}</h3>`;
}

function renderInstructions(ins) {
  const section = (titleKey, tiles) => {
    let current = null;
    const rows = tiles.map((t) => {
      let head = "";
      if (t.phase && t.phase !== current) {
        head = `<tr><td colspan="2" class="pt-1.5 pb-0.5 text-[10px] text-ink-3">${esc(opt("tactics.phase.", t.phase))}</td></tr>`;
        current = t.phase;
      }
      return `${head}<tr><td class="py-px pe-3 align-top text-ink-2">${fm(t.tile)}</td><td class="py-px align-top">${fm(t.value)}</td></tr>`;
    }).join("");
    return sectionTitle(str(titleKey)) + `<table class="w-full">${rows}</table>`;
  };
  let html = `<p class="text-sm"><b>${esc(str("tactics.mentality"))}</b> <span class="text-ink-2">${fm(ins.mentality)}</span></p>`;
  html += section("tactics.section.ip", ins.in_possession);
  html += section("tactics.section.transition", ins.in_transition);
  html += section("tactics.section.oop", ins.out_of_possession);
  if (ins.notes.length) {
    html += sectionTitle(str("tactics.section.notes"));
    html += `<ul class="list-disc space-y-0.5 ps-4 text-ink-2">${ins.notes.map((n) => `<li>${fm(n)}</li>`).join("")}</ul>`;
  }
  $("#instructions").innerHTML = html;
}

function renderDetail() {
  const box = $("#detail");
  const slot = currentSlots().find((s) => s.slot_id === S.selectedSlot);
  if (!slot) { box.innerHTML = `<p class="text-ink-3">${esc(str("tactics.click_hint"))}</p>`; return; }
  const alert = slot.transition_alert
    ? `<p class="text-bad"><b>${esc(str("tactics.detail.alert"))}:</b> ${fm(slot.transition_alert)}</p>`
    : `<p class="text-good">${esc(str("tactics.detail.optimal"))}</p>`;
  const pis = slot.instructions.length
    ? `<ul class="list-disc space-y-0.5 ps-4">${slot.instructions.map((p) => `<li>${fm(p)}</li>`).join("")}</ul>`
    : `<p class="text-ink-3">—</p>`;
  const rec = (A().training || []).find((r) => r.player_id === slot.player_id);
  const training = rec ? sectionTitle(str("tactics.detail.training")) +
    `<p>${fm(rec.role_focus)} · ${esc(trFocus(rec.additional_focus))} · <b class="${intensityClass(rec.intensity)}">${esc(trIntensity(rec.intensity))}</b></p>
     <p class="mt-0.5 text-ink-3">${trainingReasonHtml(rec)}</p>` : "";
  box.innerHTML = `
    <p class="text-sm"><b>${fm(slot.name)}</b> <span class="text-ink-3">${esc(slot.slot_id)}</span></p>
    <div class="mt-1 space-y-0.5 text-ink-2">
      <p>${esc(str("tactics.detail.ip"))}: <span class="text-ink">${fm(slot.ip_role)}</span> (${num(slot.ip_score)})</p>
      <p>${esc(str("tactics.detail.oop"))}: <span class="text-ink">${fm(slot.oop_role)}</span> (${num(slot.oop_score)})</p>
      <p>${esc(str("tactics.detail.displacement"))}: <bdi dir="ltr">${num(slot.transition_distance)}m</bdi></p>
      ${alert}
    </div>
    ${sectionTitle(str("tactics.detail.pi"))}${pis}${training}`;
}

function intensityClass(intensity) {
  return { "Double Intensity": "text-good", "Half Intensity": "text-warn" }[intensity] || "text-ink-2";
}

/* ---- bench */
function renderBench(plan) {
  const box = $("#bench");
  const sizes = S.meta.bench_sizes.map((n) => `<option value="${n}" ${S.state.settings.bench_size === n ? "selected" : ""}>${n}</option>`).join("");
  let html = `<div class="mb-3 flex items-center justify-between gap-3">
      <h2 class="text-sm font-semibold">${esc(str("bench.title"))}</h2>
      <label class="flex items-center gap-2 text-xs text-ink-3" title="${esc(str("bench.size_tip"))}">${esc(str("bench.size"))}
        <select id="sel-bench" class="field w-16">${sizes}</select></label></div>`;
  if (!plan || !plan.bench.length) {
    box.innerHTML = html + `<p class="text-sm text-ink-3">${esc(str("bench.empty"))}</p>`;
    return;
  }
  const head = ["bench.col.player", "bench.col.pos", "bench.col.cover", "bench.col.covers", "bench.col.best", "bench.col.impact"]
    .map((k) => `<th class="px-2 py-1.5 text-start font-semibold text-ink-3">${esc(str(k))}</th>`).join("");
  const rows = plan.bench.map((b, i) => `<tr class="border-t border-line">
      <td class="px-2 py-1.5 font-semibold">${i + 1}. ${fm(b.name)}</td>
      <td class="px-2 py-1.5 text-ink-2">${fm(b.positions.join("/"))}</td>
      <td class="px-2 py-1.5 ${b.role === "backup_gk" ? "text-accent-ink" : "text-good"}">${esc(str("bench.role." + b.role))}</td>
      <td class="px-2 py-1.5 text-ink-2">${fm(b.covered_positions.join(", ") || "—")}</td>
      <td class="px-2 py-1.5 text-ink-2">${b.best_slot ? fm(`${b.best_slot} (${num(b.best_score)})`) : "—"}</td>
      <td class="px-2 py-1.5 tabular-nums text-ink-2">${num(b.impact)}</td></tr>`).join("");
  html += `<div class="scroll-thin overflow-x-auto"><table class="w-full text-xs"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
  html += plan.uncovered.length
    ? `<p class="mt-2 text-xs text-warn">${trh("bench.uncovered", { slots: plan.uncovered.join(", ") })}</p>`
    : `<p class="mt-2 text-xs text-good">${esc(str("bench.all_covered"))}</p>`;
  html += sectionTitle(str("bench.subs_title"));
  html += plan.scenarios.length ? plan.scenarios.map((s) => `
    <div class="mt-2 rounded-xl border border-line p-3 text-xs">
      <p class="font-semibold text-accent-ink"><bdi dir="ltr">${esc(s.minute)}</bdi> ${esc(str("subs.kind." + s.kind))}</p>
      <p class="mt-0.5">${trh("subs.change", { on: fm(s.on), off: fm(s.off), slot: s.slot_id })}</p>
      <p class="text-ink-2">${esc(str("subs.roles"))}: ${fm(s.ip_role + " / " + s.oop_role)}</p>
      <p class="text-ink-3">${reasonHtml(s.reason_key, s.reason_args)}</p>
    </div>`).join("") : `<p class="text-xs text-ink-3">${esc(str("bench.no_subs"))}</p>`;
  box.innerHTML = html;
}

/* ---- squad table */
const SQUAD_COLS = [
  ["lock", "squad.col.lock"], ["name", "squad.col.name"], ["age", "squad.col.age"], ["pos", "squad.col.pos"],
  ["ca", "squad.col.ca"], ["pa", "squad.col.pa"], ["headroom", "squad.col.headroom"], ["prof", "squad.col.prof"],
  ["amb", "squad.col.amb"], ["imp", "squad.col.imp"], ["pres", "squad.col.pres"], ["cons", "squad.col.cons"],
  ["inj", "squad.col.inj"], ["wage", "squad.col.wage"], ["best_ip", "squad.col.best_ip"], ["ip", "squad.col.ip"],
  ["best_oop", "squad.col.best_oop"], ["oop", "squad.col.oop"], ["role_focus", "squad.col.role_focus"],
  ["add_focus", "squad.col.add_focus"], ["intensity", "squad.col.intensity"], ["status", "squad.col.status"],
];
const POS_ORDER = ["GK", "DL", "DC", "DR", "WBL", "WBR", "DM", "ML", "MC", "MR", "AML", "AMC", "AMR", "ST"];
const INTENSITY_ORDER = { "Double Intensity": 0, "Normal": 1, "Half Intensity": 2 };
const CAT_CLASS = { core: "text-cat-core", rotation: "text-cat-rotation", loan: "text-cat-loan", sell_high: "text-cat-sell", offload: "text-cat-offload" };

function squadRows() {
  const a = A();
  if (!a) return [];
  const training = new Map(a.training.map((r) => [r.player_id, r]));
  return a.squad.map((c) => ({ c, p: c.player, rec: training.get(c.player.id) }));
}

function sortValue(row, key) {
  const { c, p, rec } = row;
  switch (key) {
    case "lock": return p.locked ? 0 : 1;
    case "name": return (p.surname || p.name).toLowerCase();
    case "pos": { const i = POS_ORDER.indexOf(p.positions[0]); return i < 0 ? 99 : i; }
    case "best_ip": return c.best_ip_role;
    case "ip": return c.best_ip_score;
    case "best_oop": return c.best_oop_role;
    case "oop": return c.best_oop_score;
    case "role_focus": return rec ? rec.role_focus : "";
    case "add_focus": return rec ? trFocus(rec.additional_focus) : "";
    case "intensity": return rec ? INTENSITY_ORDER[rec.intensity] ?? 3 : 3;
    case "status": return c.category;
    default: return p[key] ?? 0;
  }
}

function renderSquad() {
  const table = $("#squad-table");
  const rows = squadRows();
  const { key, dir } = S.squadSort;
  rows.sort((x, y) => {
    const a = sortValue(x, key), b = sortValue(y, key);
    return (a < b ? -1 : a > b ? 1 : 0) * dir;
  });
  const terms = S.squadFilter.toLowerCase().split(/\s+/).filter(Boolean);
  const visible = rows.filter(({ c, p, rec }) => {
    if (!terms.length) return true;
    const hay = [p.name, p.positions.join("/"), c.best_ip_role, c.best_oop_role, trCategory(c.category), c.category,
                 rec ? rec.role_focus : "", rec ? trFocus(rec.additional_focus) : ""].join(" ").toLowerCase();
    return terms.every((t) => hay.includes(t));
  });
  $("#squad-count").textContent = terms.length
    ? tr("squad.count_filtered", { shown: visible.length, total: rows.length })
    : tr("squad.count", { total: rows.length });

  const wageTip = A() && !A().show_wage ? str("squad.wage_unmapped") : "";
  const head = SQUAD_COLS.map(([k, label]) => {
    const arrow = k === key ? (dir < 0 ? " ▾" : " ▴") : "";
    const title = k === "wage" ? wageTip : str("web.sort_hint");
    return `<th class="sticky top-0 z-10 bg-surface-2 px-2 py-2 text-start font-semibold whitespace-nowrap text-ink-2">
      <button class="hover:text-ink" data-sort="${k}" title="${esc(title)}">${esc(str(label))}${arrow}</button></th>`;
  }).join("");
  const center = "px-2 py-1.5 text-center tabular-nums";
  const body = visible.map(({ c, p, rec }) => `<tr class="border-t border-line hover:bg-surface-2/60">
      <td class="px-2 py-1.5 text-center"><input type="checkbox" class="size-4 accent-accent" data-lock="${p.id}" ${p.locked ? "checked" : ""} title="${esc(str("web.lock.tip"))}"></td>
      <td class="px-2 py-1.5 font-medium whitespace-nowrap">${fm(p.name)}</td>
      <td class="${center}">${p.age}</td>
      <td class="px-2 py-1.5 whitespace-nowrap">${fm(p.positions.join("/"))}</td>
      <td class="${center} font-semibold">${p.ca}</td><td class="${center}">${p.pa}</td><td class="${center}">${p.headroom}</td>
      <td class="${center} ${p.prof <= 9 ? "font-bold text-cat-sell" : ""}">${p.prof}</td>
      <td class="${center}">${p.amb}</td><td class="${center}">${p.imp}</td><td class="${center}">${p.pres}</td><td class="${center}">${p.cons}</td>
      <td class="${center} ${p.inj >= 14 ? "font-bold text-cat-offload" : ""}">${p.inj}</td>
      <td class="${center}">${p.wage == null ? "—" : p.wage.toLocaleString()}</td>
      <td class="px-2 py-1.5 whitespace-nowrap">${fm(c.best_ip_role)}</td><td class="${center}">${num(c.best_ip_score)}</td>
      <td class="px-2 py-1.5 whitespace-nowrap">${fm(c.best_oop_role)}</td><td class="${center}">${num(c.best_oop_score)}</td>
      <td class="px-2 py-1.5 whitespace-nowrap" title="${rec ? esc(trainingTitle(rec)) : ""}">${rec ? fm(rec.role_focus) : "—"}</td>
      <td class="px-2 py-1.5 whitespace-nowrap" title="${rec ? esc(trainingTitle(rec)) : ""}">${rec ? esc(trFocus(rec.additional_focus)) : "—"}</td>
      <td class="px-2 py-1.5 text-center font-semibold whitespace-nowrap ${rec ? intensityClass(rec.intensity) : ""}" title="${rec ? esc(trainingTitle(rec)) : ""}">${rec ? esc(trIntensity(rec.intensity)) : "—"}</td>
      <td class="px-2 py-1.5 font-semibold whitespace-nowrap ${CAT_CLASS[c.category_key] || ""}">${esc(trCategory(c.category))}</td>
    </tr>`).join("");
  table.innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body ||
    `<tr><td colspan="${SQUAD_COLS.length}" class="px-3 py-6 text-center text-ink-3">${esc(str("web.no_squad"))}</td></tr>`}</tbody>`;
}

function trainingTitle(rec) {
  const div = document.createElement("div");
  div.innerHTML = trainingReasonHtml(rec);
  return div.textContent;
}

/* ---- advisor */
const BUCKETS = [["KEEP", "text-cat-core"], ["LOAN", "text-cat-loan"], ["SELL_HIGH", "text-cat-sell"], ["OFFLOAD", "text-cat-offload"]];
const BUCKET_OF = { core: "KEEP", rotation: "KEEP", loan: "LOAN", sell_high: "SELL_HIGH" };

function renderAdvisor() {
  const a = A();
  if (!a) {
    $("#weakest").innerHTML = `<p class="text-ink-3">${esc(str("advisor.weakest.placeholder"))}</p>`;
    $("#buckets").innerHTML = BUCKETS.map(([k, cls]) => bucketCard(k, cls, `<p class="text-ink-3">${esc(str("advisor.bucket.empty"))}</p>`)).join("");
    $("#training").innerHTML = `<p class="text-ink-3">${esc(str("advisor.training.placeholder"))}</p>`;
    return;
  }
  const w = a.weakest;
  const depth = w.dropoff_delta > 0
    ? trh("advisor.weakest.depth", { slot: w.dropoff_slot, delta: num(w.dropoff_delta) })
    : esc(str("advisor.weakest.no_depth"));
  const attrs = Object.entries(w.minimum_attributes).map(([k, v]) => `${esc(attrName(k))} ≥ ${v}`).join(", ");
  $("#weakest").innerHTML = `
    <p class="font-semibold">${trh("advisor.weakest.summary", { slot: w.slot_id, name: fm(w.player_name), score: num(w.score), role: fm(w.target_role) })} ${depth}</p>
    <p class="mt-1.5 text-ink-2">${esc(str("advisor.weakest.filter"))} <b class="text-ink">${esc(w.target_position)} (${fm(w.target_role)})</b>:</p>
    <p class="mt-1 text-accent-ink">${attrs}</p>`;

  const groups = { KEEP: [], LOAN: [], SELL_HIGH: [], OFFLOAD: [] };
  for (const c of a.squad) {
    const p = c.player;
    const bucket = BUCKET_OF[c.category_key] || "OFFLOAD";
    const tag = bucket === "KEEP" ? ` <span class="${CAT_CLASS[c.category_key]}">· ${esc(trCategory(c.category))}</span>` : "";
    const wage = a.show_wage && p.wage != null ? `, $${p.wage.toLocaleString()}/wk` : "";
    const stats = fm(`CA ${p.ca} / PA ${p.pa}${wage}`);
    groups[bucket].push(`<div class="mb-2.5"><p><b>${fm(p.name)}</b>${tag}</p>
      <p class="text-xs text-ink-3">${trh("advisor.player_line", { age: p.age, stats })}</p>
      <p class="text-xs text-ink-2">${fm(c.reasons.join(" "))}</p></div>`);
  }
  $("#buckets").innerHTML = BUCKETS.map(([k, cls]) => bucketCard(k, cls,
    groups[k].join("") || `<p class="text-ink-3">${esc(str("advisor.none"))}</p>`)).join("");

  const head = ["training.col.player", "training.col.role_focus", "training.col.add_focus", "training.col.intensity", "training.col.reason"]
    .map((k) => `<th class="px-2 py-1.5 text-start font-semibold whitespace-nowrap text-ink-3">${esc(str(k))}</th>`).join("");
  const rows = a.training.map((r) => `<tr class="border-t border-line align-top">
      <td class="px-2 py-1.5 whitespace-nowrap"><b>${fm(r.name)}</b> <span class="text-ink-3">${esc(str("training.source." + r.role_source))}</span></td>
      <td class="px-2 py-1.5 whitespace-nowrap">${fm(r.role_focus)}</td>
      <td class="px-2 py-1.5 whitespace-nowrap">${esc(trFocus(r.additional_focus))}</td>
      <td class="px-2 py-1.5 font-semibold whitespace-nowrap ${intensityClass(r.intensity)}">${esc(trIntensity(r.intensity))}</td>
      <td class="px-2 py-1.5 text-ink-2">${trainingReasonHtml(r)}</td></tr>`).join("");
  $("#training").innerHTML = `<table class="w-full"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`;
}

function bucketCard(key, cls, inner) {
  return `<div class="card p-4"><h2 class="mb-2 text-sm font-semibold ${cls}">${esc(str("advisor.bucket." + key))}</h2>
    <div class="scroll-thin max-h-[420px] overflow-y-auto text-sm">${inner}</div></div>`;
}

/* ------------------------------------------------------------------ actions */
function applyState(state) {
  S.state = state;
  const slots = currentSlots();
  if (!slots.some((s) => s.slot_id === S.selectedSlot)) S.selectedSlot = null;
  renderControls();
  renderAll();
}

async function loadLive(interactive) {
  if (S.loading) return;
  S.loading = true;
  renderLoadButton();
  renderStatus();
  try {
    const state = await api("/api/load/live", {});
    S.loading = false;
    applyState(state);
    const n = state.notice;
    if (!n) return;
    if (n.kind === "success") { if (interactive) toast(str(n.title) + " · " + n.message, "success"); return; }
    if (!interactive && !n.always) return;
    const actions = [{ label: str("web.ok"), primary: n.action !== "calibrate" }];
    if (n.action === "calibrate") actions.unshift({ label: str("toolbar.calibrate"), primary: true, value: "calibrate" });
    const body = n.body ? `<p class="whitespace-pre-line">${trh(n.body, n.args || {})}</p>` : "";
    const choice = await modal({ title: str(n.title), body, actions });
    if (choice === "calibrate") openCalibration();
  } catch (err) {
    S.loading = false;
    renderLoadButton();
    renderStatus();
    if (err.key) apiErrorModal(err);
  }
}

async function postSettings(patch) {
  try { applyState(await api("/api/settings", patch)); } catch (err) { if (err.key) apiErrorModal(err); }
}

async function importFile(file) {
  const data = await new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(String(fr.result).split(",", 2)[1] || "");
    fr.onerror = reject;
    fr.readAsDataURL(file);
  });
  try {
    applyState(await api("/api/import", { filename: file.name, data }));
    toast(tr("status.imported", S.state.status.args), "info");
  } catch (err) {
    if (err.key === "dialog.import_incomplete.body") {
      modal({ title: str("dialog.import_incomplete.title"), body: `<p>${trh(err.key, err.args)}</p>`, actions: [{ label: str("web.ok"), primary: true }] });
    } else if (err.key) apiErrorModal(err);
  }
}

function calibrationFields(prefix, defaults) {
  const field = (key, label, min, max, value) => `
    <label class="flex items-center justify-between gap-3 py-0.5"><span class="text-ink-2">${esc(label)}</span>
      <input name="${prefix}.${key}" type="number" min="${min}" max="${max}" value="${value}" required class="field w-24 text-end tabular-nums"></label>`;
  return `
    <label class="flex items-center justify-between gap-3 py-0.5"><span class="text-ink-2">${esc(str("web.calib.name"))}</span>
      <input name="${prefix}.name" value="${esc(defaults.name)}" class="field w-44"></label>
    ${field("age", str("web.calib.age"), 15, 45, defaults.age)}
    ${field("ca", str("web.calib.ca"), 1, 200, defaults.ca)}
    ${field("pa", str("web.calib.pa"), 1, 200, defaults.pa)}
    ${["pace", "finishing", "passing", "tackling", "decisions"].map((a) => field(a, `${attrName(a)} (1–20)`, 1, 20, defaults[a])).join("")}`;
}

function openCalibration() {
  const d1 = { name: "Starter #1", age: 22, ca: 145, pa: 165, pace: 15, finishing: 12, passing: 14, tackling: 13, decisions: 14 };
  const d2 = { name: "Starter #2", age: 24, ca: 140, pa: 150, pace: 13, finishing: 10, passing: 15, tackling: 14, decisions: 13 };
  const body = `<p class="mb-3 text-ink-2">${esc(str("web.calib.intro"))}</p>
    <div id="calib-form" class="grid gap-4 sm:grid-cols-2">
      <fieldset class="rounded-xl border border-line p-3"><legend class="px-1 text-xs font-semibold">${esc(str("web.calib.player1"))}</legend>${calibrationFields("p1", d1)}</fieldset>
      <fieldset class="rounded-xl border border-line p-3"><legend class="px-1 text-xs font-semibold">${esc(str("web.calib.player2"))}</legend>
        <label class="mb-1 flex items-center gap-2 text-xs"><input id="calib-use-p2" type="checkbox" class="size-4 accent-accent">${esc(str("web.calib.use_p2"))}</label>
        ${calibrationFields("p2", d2)}</fieldset>
    </div>
    <p id="calib-result" class="mt-3 hidden whitespace-pre-line text-sm"></p>`;
  const collect = (prefix) => {
    const out = {};
    for (const el of $$(`#calib-form [name^="${prefix}."]`)) out[el.name.split(".")[1]] = el.name.endsWith(".name") ? el.value : Number(el.value);
    return out;
  };
  modal({
    title: str("toolbar.calibrate_tip"),
    body,
    actions: [
      { label: str("web.close") },
      {
        label: str("web.calib.run"), primary: true, submit: true,
        onClick: async (btn) => {
          btn.disabled = true;
          btn.textContent = str("web.loading");
          const result = $("#calib-result");
          try {
            const payload = { p1: collect("p1") };
            if ($("#calib-use-p2").checked) payload.p2 = collect("p2");
            const state = await api("/api/calibrate", payload);
            applyState(state);
            const ok = state.calibration.success;
            result.className = "mt-3 whitespace-pre-line text-sm " + (ok ? "text-good" : "text-bad");
            result.textContent = `${str(ok ? "web.calib.ok.title" : "web.calib.fail.title")}: ${state.calibration.message}`;
          } catch (err) {
            result.className = "mt-3 text-sm text-bad";
            result.textContent = str("web.calib.fail.title");
          }
          btn.disabled = false;
          btn.textContent = str("web.calib.run");
          return true; // keep the dialog open to show the result
        },
      },
    ],
  });
}

async function copyPlan() {
  const a = A();
  if (!a) return;
  const btn = $("#btn-copy");
  try {
    await navigator.clipboard.writeText(a.plan_text);
  } catch (e) {
    const ta = document.createElement("textarea");
    ta.value = a.plan_text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  btn.textContent = str("tactics.copied");
  setTimeout(() => { btn.textContent = str("tactics.copy_plan"); }, 1500);
}

async function reportBug() {
  try {
    const { url } = await api("/api/bug-url");
    window.open(url, "_blank", "noopener");
  } catch (err) { if (err.key) apiErrorModal(err); }
}

async function quit() {
  const choice = await modal({
    title: str("web.quit"),
    body: `<p>${esc(str("web.quit_confirm"))}</p>`,
    actions: [{ label: str("web.cancel") }, { label: str("web.quit"), primary: true, value: "quit" }],
  });
  if (choice !== "quit") return;
  try { await api("/api/quit", {}); } catch (e) { /* server already gone */ }
  showOffline(true);
}

/* ------------------------------------------------------------------ wiring */
function wire() {
  $("#btn-load").addEventListener("click", () => loadLive(true));
  $("#btn-calibrate").addEventListener("click", openCalibration);
  $("#btn-import").addEventListener("click", () => $("#import-file").click());
  $("#import-file").addEventListener("change", (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = "";
    if (file) importFile(file);
  });
  $("#sel-style").addEventListener("change", (e) => postSettings({ style: e.target.value }));
  $("#sel-formation").addEventListener("change", (e) => postSettings({ formation: e.target.value }));
  $("#chk-important").addEventListener("change", (e) => postSettings({ important: e.target.checked }));
  $("#btn-theme").addEventListener("click", () => setTheme(S.theme === "dark" ? "light" : "dark"));
  $("#btn-lang").addEventListener("click", () => setLanguage(S.lang === "he" ? "en" : "he"));
  $("#btn-bug").addEventListener("click", reportBug);
  $("#btn-quit").addEventListener("click", quit);
  $("#btn-copy").addEventListener("click", copyPlan);
  for (const b of $$("[data-tab]")) b.addEventListener("click", () => setTab(b.dataset.tab));
  for (const b of $$("[data-mode]")) b.addEventListener("click", () => setMode(b.dataset.mode));

  const pickSlot = (target) => {
    const node = target.closest && target.closest("[data-slot]");
    if (!node) return;
    S.selectedSlot = node.dataset.slot;
    renderTactics();
  };
  $("#pitches").addEventListener("click", (e) => pickSlot(e.target));
  $("#pitches").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pickSlot(e.target); } });
  $("#bench").addEventListener("change", (e) => { if (e.target.id === "sel-bench") postSettings({ bench_size: Number(e.target.value) }); });

  $("#squad-search").addEventListener("input", (e) => { S.squadFilter = e.target.value; renderSquad(); });
  $("#squad-table").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-sort]");
    if (!btn) return;
    const key = btn.dataset.sort;
    S.squadSort = { key, dir: S.squadSort.key === key ? -S.squadSort.dir : (["name", "pos", "best_ip", "best_oop", "role_focus", "add_focus", "status", "intensity", "lock"].includes(key) ? 1 : -1) };
    renderSquad();
  });
  $("#squad-table").addEventListener("change", async (e) => {
    const id = e.target.dataset && e.target.dataset.lock;
    if (!id) return;
    try { applyState(await api("/api/lock", { player_id: Number(id), locked: e.target.checked })); }
    catch (err) { if (err.key) apiErrorModal(err); }
  });

  // Heartbeat: the server stops itself once no Tacticfy page has checked in for a few minutes.
  setInterval(() => { if (!S.offline) api("/api/heartbeat", {}).catch(() => {}); }, 20000);
}

async function boot() {
  // Optional deep-link parameters (?lang=he&theme=dark&tab=squad&mode=BENCH) override saved preferences.
  const q = new URLSearchParams(location.search);
  if (["light", "dark"].includes(q.get("theme"))) setTheme(q.get("theme"));
  S.theme = document.documentElement.classList.contains("dark") ? "dark" : "light";
  wire();
  const lang = q.get("lang") || load("lang");
  const tab = q.get("tab") || load("tab");
  const mode = (q.get("mode") || "").toUpperCase();
  try {
    S.meta = await api("/api/meta");
    S.state = await api("/api/state");
    await setLanguage(lang === "he" ? "he" : "en");
  } catch (e) {
    return; // offline overlay is already showing
  }
  setTab(["tactics", "squad", "advisor"].includes(tab) ? tab : "tactics");
  setMode(["BEST", "SECOND", "DROPOFF", "BENCH"].includes(mode) ? mode : "BEST");
  if (!S.state.player_count) loadLive(false);
}

document.addEventListener("DOMContentLoaded", boot);
