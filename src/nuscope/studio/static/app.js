// NUScope Studio — browser UI (no build step, no framework).
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = j.detail || msg; } catch (e) { /* not JSON */ }
    throw new Error(msg);
  }
  return r;
}
const post = (path, body) => api(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json());
function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v; else if (k === "on") e.addEventListener("click", v);
    else if (k.startsWith("on:")) e.addEventListener(k.slice(3), v); else if (v != null && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) e.append(k);
  return e;
}
const fmtBytes = (n) => (n == null ? "" : n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} kB` : n < 1073741824 ? `${(n / 1048576).toFixed(1)} MB` : `${(n / 1073741824).toFixed(2)} GB`);
const fmtNum = (v, d = 3) => (v == null || !isFinite(v) ? "–" : Math.abs(v) >= 1e4 || (Math.abs(v) < 1e-3 && v !== 0) ? (+v).toExponential(2) : Number.isInteger(v) ? v.toLocaleString() : (+v).toPrecision(d + 1).replace(/\.?0+$/, ""));
const LEN = { pm: 1e-3, nm: 1, "Å": 0.1, A: 0.1, um: 1e3, "µm": 1e3, "μm": 1e3, mm: 1e6, m: 1e9 };

function toast(title, body = "", kind = "") {
  const t = el("div", { class: `toast ${kind}` }, el("b", {}, title), body);
  $("#toasts").append(t);
  setTimeout(() => t.remove(), kind === "err" ? 9000 : 4500);
}
function download(url) { const a = el("a", { href: url, download: "" }); document.body.append(a); a.click(); a.remove(); }

// ================================================================== state
const S = {
  root: null, path: "", items: new Map(), cur: null, frame: 0,
  lo: null, hi: null, gamma: 1, log: false, cmap: "gray", hist: null,
  zoom: 1, pan: [0, 0], fitScale: 1, tool: "pan", line: null, pick: null,
  gray: null, colored: null, overlay: null, overlayTid: null, showScale: true, showCbar: false,
};

// ================================================================== colour maps
const CMAPS = {
  gray: [[0, 0, 0], [255, 255, 255]],
  purple: [[0, 0, 0], [78, 42, 132], [182, 172, 209], [255, 255, 255]],
  inferno: [[0, 0, 4], [87, 16, 110], [188, 55, 84], [249, 142, 9], [252, 255, 164]],
  magma: [[0, 0, 4], [81, 18, 124], [183, 55, 121], [252, 137, 97], [252, 253, 191]],
  viridis: [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]],
  cividis: [[0, 34, 78], [65, 77, 107], [124, 123, 120], [188, 175, 111], [253, 234, 69]],
  fire: [[0, 0, 0], [140, 0, 0], [255, 80, 0], [255, 200, 40], [255, 255, 255]],
};
function lut(name) {
  const stops = CMAPS[name] || CMAPS.gray, t = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i++) {
    const f = (i / 255) * (stops.length - 1), k = Math.min(stops.length - 2, Math.floor(f)), u = f - k;
    for (let c = 0; c < 3; c++) t[i * 3 + c] = stops[k][c] + (stops[k + 1][c] - stops[k][c]) * u;
  }
  return t;
}
const cssColor = (name, v) => { const t = lut(name), i = Math.round(v * 255) * 3; return `rgb(${t[i]},${t[i + 1]},${t[i + 2]})`; };

// ================================================================== library
async function loadLibrary(path = S.path, q = "") {
  S.path = path;
  const d = await (await api(`/api/library?path=${encodeURIComponent(path)}&q=${encodeURIComponent(q)}`)).json();
  const crumbs = $("#lib-path"); crumbs.replaceChildren();
  const parts = d.path ? d.path.split("/") : [];
  crumbs.append(el("button", { on: () => loadLibrary("") }, S.rootName || "folder"));
  parts.forEach((p, i) => crumbs.append(el("span", {}, "/"), el("button", { on: () => loadLibrary(parts.slice(0, i + 1).join("/")) }, p)));
  const list = $("#lib-list"); list.replaceChildren();
  if (!d.entries.length) list.append(el("li", { class: "muted" }, el("span"), el("span", { class: "nm" }, q ? "No matching files" : "No microscope files here")));
  for (const e of d.entries) list.append(fileRow(e, q));
  if (!S.cur && !q) {
    let files = d.entries.filter((e) => !e.dir);
    if (!files.length) files = (await (await api(`/api/library?path=${encodeURIComponent(path)}&q=.`)).json()).entries;
    renderRecent(files.sort((a, b) => b.mtime - a.mtime));
  }
}
function iconFor(e) {
  if (e.dir) return ["dir", "DIR"];
  const x = e.ext;
  if (["nxs", "h5", "hdf5", "zarr"].includes(x)) return ["nx", x.toUpperCase().slice(0, 3)];
  if (["tif", "tiff", "png", "jpg", "jpeg"].includes(x)) return ["tif", "TIF"];
  if (["dm3", "dm4"].includes(x)) return ["img", "DM"];
  if (["bcf", "spx", "spd", "spc", "msa", "emsa"].includes(x)) return ["spec", "EDS"];
  if (["emd", "ser", "emi", "mrc", "mib"].includes(x)) return ["d4", x.toUpperCase().slice(0, 3)];
  return ["other", x.toUpperCase().slice(0, 3)];
}
function fileRow(e, q, onOpen = null) {
  const [cls, label] = iconFor(e);
  const sub = q ? e.path.split("/").slice(0, -1).join("/") : e.sidecar ? "with metadata file" : "";
  const li = el("li", { tabindex: "0", title: e.path },
    el("span", { class: `ic ${cls}` }, label),
    el("span", { class: "nm" }, e.name, sub ? el("small", {}, sub) : null),
    el("span", { class: "sz" }, e.dir ? "" : fmtBytes(e.size)));
  const go = onOpen ? () => onOpen(e, li) : () => (e.dir ? loadLibrary(e.path) : openPath(e.path, li));
  li.addEventListener("click", go);
  li.addEventListener("keydown", (ev) => { if (ev.key === "Enter") go(); });
  return li;
}
function renderRecent(files) {
  const r = $("#recent"); r.replaceChildren();
  if (!files.length) { r.append(el("li", { class: "muted" }, "Open a folder on the left to see its files.")); return; }
  for (const f of files.slice(0, 8)) r.append(el("li", { on: () => openPath(f.path), title: f.path }, f.name,
    el("small", {}, [f.path.split("/").slice(0, -1).join("/"), fmtBytes(f.size)].filter(Boolean).join(" · "))));
}
let searchT;
$("#lib-search").addEventListener("input", (e) => { clearTimeout(searchT); searchT = setTimeout(() => loadLibrary(S.path, e.target.value.trim()), 200); });
$$("#lib-tabs button").forEach((b) => b.addEventListener("click", () => {
  $$("#lib-tabs button").forEach((x) => x.classList.toggle("on", x === b));
  for (const t of ["folder", "globus", "open"]) $(`#lib-${t}`).hidden = t !== b.dataset.tab;
}));

// ------------------------------------------------------------------ opening
async function openPath(path, li) {
  li?.classList.add("busy");
  try {
    const out = await post("/api/open", { path });
    for (const s of out) S.items.set(s.id, s);
    renderOpen();
    await show(out[0].id);
    if (out.length > 1) toast(`${out.length} datasets in this file`, " All are listed under Open.");
    const bad = out.find((s) => s.integrity?.status === "tampered");
    if (bad) toast("This file changed after it was sealed", ` ${bad.integrity.problems.join("; ")}. See History.`, "err");
  } catch (e) { toast("Could not open the file", ` ${e.message}`, "err"); }
  li?.classList.remove("busy");
}
async function openUrl(url) {
  try {
    toast("Fetching from Globus", " The file is copied to the local cache, then opened.");
    const out = await post("/api/open", { url });
    for (const s of out) S.items.set(s.id, s);
    renderOpen(); await show(out[0].id);
  } catch (e) { toast("Could not open from Globus", ` ${e.message}`, "err"); }
}
async function uploadFiles(files) {
  if (!files.length) return;
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  try {
    const r = await (await api("/api/upload", { method: "POST", body: fd })).json();
    toast(`Added ${r.saved.length} file(s)`, " to the uploads folder.", "ok");
    await loadLibrary("uploads");
    const main = r.saved.find((p) => !/\.txt$/i.test(p));
    if (main) openPath(main);
  } catch (e) { toast("Upload failed", ` ${e.message}`, "err"); }
}
$("#file-input").addEventListener("change", (e) => uploadFiles([...e.target.files]));
for (const ev of ["dragenter", "dragover"]) document.addEventListener(ev, (e) => { e.preventDefault(); document.body.classList.add("dragging"); });
for (const ev of ["dragleave", "drop"]) document.addEventListener(ev, (e) => { e.preventDefault(); if (ev === "drop" || !e.relatedTarget) document.body.classList.remove("dragging"); });
document.addEventListener("drop", (e) => uploadFiles([...e.dataTransfer.files]));

function renderOpen() {
  const list = $("#open-list"); list.replaceChildren();
  $("#open-count").textContent = S.items.size ? `(${S.items.size})` : "";
  const roots = [...S.items.values()].filter((s) => !s.parent || !S.items.has(s.parent));
  const addRow = (s, depth) => {
    const [cls, label] = s.view.kind === "spectrum_image" || s.view.kind === "spectrum" ? ["spec", "SPC"] : s.view.kind === "4d" ? ["d4", "4D"] : ["img", s.op ? "RES" : "IMG"];
    const li = el("li", { class: `${depth ? "child" : ""} ${S.cur === s.id ? "on" : ""}`, tabindex: "0" },
      el("span", { class: `ic ${cls}` }, label), el("span", { class: "nm" }, s.name, el("small", {}, s.shape.join(" × "))),
      el("button", { class: "x", title: "Close", "aria-label": "Close", on: async (ev) => { ev.stopPropagation(); await api(`/api/ds/${s.id}`, { method: "DELETE" });
        for (const [k, v] of S.items) if (k === s.id || v.parent === s.id) S.items.delete(k);
        if (!S.items.has(S.cur)) { S.cur = null; showWelcome(); } renderOpen(); } }, "×"));
    li.addEventListener("click", () => show(s.id));
    list.append(li);
    for (const c of S.items.values()) if (c.parent === s.id) addRow(c, depth + 1);
  };
  roots.forEach((r) => addRow(r, 0));
  if (!S.items.size) list.append(el("li", {}, el("span"), el("span", { class: "nm" }, "Nothing open yet")));
}
function showWelcome() {
  $("#welcome").hidden = false; $("#stage").hidden = true; $("#crumb").replaceChildren();
  for (const b of ["#save-btn", "#export-btn"]) $(b).disabled = true;
  $("#ins-info").replaceChildren(el("div", { class: "empty-note" }, "Open a file to see its calibration and metadata."));
}

// ================================================================== show a dataset
async function show(id) {
  const s = await (await api(`/api/ds/${id}`)).json();
  S.items.set(id, { ...S.items.get(id), ...s });
  stashResults(id);
  S.cur = id; S.frame = 0; S.line = null; S.pick = null; S.overlay = null; S.overlayTid = null;
  S.lo = S.hi = null; S.gamma = 1; $("#gamma").value = 1; $("#gamma-out").textContent = "1.00";
  S.log = s.signal === "diffraction"; $("#log").checked = S.log;
  $("#welcome").hidden = true; $("#stage").hidden = false;
  for (const b of ["#save-btn", "#export-btn"]) $(b).disabled = false;
  $("#crumb").replaceChildren(s.name, el("small", {}, `${s.shape.join(" × ")} · ${s.dtype}`));
  $("#st-ds").textContent = calibText(s);
  $("#overlay-toggle").hidden = true; $("#pickpane").hidden = true;
  const v = s.view;
  $("#pick-tool").hidden = !["spectrum_image", "4d"].includes(v.kind);
  if (S.tool === "pick" && $("#pick-tool").hidden) setTool("pan");
  $("#frame-box").hidden = v.kind !== "stack";
  if (v.kind === "stack") { $("#frame").max = v.frames - 1; $("#frame").value = 0; $("#frame-label").textContent = `1 / ${v.frames}`; }
  $("#view-hint").textContent = { spectrum_image: "Spectrum image: total intensity shown. Use the pick tool to see the spectrum at a pixel.",
    "4d": "4D data: total intensity per scan position. Use the pick tool to see the pattern there.",
    stack: "Image stack: move the frame slider." }[v.kind] || "";
  renderOpen(); renderInfo(s); renderTools(s); renderHistory(s);
  if (v.kind === "spectrum") { await showSpectrum(s); return; }
  await new Promise((r) => { requestAnimationFrame(r); setTimeout(r, 60); });   // let the stage lay out first
  await refreshHistogram(); await loadImage(true);
}
function calibText(s) {
  const ia = s.view.image_axes;
  if (!ia) return s.name;
  const ax = s.axes[ia[1]];
  if (ax.units === "px") return "Uncalibrated (pixels)";
  if (/^1\/nm$/.test(ax.units) && ax.scale < 0.01) return `${fmtNum(ax.scale * 1e3)} 1/µm per pixel`;
  return `${fmtNum(ax.scale)} ${ax.units} per pixel`;
}
async function showSpectrum(s) {
  const d = await (await api(`/api/ds/${s.id}/spectrum`)).json();
  $("#pickpane").hidden = false; $("#pick-title").textContent = `${s.name}: spectrum`;
  Charts.lines($("#pick-body"), { height: 220, xLabel: `${d.name} (${d.units})`, endLabels: false, series: [{ name: "counts", color: Charts.css("accent"), pts: d.x.map((x, i) => ({ x, y: d.y[i] })) }] });
}

// ------------------------------------------------------------------ image loading + drawing
const cv = $("#cv"), ctx = cv.getContext("2d");
let imgT;
async function loadImage(fit = false) {
  const s = S.items.get(S.cur); if (!s) return;
  const q = new URLSearchParams({ frame: S.frame, gamma: S.gamma, log: S.log });
  if (S.lo != null) { q.set("lo", S.lo); q.set("hi", S.hi); }
  const blob = await (await api(`/api/ds/${S.cur}/image?${q}`)).blob();
  const bmp = await createImageBitmap(blob, { colorSpaceConversion: "none", premultiplyAlpha: "none" });
  const off = document.createElement("canvas"); off.width = bmp.width; off.height = bmp.height;
  const c = off.getContext("2d", { willReadFrequently: true }); c.drawImage(bmp, 0, 0);
  S.gray = c.getImageData(0, 0, bmp.width, bmp.height);
  colorize();
  if (fit) fitView();
  draw();
}
function colorize() {
  if (!S.gray) return;
  const t = lut(S.cmap), src = S.gray.data, out = new ImageData(S.gray.width, S.gray.height), d = out.data;
  for (let i = 0; i < src.length; i += 4) { const k = src[i] * 3; d[i] = t[k]; d[i + 1] = t[k + 1]; d[i + 2] = t[k + 2]; d[i + 3] = 255; }
  const off = document.createElement("canvas"); off.width = out.width; off.height = out.height;
  off.getContext("2d").putImageData(out, 0, 0); S.colored = off;
}
function scheduleImage() { clearTimeout(imgT); imgT = setTimeout(() => loadImage(false), 90); }
function physAxes() { const s = S.items.get(S.cur); const ia = s.view.image_axes || [0, 1]; return [s.axes[ia[0]], s.axes[ia[1]]]; }
function fitView() {
  if (!S.gray) return;
  const W = cv.clientWidth, H = cv.clientHeight;
  S.fitScale = Math.min(W / S.gray.width, H / S.gray.height) * 0.94; S.zoom = 1; S.pan = [0, 0];
}
const scale = () => S.fitScale * S.zoom;
function toScreen(px, py) { const W = cv.clientWidth, H = cv.clientHeight, s = scale();
  return [W / 2 + S.pan[0] + (px - S.gray.width / 2) * s, H / 2 + S.pan[1] + (py - S.gray.height / 2) * s]; }
function toImage(x, y) { const W = cv.clientWidth, H = cv.clientHeight, s = scale();
  return [(x - W / 2 - S.pan[0]) / s + S.gray.width / 2, (y - H / 2 - S.pan[1]) / s + S.gray.height / 2]; }
function draw() {
  const dpr = devicePixelRatio, W = cv.clientWidth, H = cv.clientHeight;
  if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--viewport") || "#050609"; ctx.fillRect(0, 0, W, H);
  if (!S.colored) return;
  const [x0, y0] = toScreen(0, 0), [x1, y1] = toScreen(S.gray.width, S.gray.height);
  ctx.imageSmoothingEnabled = scale() < 2;
  ctx.drawImage(S.colored, x0, y0, x1 - x0, y1 - y0);
  if (S.overlay && $("#show-overlay").checked) { ctx.imageSmoothingEnabled = false; ctx.drawImage(S.overlay, x0, y0, x1 - x0, y1 - y0); }
  if (S.line) {
    const [a, b] = [toScreen(S.line[0][1], S.line[0][0]), toScreen(S.line[1][1], S.line[1][0])];
    ctx.strokeStyle = "#ffcf33"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(...b); ctx.stroke();
    for (const p of [a, b]) { ctx.beginPath(); ctx.arc(p[0], p[1], 4, 0, 7); ctx.fillStyle = "#ffcf33"; ctx.fill(); }
  }
  if (S.pick) { const [px, py] = toScreen(S.pick[1] + 0.5, S.pick[0] + 0.5);
    ctx.strokeStyle = "#ffcf33"; ctx.lineWidth = 2; ctx.strokeRect(px - 7, py - 7, 14, 14); }
  if (S.showScale) drawScaleBar(W, H);
  if (S.showCbar) drawColorbar(W, H);
}
function drawScaleBar(W, H) {
  const ax = physAxes()[1];
  let per = ax.scale, unit = ax.units; // physical units per image pixel
  if (unit === "px") return;
  if (LEN[unit]) { per = ax.scale * LEN[unit]; unit = "nm"; }
  else if (/^1\/(nm|Å|A)$/.test(unit) && per < 0.01) { per *= 1e3; unit = "1/µm"; }   // FFTs of SEM images
  const s = scale(), target = 140 / s * per;
  if (!(target > 0)) return;
  const e = Math.floor(Math.log10(target)), nice = [5, 2, 1].map((m) => m * 10 ** e).find((v) => v <= target);
  const L = (nice / per) * s, X = W - 24 - L, Y = H - 22;
  let label = `${fmtNum(nice)} ${unit}`;
  if (unit === "nm" && nice >= 1e6) label = `${fmtNum(nice / 1e6)} mm`;
  else if (unit === "nm" && nice >= 1000) label = `${fmtNum(nice / 1000)} µm`;
  ctx.font = "600 12px -apple-system, Segoe UI, sans-serif"; ctx.textAlign = "center";
  const tw = Math.max(L, ctx.measureText(label).width) + 16;
  ctx.fillStyle = "rgba(0,0,0,.45)"; ctx.fillRect(X + L / 2 - tw / 2, Y - 22, tw, 32);
  ctx.fillStyle = "#fff"; ctx.fillRect(X, Y, L, 4); ctx.fillText(label, X + L / 2, Y - 7);
}
function drawColorbar(W, H) {
  const h = Math.min(220, H - 80), x = W - 34, y = 36;
  for (let i = 0; i < h; i++) { ctx.fillStyle = cssColor(S.cmap, 1 - i / h); ctx.fillRect(x, y + i, 14, 1); }
  ctx.strokeStyle = "rgba(255,255,255,.6)"; ctx.strokeRect(x, y, 14, h);
  ctx.fillStyle = "#fff"; ctx.font = "11px -apple-system, Segoe UI, sans-serif"; ctx.textAlign = "right";
  ctx.fillText(fmtNum(S.hi), x - 5, y + 9); ctx.fillText(fmtNum(S.lo), x - 5, y + h);
}

// ------------------------------------------------------------------ interaction
let drag = null, readT;
cv.addEventListener("pointerdown", (e) => {
  if (!S.gray) return;
  cv.setPointerCapture(e.pointerId);
  const r = cv.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
  if (S.tool === "line" && e.button === 0) { const [ix, iy] = toImage(x, y); S.line = [[iy, ix], [iy, ix]]; drag = { line: true }; return; }
  if (S.tool === "pick" && e.button === 0) { const [ix, iy] = toImage(x, y); doPick(Math.floor(iy), Math.floor(ix)); return; }
  drag = { pan: [x, y] }; cv.style.cursor = "grabbing";
});
cv.addEventListener("pointermove", (e) => {
  if (!S.gray) return;
  const r = cv.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
  if (drag?.pan) { S.pan[0] += x - drag.pan[0]; S.pan[1] += y - drag.pan[1]; drag.pan = [x, y]; draw(); return; }
  if (drag?.line) { const [ix, iy] = toImage(x, y); S.line[1] = [iy, ix]; draw(); return; }
  const [ix, iy] = toImage(x, y);
  if (ix < 0 || iy < 0 || ix >= S.gray.width || iy >= S.gray.height) { $("#st-cursor").textContent = "Outside the image"; return; }
  clearTimeout(readT);
  readT = setTimeout(async () => {
    try {
      const v = await (await api(`/api/ds/${S.cur}/value?y=${Math.floor(iy)}&x=${Math.floor(ix)}&frame=${S.frame}`)).json();
      const [ay, ax] = physAxes();
      const p = (a, i) => (a.units === "px" ? "" : ` (${fmtNum(a.offset + a.scale * i)} ${a.units})`);
      const sc = $("#st-cursor"); sc.replaceChildren(el("b", {}, `x ${v.x} · y ${v.y}`), `${p(ax, v.x)}${p(ay, v.y)}   value `, el("b", {}, fmtNum(v.value)));
    } catch (err) { /* dataset closed */ }
  }, 50);
});
cv.addEventListener("pointerup", () => {
  cv.style.cursor = "";
  if (drag?.line) {
    const [[y0, x0], [y1, x1]] = S.line;
    if (Math.hypot(y1 - y0, x1 - x0) > 2) runTool("line_profile", { start: [y0, x0], end: [y1, x1], width: +($("#lp-width")?.value || 3) });
  }
  drag = null;
});
cv.addEventListener("wheel", (e) => {
  e.preventDefault(); if (!S.gray) return;
  const r = cv.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
  const before = toImage(x, y), f = Math.exp(-e.deltaY * 0.0015);
  S.zoom = Math.max(0.2, Math.min(60, S.zoom * f));
  const after = toScreen(...before); S.pan[0] += x - after[0]; S.pan[1] += y - after[1]; draw();
}, { passive: false });
cv.addEventListener("dblclick", () => { fitView(); draw(); });
new ResizeObserver(() => { if (S.gray) { fitView(); draw(); } }).observe($("#canvas-wrap"));
function setTool(t) { S.tool = t; $$("#tools button").forEach((b) => b.classList.toggle("on", b.dataset.tool === t)); cv.className = t; }
$$("#tools button").forEach((b) => b.addEventListener("click", () => setTool(b.dataset.tool)));
$("#zoom-fit").onclick = () => { fitView(); draw(); };
$("#zoom-1").onclick = () => { S.zoom = 1 / S.fitScale / devicePixelRatio * devicePixelRatio; S.zoom = 1 / S.fitScale; draw(); };
$("#zoom-in").onclick = () => { S.zoom = Math.min(60, S.zoom * 1.4); draw(); };
$("#zoom-out").onclick = () => { S.zoom = Math.max(0.2, S.zoom / 1.4); draw(); };
$("#cmap").onchange = (e) => { S.cmap = e.target.value; colorize(); draw(); drawHist(); };
$("#show-scale").onchange = (e) => { S.showScale = e.target.checked; draw(); };
$("#show-cbar").onchange = (e) => { S.showCbar = e.target.checked; draw(); };
$("#show-overlay").onchange = draw;
$("#frame").oninput = (e) => { S.frame = +e.target.value; $("#frame-label").textContent = `${S.frame + 1} / ${+e.target.max + 1}`; refreshHistogram().then(() => loadImage()); };
document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, select, textarea") || !S.gray) return;
  if (e.key === "f" || e.key === "F") { fitView(); draw(); }
  else if (e.key === "+" || e.key === "=") $("#zoom-in").click();
  else if (e.key === "-") $("#zoom-out").click();
  else if (e.key === "l" || e.key === "L") setTool("line");
  else if ((e.key === "p" || e.key === "P") && !$("#pick-tool").hidden) setTool("pick");
  else if (e.key === "Escape") { setTool("pan"); S.line = null; draw(); }
});

// ------------------------------------------------------------------ pick (spectrum image / 4D)
async function doPick(y, x) {
  const s = S.items.get(S.cur);
  if (y < 0 || x < 0 || y >= S.gray.height || x >= S.gray.width) return;
  S.pick = [y, x]; draw();
  try {
    const d = await (await api(`/api/ds/${S.cur}/pick?y=${y}&x=${x}`)).json();
    $("#pickpane").hidden = false;
    $("#pick-title").textContent = `${d.kind === "spectrum" ? "Spectrum" : "Pattern"} at x ${x}, y ${y}`;
    if (d.kind === "spectrum") {
      Charts.lines($("#pick-body"), { height: 210, xLabel: `${d.name} (${d.units})`, endLabels: false, yMin: 0,
        series: [{ name: "counts", color: Charts.css("accent"), pts: d.x.map((v, i) => ({ x: v, y: d.y[i] })) }] });
    } else {
      $("#pick-body").replaceChildren(el("img", { src: `/api/ds/${s.id}/pick.png?t=${Date.now()}`, alt: `Diffraction pattern at ${x}, ${y}` }),
        el("p", { class: "hint" }, `${d.shape.join(" × ")} pixels, ${fmtNum(d.scale)} ${d.units} per pixel, log scale`));
    }
  } catch (e) { toast("Pick failed", ` ${e.message}`, "err"); }
}
$("#pick-close").onclick = () => { $("#pickpane").hidden = true; S.pick = null; draw(); };

// ------------------------------------------------------------------ histogram + contrast
const hc = $("#hist"), hctx = hc.getContext("2d");
async function refreshHistogram() {
  S.hist = await (await api(`/api/ds/${S.cur}/histogram?frame=${S.frame}`)).json();
  if (S.lo == null) [S.lo, S.hi] = S.hist.auto;
  $("#lo").value = +S.lo.toPrecision(5); $("#hi").value = +S.hi.toPrecision(5);
  drawHist();
}
function drawHist() {
  if (!S.hist) return;
  const dpr = devicePixelRatio, W = hc.clientWidth, H = hc.clientHeight;
  hc.width = W * dpr; hc.height = H * dpr; hctx.setTransform(dpr, 0, 0, dpr, 0, 0); hctx.clearRect(0, 0, W, H);
  const { counts, min, max } = S.hist, m = Math.max(...counts.map((c) => Math.log1p(c))) || 1;
  const X = (v) => ((v - min) / ((max - min) || 1)) * W;
  counts.forEach((c, i) => {
    const h = (Math.log1p(c) / m) * (H - 6), x = (i / counts.length) * W;
    const v = min + (i / counts.length) * (max - min), u = Math.min(1, Math.max(0, (v - S.lo) / ((S.hi - S.lo) || 1)));
    hctx.fillStyle = cssColor(S.cmap === "gray" ? "purple" : S.cmap, 0.25 + 0.75 * u); hctx.fillRect(x, H - h, W / counts.length + 0.5, h);
  });
  for (const [v, lab] of [[S.lo, "min"], [S.hi, "max"]]) {
    const x = Math.max(1, Math.min(W - 1, X(v)));
    hctx.strokeStyle = "#fff"; hctx.lineWidth = 2; hctx.beginPath(); hctx.moveTo(x, 0); hctx.lineTo(x, H); hctx.stroke();
    hctx.fillStyle = "#fff"; hctx.beginPath(); hctx.arc(x, 6, 4, 0, 7); hctx.fill();
    void lab;
  }
}
let hdrag = null;
hc.addEventListener("pointerdown", (e) => {
  if (!S.hist) return; hc.setPointerCapture(e.pointerId);
  const r = hc.getBoundingClientRect(), v = S.hist.min + ((e.clientX - r.left) / r.width) * (S.hist.max - S.hist.min);
  hdrag = Math.abs(v - S.lo) < Math.abs(v - S.hi) ? "lo" : "hi"; moveHandle(e);
});
hc.addEventListener("pointermove", (e) => { if (hdrag) moveHandle(e); });
hc.addEventListener("pointerup", () => { hdrag = null; });
function moveHandle(e) {
  const r = hc.getBoundingClientRect(), v = S.hist.min + Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * (S.hist.max - S.hist.min);
  if (hdrag === "lo") S.lo = Math.min(v, S.hi - 1e-9); else S.hi = Math.max(v, S.lo + 1e-9);
  $("#lo").value = +S.lo.toPrecision(5); $("#hi").value = +S.hi.toPrecision(5); drawHist(); scheduleImage(); if (S.showCbar) draw();
}
$("#lo").onchange = (e) => { S.lo = +e.target.value; drawHist(); scheduleImage(); };
$("#hi").onchange = (e) => { S.hi = +e.target.value; drawHist(); scheduleImage(); };
$("#gamma").oninput = (e) => { S.gamma = +e.target.value; $("#gamma-out").textContent = S.gamma.toFixed(2); scheduleImage(); };
$("#log").onchange = (e) => { S.log = e.target.checked; scheduleImage(); };
$("#auto").onclick = () => { [S.lo, S.hi] = S.hist.auto; S.gamma = 1; $("#gamma").value = 1; $("#gamma-out").textContent = "1.00"; refreshHistogram(); scheduleImage(); };

// ================================================================== inspector: info
const LABELS = {
  instrument: ["Instrument", { name: "Name", vendor: "Vendor", model: "Model", serial: "Serial number", facility: "Facility", doi: "DOI" }],
  beam: ["Beam", { voltage_kV: ["Voltage", "kV"], current_nA: ["Current", "nA"], spot: "Spot", probe_size_nm: ["Probe size", "nm"], emission_current_uA: ["Emission", "µA"] }],
  optics: ["Optics", { magnification: ["Magnification", "×"], working_distance_mm: ["Working distance", "mm"], hfw_um: ["Field width", "µm"],
    camera_length_mm: ["Camera length", "mm"], field_of_view_um: ["Field of view", "µm"], mode: "Mode" }],
  detector: ["Detector", { name: "Detector", mode: "Mode", collection_semiangle_mrad: ["Collection angle", "mrad"],
    convergence_semiangle_mrad: ["Convergence angle", "mrad"], exposure_s: ["Exposure", "s"] }],
  acquisition: ["Acquisition", { datetime: "Acquired", operator: "Operator", dwell_us: ["Dwell time", "µs"], frame_integration: "Frames integrated",
    line_integration: "Line integration", scan_rotation_deg: ["Scan rotation", "°"], software: "Software" }],
  sample: ["Sample", { name: "Name", description: "Description" }],
};
function kvCard(title, rows) {
  const dl = el("dl", { class: "kv" });
  for (const [k, v] of rows) dl.append(el("dt", {}, k), el("dd", {}, v));
  return rows.length ? el("div", { class: "card" }, el("h3", {}, title), dl) : null;
}
function renderInfo(s) {
  const box = $("#ins-info"); box.replaceChildren();
  const kindName = { image: "Image", stack: "Image stack", spectrum_image: "Spectrum image", "4d": "4D data", spectrum: "Spectrum" }[s.view.kind] || s.signal;
  box.append(el("div", { class: "ds-head" }, el("h2", {}, s.name),
    el("div", { class: "badges" }, el("span", { class: "badge accent" }, s.metadata.technique || kindName), el("span", { class: "badge" }, kindName),
      el("span", { class: "badge" }, `${s.shape.join(" × ")}`), el("span", { class: "badge" }, s.dtype))));
  box.append(kvCard("Calibration", s.axes.map((a) => [a.name, a.units === "px" ? `${a.size} px, not calibrated` : `${a.size} × ${fmtNum(a.scale)} ${a.units}`])));
  for (const [sec, [title, map]] of Object.entries(LABELS)) {
    const d = s.metadata[sec] || {}, rows = [];
    for (const [k, lab] of Object.entries(map)) {
      if (d[k] == null || d[k] === "") continue;
      const [name, unit] = Array.isArray(lab) ? lab : [lab, ""];
      rows.push([name, unit === "×" ? `${fmtNum(d[k])}×` : `${typeof d[k] === "number" ? fmtNum(d[k]) : d[k]}${unit ? ` ${unit}` : ""}`]);
    }
    if (sec === "sample" && d.stage) rows.push(["Stage", Object.entries(d.stage).map(([k, v]) => `${k.replace(/_.*/, "")} ${fmtNum(v)}`).join(", ")]);
    const c = kvCard(title, rows); if (c) box.append(c);
  }
  if (s.metadata.facility) box.append(kvCard("Facility", [["", s.metadata.facility]]));
  const orig = el("details", { class: "card" }, el("summary", {}, el("b", {}, "Original metadata"), " from the file"));
  const search = el("input", { type: "search", placeholder: "Search keys and values" });
  const tree = el("div", { class: "tree-json" }, el("span", { class: "hint" }, "Loading…"));
  orig.append(search, tree);
  let loaded = null;
  orig.addEventListener("toggle", async () => {
    if (!orig.open || loaded) return;
    loaded = await (await api(`/api/ds/${s.id}/original`)).json(); renderTree(tree, loaded, "");
  });
  search.addEventListener("input", () => loaded && renderTree(tree, loaded, search.value.trim().toLowerCase()));
  box.append(orig);
}
function renderTree(host, obj, q) {
  host.replaceChildren();
  let count = 0;
  const walk = (o, parent, depth, path) => {
    for (const [k, v] of Object.entries(o)) {
      if (count > 1500) return;
      const p = `${path}${k}`.toLowerCase();
      if (v && typeof v === "object" && !Array.isArray(v)) {
        const d = el("details", q || depth < 1 ? { open: true } : {}, el("summary", {}, k)); const before = count;
        walk(v, d, depth + 1, `${path}${k}.`);
        if (!q || count > before) parent.append(d);
      } else if (!q || p.includes(q) || String(v).toLowerCase().includes(q)) {
        count++; parent.append(el("div", { class: "leaf" }, el("span", {}, `${k}: `), Array.isArray(v) ? JSON.stringify(v) : String(v)));
      }
    }
  };
  walk(obj, host, 0, "");
  if (!host.children.length) host.append(el("span", { class: "hint" }, q ? "Nothing matches." : "No original metadata."));
}

// ================================================================== inspector: analyze
const TOOLS = [
  { op: "stats", title: "Noise and contrast", text: "Intensity range, noise level and signal-to-noise ratio.", form: [] },
  { op: "denoise", title: "Denoise", text: "Creates a cleaner copy; the original is kept.", form: [
    ["method", "Method", "select", [["nlm", "Non-local means"], ["gaussian", "Gaussian"], ["median", "Median"]]], ["strength", "Strength", "number", 1]] },
  { op: "subtract_background", title: "Remove uneven background", text: "Subtracts slow shading across the field.", form: [["sigma_nm", "Smoothing width (nm)", "number", 2000]] },
  { op: "fft", title: "Fourier transform", text: "Power spectrum with reciprocal-space calibration (1/nm).", form: [] },
  { op: "radial_profile", title: "Radial profile", text: "Azimuthal average of a power spectrum or diffraction pattern; peaks give periodicities.", form: [], need: "diffraction" },
  { op: "particles", title: "Particles", text: "Finds features and measures size and shape in nm. Outlines are drawn on the image.", form: [
    ["method", "Threshold", "select", [["otsu", "Otsu (automatic)"], ["li", "Li"], ["triangle", "Triangle"]]], ["dark", "Features are darker than background", "check", false],
    ["min_area_nm2", "Smallest area (nm²)", "number", 0], ["separate", "Split touching particles", "check", false]] },
  { op: "line_profile", title: "Line profile", text: "Choose the line tool (L) and drag across the image.", form: [["width", "Line width (px)", "number", 3, "lp-width"]], manual: true },
  { op: "calibrate", title: "Correct the pixel size", text: "For example after measuring a calibration standard. The reason is kept in the history.", form: [
    ["pixel_size_nm", "Pixel size (nm)", "number", null], ["reason", "Reason", "text", ""]] },
  { op: "bin", title: "Bin 2 × 2", text: "Averages 2 × 2 pixels: half the size, less noise.", form: [["factor", "Factor", "number", 2]] },
];
function renderTools(s) {
  const host = $("#tools-list"); host.replaceChildren();
  for (const t of TOOLS) {
    const disabled = t.need === "diffraction" && s.signal !== "diffraction";
    const det = el("details", { class: `tool ${disabled ? "disabled" : ""}` }, el("summary", {}, el("b", {}, t.title), el("small", {}, disabled ? "Run Fourier transform first, then use it on the result." : t.text)));
    const body = el("div", { class: "body" });
    const inputs = {};
    for (const [key, label, type, def, id] of t.form) {
      let inp;
      if (type === "select") inp = el("select", {}, ...def.map(([v, l]) => el("option", { value: v }, l)));
      else if (type === "check") { inp = el("input", { type: "checkbox", ...(def ? { checked: true } : {}) }); body.append(el("label", { class: "toggle" }, inp, ` ${label}`)); inputs[key] = inp; continue; }
      else inp = el("input", { type, value: def ?? (key === "pixel_size_nm" ? (s.pixel_size_nm ?? "") : ""), step: "any", ...(id ? { id } : {}) });
      inputs[key] = inp; body.append(el("label", {}, label, inp));
    }
    if (!t.manual) body.append(el("button", { class: "btn primary wide", disabled, on: () => {
      const params = {};
      for (const [k, inp] of Object.entries(inputs)) params[k] = inp.type === "checkbox" ? inp.checked : inp.type === "number" ? (inp.value === "" ? null : +inp.value) : inp.value;
      if (t.op === "calibrate" && !params.pixel_size_nm) return toast("Enter a pixel size", "", "err");
      runTool(t.op, params);
    } }, `Run ${t.title.toLowerCase()}`));
    else body.append(el("button", { class: "btn wide", on: () => setTool("line") }, "Use the line tool"));
    det.append(body); host.append(det);
  }
}
const RESULTS = new Map();   // dataset id -> its result cards
function stashResults(nextId) {
  const box = $("#results");
  if (S.cur && S.cur !== nextId) RESULTS.set(S.cur, [...box.children].filter((c) => c.classList.contains("result")));
  box.replaceChildren(...(RESULTS.get(nextId) || []));
  if (!box.children.length) box.append(el("div", { class: "empty-note" }, "Results of the tools above appear here."));
}
async function runTool(op, params) {
  const s = S.items.get(S.cur);
  const card = el("div", { class: "result" }, el("div", { class: "result-head" }, el("b", {}, TOOLS.find((t) => t.op === op)?.title || op), el("span", { class: "spinner" })));
  const results = $("#results"); $(".empty-note", results)?.remove(); results.prepend(card);
  $$("#ins-tabs button").find((b) => b.dataset.tab === "analyze").click();
  const reveal = () => { const box = $("#ins-analyze");
    if (box.scrollHeight <= box.clientHeight) return card.scrollIntoView({ block: "nearest" });   // narrow layout: the page scrolls
    box.scrollTop = card.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop - 8; };
  reveal();
  try {
    const r = await post(`/api/ds/${s.id}/run`, { op, params, frame: S.frame });
    card.firstChild.lastChild.replaceWith(el("small", {}, `${r.seconds} s`));
    if (r.kind === "dataset") {
      S.items.set(r.dataset.id, r.dataset); renderOpen();
      card.append(el("p", { class: "hint" }, `New dataset: ${r.dataset.name}. It is linked to its source under Open.`),
        el("button", { class: "btn wide", on: () => show(r.dataset.id) }, "Show result"));
      if (["denoise", "fft", "subtract_background", "bin", "calibrate"].includes(op)) await show(r.dataset.id);
    } else if (r.kind === "values") {
      const v = r.values, keys = [["mean", "Mean"], ["std", "Std. dev."], ["noise_sigma", "Noise σ"], ["snr", "SNR"], ["min", "Min"], ["max", "Max"]];
      card.append(el("div", { class: "vals" }, ...keys.filter(([k]) => k in v).map(([k, l]) => el("div", {}, el("small", {}, l), el("b", {}, fmtNum(v[k]))))));
    } else if (r.kind === "table") renderTable(card, r, op);
    if (r.kind !== "dataset") reveal();
    renderHistory(await (await api(`/api/ds/${S.cur}`)).json());
  } catch (e) {
    card.firstChild.lastChild.replaceWith(el("small", { style: "color:var(--err)" }, "failed"));
    card.append(el("p", { class: "hint" }, e.message));
  }
}
function renderTable(card, r, op) {
  const col = (n) => r.columns.indexOf(n);
  if (op === "particles") {
    const area = r.attrs.area_fraction, u = r.attrs.units;
    card.append(el("div", { class: "vals" }, el("div", {}, el("small", {}, "Particles"), el("b", {}, r.n.toLocaleString())),
      el("div", {}, el("small", {}, `Median diameter (${u})`), el("b", {}, r.n ? fmtNum(median(r.rows.map((x) => x[col("eq_diameter_nm")]))) : "–")),
      el("div", {}, el("small", {}, "Area fraction"), el("b", {}, `${(100 * area).toFixed(1)} %`))));
    if (r.n) { const h = el("div", { class: "chart" }); card.append(h); Charts.hist(h, { values: r.rows.map((x) => x[col("eq_diameter_nm")]), xLabel: `equivalent diameter (${u})`, bins: 24, color: Charts.css("accent") }); }
    if (r.overlay) {
      const img = new Image(); img.onload = () => { const c = document.createElement("canvas"); c.width = img.width; c.height = img.height; c.getContext("2d").drawImage(img, 0, 0); S.overlay = c; S.overlayTid = r.table; $("#overlay-toggle").hidden = false; draw(); };
      img.src = `/api/ds/${S.cur}/overlay/${r.table}.png`;
    }
  } else if (op === "line_profile") {
    const h = el("div", { class: "chart" }); card.append(h);
    let u = physAxes()[1].units === "px" ? "px" : "nm", k = 1;
    if (u === "nm" && r.rows.at(-1)[0] > 5000) { u = "µm"; k = 1e-3; }
    Charts.lines(h, { height: 190, xLabel: `distance (${u})`, endLabels: false, yMin: null, series: [{ name: "intensity", color: Charts.css("accent"), pts: r.rows.map((x) => ({ x: x[0] * k, y: x[1] })) }] });
  } else if (op === "radial_profile") {
    const h = el("div", { class: "chart" }); card.append(h);
    const micro = r.rows.at(-1)[0] < 0.01, k = micro ? 1e3 : 1, fu = micro ? "1/µm" : "1/nm", pu = micro ? "µm" : "nm";
    Charts.lines(h, { height: 190, xLabel: `spatial frequency (${fu})`, endLabels: false, logY: true, series: [{ name: "intensity", color: Charts.css("accent"), pts: r.rows.filter((x) => x[0] > 0).map((x) => ({ x: x[0] * k, y: Math.max(x[1], 1e-12) })) }] });
    const best = r.rows.slice(3).reduce((a, b) => (b[1] > a[1] ? b : a), r.rows[3] || r.rows[0]);
    if (best) card.append(el("p", { class: "hint" }, `Strongest peak at ${fmtNum(best[0] * k)} ${fu}, a period of ${fmtNum(best[3] / k)} ${pu}.`));
  }
  const tbl = el("div", { class: "tbl" });
  const draw = (sortCol = null, dir = 1) => {
    const rows = r.rows.slice(); if (sortCol != null) rows.sort((a, b) => (a[sortCol] - b[sortCol]) * dir);
    tbl.replaceChildren(el("table", { class: "t" }, el("thead", {}, el("tr", {}, ...r.columns.map((c, i) => el("th", { on: () => draw(i, sortCol === i ? -dir : -1) }, c.replace(/_/g, " "))))),
      el("tbody", {}, ...rows.slice(0, 400).map((row) => el("tr", {}, ...row.map((v) => el("td", {}, typeof v === "number" ? fmtNum(v) : String(v))))))));
  };
  draw();
  const more = el("details", {}, el("summary", { class: "hint" }, `Table (${r.n.toLocaleString()} rows)`), tbl);
  card.append(more, el("button", { class: "btn wide", on: () => download(`/api/table/${r.table}.csv`) }, "Download CSV"));
}
const median = (a) => { const s = a.slice().sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };

// ================================================================== inspector: history
const OPNAMES = { "io.read.thermo": "Read Thermo Fisher / FEI file", "io.read.zeiss": "Read Zeiss file", "io.read.hitachi": "Read Hitachi file",
  "io.read.jeol": "Read JEOL file", "io.read.digitalmicrograph": "Read Gatan DigitalMicrograph file", "io.read.nuscope": "Opened NUScope file",
  "analyze.denoise": "Denoised", "analyze.fft": "Fourier transform", "analyze.particles": "Measured particles", "analyze.stats": "Measured noise and contrast",
  "analyze.subtract_background": "Removed background", "analyze.radial_profile": "Radial profile", "analyze.line_profile": "Line profile",
  "analyze.calibrate": "Corrected pixel size", "analyze.bin": "Binned", "analyze.crop": "Cropped", "analyze.threshold": "Thresholded",
  "studio.view": "Took the displayed view", "create.from_array": "Created from an array" };
// ------------------------------------------------------------------ integrity: seal, signatures, keys
const SHIELD = '<svg viewBox="0 0 24 24"><path d="M12 3 5 6v5c0 4.4 3 8.3 7 10 4-1.7 7-5.6 7-10V6z"/><path d="m9 12 2 2 4-4"/></svg>';
const SHIELD_X = '<svg viewBox="0 0 24 24"><path d="M12 3 5 6v5c0 4.4 3 8.3 7 10 4-1.7 7-5.6 7-10V6z"/><path d="m9.5 9.5 5 5m0-5-5 5"/></svg>';
const svg = (markup) => { const t = document.createElement("template"); t.innerHTML = markup; return t.content.firstChild; };

function renderSignNote() {
  const n = $("#sign-note"); if (!n) return;
  n.replaceChildren(svg(SHIELD));
  if (S.key) n.append(el("span", {}, `Sealed and signed with your key · ${S.key.name} · `, el("code", {}, S.key.fingerprint)));
  else n.append(el("span", {}, "Sealed with SHA-256 hashes. ", el("a", { on: (e) => { e.stopPropagation(); closeMenus(); keyDialog(); } }, "Create a signing key"), " to sign as well."));
}
function keyDialog() {
  const name = el("input", { type: "text", placeholder: "Your name" }), orcid = el("input", { type: "text", placeholder: "https://orcid.org/0000-…" });
  const body = el("div", {},
    el("p", { class: "hint" }, "Your key signs every file you save, so anyone can check that the data, metadata and history are exactly as you left them, and that they come from you. The private key stays on this computer, readable only by you."),
    el("div", { class: "row" }, el("label", {}, "Name", name), el("label", {}, "ORCID (optional)", orcid)));
  modal("Create your signing key", body, "Create key", async () => {
    try {
      S.key = await post("/api/keys", { name: name.value, orcid: orcid.value });
      renderSignNote();
      toast("Signing key created", ` Fingerprint ${S.key.fingerprint}. Files you save from now on are signed.`, "ok");
      const cur = S.items.get(S.cur); if (cur) renderHistory(cur);
    } catch (e) { toast("Could not create the key", ` ${e.message}`, "err"); return false; }
  });
  setTimeout(() => name.focus(), 50);
}
const SAVED = new Map();   // dataset id -> {path, integrity} of its last save
function sealCard(s) {
  const saved = SAVED.get(s.id), r = s.integrity || saved?.integrity, card = el("div", { class: `card seal ${r ? r.status : "none"}` });
  const steps = s.activities.length;
  const chain = s.chain?.intact ? `History chain intact: ${steps} step${steps === 1 ? "" : "s"} linked by SHA-256.` : `History chain: ${(s.chain?.problems || []).join("; ")}`;
  if (!r) {
    card.append(el("div", { class: "seal-head" }, svg(SHIELD), "Not sealed yet"),
      el("p", { class: "hint" }, s.sources.length ? "Read from an instrument file; its SHA-256 is recorded below. " : "",
        "Saving writes a seal with hashes of the data, calibration, metadata and history",
        S.key ? `, signed by ${S.key.name}.` : ". ", S.key ? "" : el("a", { class: "link", on: keyDialog }, "Create a signing key"), S.key ? "" : " to sign it too."),
      el("p", { class: "hint" }, chain));
    return card;
  }
  const head = { signed: "Signed and intact", sealed: "Intact · sealed, not signed", tampered: "Changed after it was sealed", unsealed: "No seal in this file" }[r.status];
  card.append(el("div", { class: "seal-head" }, svg(r.status === "tampered" ? SHIELD_X : SHIELD), head));
  if (!s.integrity) card.append(el("small", { class: "hint" }, "Your saved file ", el("code", {}, saved.path), el("br")));
  if (r.sealed_at) card.append(el("small", { class: "hint" }, `Sealed ${new Date(r.sealed_at).toLocaleString()} · seal `, el("code", {}, (r.seal_id || "").slice(0, 16) + "…")));
  const labels = { data: "Data", calibration: "Calibration", metadata: "Metadata", history: "History", "history chain": "History chain" };
  card.append(el("div", { class: "checks" }, ...Object.entries(r.checks).map(([k, v]) => el("span", { class: v ? "y" : "n" }, `${v ? "✓" : "✗"} ${labels[k] || k}`))));
  for (const g of r.signatures) {
    const tag = !g.valid ? el("span", { class: "tag-err" }, "signature invalid") : g.trusted ? el("span", { class: "tag-ok" }, "trusted key") : el("span", { class: "tag-warn", title: "Valid signature, but this key is not in your trusted list. Trust it with: nuscope keys trust <file.pub.json>" }, "unknown key");
    card.append(el("div", { class: "signer" }, el("b", {}, g.name, g.role ? ` · ${g.role}` : ""), tag,
      el("small", {}, g.orcid ? `${g.orcid} · ` : "", "key ", el("code", {}, g.fingerprint), " · ", new Date(g.signed_at).toLocaleString())));
  }
  for (const i of r.instruments || []) card.append(el("div", { class: "signer" }, el("b", {}, "Instrument"), el("span", { class: "tag-ok" }, "DOI"),
    el("small", {}, i.name || "", " · ", el("a", { href: `https://doi.org/${i.doi}`, target: "_blank", rel: "noopener" }, i.doi))));
  for (const d of r.identifiers || []) card.append(el("div", { class: "signer" }, el("b", {}, "Dataset DOI"), el("span", { class: d.state === "findable" ? "tag-ok" : "tag-warn" }, d.state),
    el("small", {}, d.doi, ` · ${d.datacite} DataCite`)));
  for (const p of r.problems) card.append(el("p", { class: "hint", style: "color:var(--err)" }, p));
  if (r.status !== "tampered") card.append(el("p", { class: "hint" }, s.integrity ? "Checked when the file was opened. Steps added since then are covered when you save again." : "Checked right after saving."));
  return card;
}

function renderHistory(s) {
  const box = $("#ins-history"); box.replaceChildren();
  box.append(sealCard(s));
  box.append(el("p", { class: "hint" }, "Everything done to this dataset, oldest first. It is saved inside every file you save and can be exported."));
  const ul = el("ul", { class: "timeline" });
  for (const a of s.activities) {
    const params = a.params?.seal
      ? `${a.params.integrity} · seal ${a.params.seal.slice(0, 12)}… · ${a.params.signed_by.length} signature${a.params.signed_by.length === 1 ? "" : "s"}`
      : Object.entries(a.params || {}).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(", ");
    const cls = a.op.startsWith("io.read") ? "read" : a.op.startsWith("io.save") ? "save" : "";
    const name = OPNAMES[a.op] || (a.op.startsWith("io.save") ? `Saved as ${a.op.split(".").pop()}` : a.op.startsWith("io.read") ? `Read ${a.op.split(".").pop()} file` : a.op);
    ul.append(el("li", { class: cls }, el("b", {}, name),
      el("small", {}, new Date(a.ended || a.started).toLocaleString(), " · ", a.software?.nuscope ? `NUScope ${a.software.nuscope}` : "", a.host ? ` · ${a.host}` : ""),
      params ? el("small", {}, el("code", {}, params)) : null));
  }
  box.append(ul);
  if (s.sources.length) {
    box.append(el("h3", { class: "sec" }, "Source files"));
    for (const e of s.sources) box.append(el("div", { class: "card src" }, el("b", {}, e.label), el("br"),
      el("small", {}, fmtBytes(e.size), " · SHA-256 ", el("code", {}, (e.sha256 || "").slice(0, 16) + "…")), el("br"),
      el("small", {}, e.location || "")));
  }
  const people = s.agents.filter((a) => a.kind !== "software");
  if (people.length) box.append(kvCard("Agents", people.map((a) => [a.kind, a.name + (a.orcid ? ` (${a.orcid})` : "")])));
  box.append(el("button", { class: "btn wide", on: () => download(`/api/ds/${s.id}/prov.json`) }, "Download provenance (PROV-JSON)"),
    el("button", { class: "btn wide", on: crateDialog }, "Package for a repository (RO-Crate)…"));
}

// ================================================================== save, export, crate
function closeMenus() { $$(".menu-list").forEach((m) => (m.hidden = true)); }
$$(".menu > .btn").forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); const l = b.nextElementSibling; const was = l.hidden; closeMenus(); l.hidden = !was; }));
document.addEventListener("click", closeMenus);
$$("[data-save]").forEach((b) => b.addEventListener("click", async () => {
  try {
    const r = await post(`/api/ds/${S.cur}/save`, { format: b.dataset.save });
    const g = r.integrity.signatures.filter((x) => x.valid).map((x) => x.name);
    SAVED.set(S.cur, r);
    toast(g.length ? "Saved, sealed and signed" : "Saved and sealed", ` ${r.path}${g.length ? ` · signed by ${g.join(", ")}` : ""}`, "ok");
    renderHistory(await (await api(`/api/ds/${S.cur}`)).json());
    if (r.download) download(r.download);
  } catch (e) { toast("Could not save", ` ${e.message}`, "err"); }
}));
$$("[data-fig]").forEach((b) => b.addEventListener("click", () => {
  const q = new URLSearchParams({ fmt: b.dataset.fig, frame: S.frame, lo: S.lo, hi: S.hi, gamma: S.gamma, log: S.log, cmap: S.cmap, scalebar: S.showScale, colorbar: S.showCbar });
  download(`/api/ds/${S.cur}/figure?${q}`);
  toast("Exporting figure", ` ${b.dataset.fig.toUpperCase()} with the current colours and contrast.`);
}));
function modal(title, body, okText, onOk) {
  $("#modal-title").textContent = title; $("#modal-body").replaceChildren(body); $("#modal-ok").textContent = okText;
  $("#modal").hidden = false;
  $("#modal-ok").onclick = async () => { if ((await onOk()) !== false) $("#modal").hidden = true; };
}
$("#modal-cancel").onclick = () => { $("#modal").hidden = true; };
function crateDialog() {
  const items = [...S.items.values()];
  const checks = items.map((s) => el("label", { class: "toggle" }, el("input", { type: "checkbox", value: s.id, ...(s.id === S.cur ? { checked: true } : {}) }), ` ${s.name}`));
  const title = el("input", { type: "text", value: S.items.get(S.cur)?.name || "" });
  const name = el("input", { type: "text", placeholder: "Your name" }), orcid = el("input", { type: "text", placeholder: "https://orcid.org/0000-…" });
  const body = el("div", {}, el("p", { class: "hint" }, "Writes the datasets as NeXus files with an ro-crate-metadata.json that describes files, people, instruments and every processing step, zipped for upload to a repository."),
    el("label", {}, "Title", title), el("div", { class: "row" }, el("label", {}, "Author", name), el("label", {}, "ORCID (optional)", orcid)),
    el("h3", { class: "sec" }, "Datasets"), el("div", { style: "display:grid;gap:4px" }, ...checks));
  modal("Package as RO-Crate", body, "Create package", async () => {
    const ids = checks.map((c) => c.firstChild).filter((c) => c.checked).map((c) => c.value);
    if (!ids.length) { toast("Choose at least one dataset", "", "err"); return false; }
    try {
      const r = await post("/api/crate", { ids, title: title.value, authors: name.value ? [{ name: name.value, orcid: orcid.value || undefined }] : [] });
      toast("RO-Crate ready", ` ${r.folder}`, "ok"); download(r.download);
    } catch (e) { toast("Could not package", ` ${e.message}`, "err"); return false; }
  });
}

// ================================================================== Globus
$("#g-browse").onclick = () => browseGlobus($("#g-coll").value.trim(), $("#g-path").value.trim() || "/");
async function browseGlobus(coll, path) {
  if (coll.length !== 36) return toast("Enter a collection id", " It is the UUID shown in the Globus web app under Collections.", "err");
  const list = $("#g-list"); list.replaceChildren(el("li", {}, el("span", { class: "spinner" }), el("span", { class: "nm" }, "Listing…")));
  try {
    const d = await (await api(`/api/globus/ls?collection=${coll}&path=${encodeURIComponent(path)}`)).json();
    $("#g-path").value = path; list.replaceChildren();
    if (path !== "/") list.append(fileRow({ name: "..", dir: true, path: "", ext: "" }, "", () => browseGlobus(coll, path.replace(/\/[^/]+\/?$/, "") || "/")));
    for (const e of d.entries) list.append(fileRow(e, "", (f) => (f.dir ? browseGlobus(coll, f.path) : openUrl(`globus://${coll}${f.path}`))));
    try { localStorage.setItem("nuscope-globus", coll); } catch (e2) { /* storage blocked */ }
  } catch (e) { list.replaceChildren(el("li", {}, el("span"), el("span", { class: "nm" }, e.message))); }
}

// ================================================================== tabs, theme, boot
$$("#ins-tabs button").forEach((b) => b.addEventListener("click", () => {
  $$("#ins-tabs button").forEach((x) => x.classList.toggle("on", x === b));
  for (const t of ["info", "analyze", "history"]) $(`#ins-${t}`).hidden = t !== b.dataset.tab;
}));
function applyTheme(t) {
  if (t === "light") document.documentElement.dataset.theme = "light"; else delete document.documentElement.dataset.theme;
  try { localStorage.setItem("nuscope-studio-theme", t); } catch (e) { /* storage blocked */ }
  draw(); drawHist();
}
$("#theme-btn").onclick = () => applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");

(async function boot() {
  try { applyTheme(localStorage.getItem("nuscope-studio-theme") || "dark"); } catch (e) { /* storage blocked */ }
  const st = await (await api("/api/state")).json();
  S.rootName = st.name; S.key = st.key; renderSignNote();
  $("#folder-chip").textContent = `${st.name} · NUScope ${st.version}`; $("#folder-chip").title = st.root;
  $("#globus-hint").textContent = st.globus.configured
    ? "Browse a Globus collection and open files directly. Log in once in a terminal with: nuscope globus login <collection id>"
    : "Globus is not set up yet. Register NUScope as a native app at app.globus.org/settings/developers, then run: nuscope globus setup <client id> and nuscope globus login <collection id>.";
  try { $("#g-coll").value = localStorage.getItem("nuscope-globus") || ""; } catch (e) { /* storage blocked */ }
  // datasets stay open on the server, so a page reload picks up where it left off
  const sess = await (await api("/api/session")).json();
  for (const it of await Promise.all(sess.map((x) => api(`/api/ds/${x.id}`).then((r) => r.json())))) S.items.set(it.id, it);
  renderOpen();
  await loadLibrary("");
  if (sess.length) await show(sess.at(-1).id);
})();
