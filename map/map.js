// Line Down pixel map: two maps on one clock, a normal day (left) and the day of a subway delay (right).
// Every dot is a real Bike Share trip from data.js (written by export.py); map units are 100 m.
// Pixel art: each colour is drawn on its own layer with edges snapped on or off, on a small canvas
// where one art pixel is 2 device pixels, then scaled up without smoothing. Text is drawn crisp on top.
const [W, H] = DATA.size;
const SLOTS = DATA.slot_minutes, K0 = SLOTS.indexOf(0), SPAN = SLOTS.length * 15 * 60;   // seconds shown
const SPEED = 300;   // 4 hours play in 48 seconds
const C = { bg: "#fbfaf7", lake: "#d7e6f0", dock: "#dcd8cf", ring: "#e58b84", red: "#d62d20", rim: "#555555", white: "#ffffff",
            hot: "#f05a00", trail: ["#f47b20", "#f8a768", "#fbcfa9"], far: "#bdb8ae", ink: "#1d1d1f" };
let ART = 2;   // css pixels per art pixel, set so one art pixel is 2 device pixels

const scratch = document.createElement("canvas"), sg = scratch.getContext("2d", { willReadFrequently: true });
function layer(target, color, paint) {   // paint() draws in css pixels; lands on target in one solid colour
  scratch.width = target.canvas.width; scratch.height = target.canvas.height;
  sg.setTransform(1 / ART, 0, 0, 1 / ART, 0, 0);
  sg.fillStyle = sg.strokeStyle = color; sg.lineJoin = sg.lineCap = "round";
  paint(sg);
  const d = sg.getImageData(0, 0, scratch.width, scratch.height), a = d.data;
  for (let i = 3; i < a.length; i += 4) a[i] = a[i] >= 110 ? 255 : 0;
  sg.putImageData(d, 0, 0);
  target.drawImage(scratch, 0, 0);
}

const $ = id => document.getElementById(id);
const stationXY = Object.fromEntries(DATA.stations.map(s => [s.name, s.xy]));
const terminals = new Set(Object.values(DATA.lines).flatMap(l => l.ends));
const short = s => s.replace(/ Station$/, "");
const day = (iso, opts) => new Date(iso.slice(0, 10) + "T12:00").toLocaleDateString("en-CA", opts);
const weekday = iso => day(iso, { weekday: "long" });
const longDate = iso => day(iso, { weekday: "long", month: "long", day: "numeric", year: "numeric" });
function clock(iso, plusMin) {
  const [h, m] = iso.slice(11, 16).split(":").map(Number), t = h * 60 + m + Math.floor(plusMin), hh = Math.floor(t / 60) % 24;
  return `${(hh + 11) % 12 + 1}:${String(t % 60).padStart(2, "0")} ${hh < 12 ? "am" : "pm"}`;
}

const panels = [
  { canvas: $("mapNormal"), count: $("countNormal"), key: "trips_normal" },
  { canvas: $("mapDay"), count: $("countDay"), key: "trips" },
];
for (const p of panels) {
  p.ctx = p.canvas.getContext("2d");
  p.art = document.createElement("canvas"); p.g = p.art.getContext("2d");
  p.base = document.createElement("canvas"); p.bg = p.base.getContext("2d");
}
let ev = null, T = 0, playing = false, last = 0, view, k, cssW, cssH, atOff;

// framing shared by both maps: about 6 km across (4.5 km when narrow), centred on the stopped station(s)
function frame() {
  cssW = panels[0].canvas.clientWidth; cssH = Math.round(Math.min(cssW * (cssW < 500 ? 0.6 : 0.8), innerHeight * 0.5));
  ART = 2 / (devicePixelRatio || 1);
  const pts = ev.affected.map(s => stationXY[s]), cx = pts.reduce((a, p) => a + p[0], 0) / pts.length, cy = pts.reduce((a, p) => a + p[1], 0) / pts.length;
  const vw = Math.max(cssW < 500 ? 45 : 60, Math.max(...pts.map(p => p[0])) - Math.min(...pts.map(p => p[0])) + 30);
  k = cssW / vw; view = { x: cx - vw / 2, y: cy - cssH / k / 2 };
  for (const p of panels) {
    const r = devicePixelRatio || 1;
    p.canvas.style.height = cssH + "px"; p.canvas.width = Math.round(cssW * r); p.canvas.height = Math.round(cssH * r);
    p.art.width = p.base.width = Math.ceil(cssW / ART); p.art.height = p.base.height = Math.ceil(cssH / ART);
    drawBase(p.bg);
  }
}
const P = ([x, y]) => [(x - view.x) * k, (y - view.y) * k];                                       // css pixels
const A = ([x, y]) => [Math.round((x - view.x) * k / ART), Math.round((y - view.y) * k / ART)];   // art pixels

function path(ctx, pts) { ctx.beginPath(); pts.forEach((p, i) => { const [x, y] = P(p); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); }
const dots = (list, r) => ctx => { for (const [x, y] of list) { ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill(); } };

function drawBase(g) {   // everything that does not move
  g.fillStyle = C.bg; g.fillRect(0, 0, g.canvas.width, g.canvas.height);
  const s = DATA.shore;
  layer(g, C.lake, ctx => { path(ctx, [[-50, s[0][1]], ...s, [W + 50, s[s.length - 1][1]], [W + 50, H + 200], [-50, H + 200]]); ctx.closePath(); ctx.fill(); });
  g.fillStyle = C.dock;
  for (const b of Object.values(DATA.bikes)) { const [x, y] = A(b.xy); g.fillRect(x, y, 1, 1); }
  for (const id of ["2", "4", "1"]) {
    const l = DATA.lines[id];
    if (l) layer(g, l.color, ctx => { path(ctx, l.points); ctx.lineWidth = 5; ctx.stroke(); });
  }
  const centres = ev.affected.map(s => P(stationXY[s]));
  layer(g, C.ring, ctx => { ctx.setLineDash([6, 6]); ctx.lineWidth = 2; for (const [x, y] of centres) { ctx.beginPath(); ctx.arc(x, y, 10 * k, 0, 7); ctx.stroke(); } });
  const st = DATA.stations.map(s => P(s.xy));
  layer(g, C.rim, dots(st, 5.5));
  layer(g, C.white, dots(st, 3.5));
  layer(g, C.white, dots(centres, 9));
  layer(g, C.red, dots(centres, 7));
}

function where(trip, t) {   // straight line from start dock to end dock over the trip's real duration
  const a = DATA.bikes[trip[2]]?.xy, b = DATA.bikes[trip[3]]?.xy ?? a;
  const f = Math.min(1, Math.max(0, (t - trip[0]) / trip.dur));
  return a && [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
}

function drawPanel(p) {
  const g = p.g, trips = ev[p.key];
  g.drawImage(p.base, 0, 0);
  let count = 0;
  for (const tr of trips) {
    if (tr[4] && tr[0] >= atOff && tr[0] < T) count++;   // same window as the headline's hour
    if (tr[0] > T || T > tr[0] + tr.dur) continue;
    const xy = where(tr, T);
    if (!xy) continue;
    if (!tr[4]) { const [x, y] = A(xy); g.fillStyle = C.far; g.fillRect(x, y, 2, 2); continue; }
    for (let j = C.trail.length * 2; j >= 1; j--) {   // fading trail: where it was over the last 3 minutes
      const tt = T - j * 30;
      if (tt < tr[0]) continue;
      const [x, y] = A(where(tr, tt)); g.fillStyle = C.trail[Math.floor((j - 1) / 2)]; g.fillRect(x, y, 2, 2);
    }
    const [x, y] = A(xy); g.fillStyle = C.hot; g.fillRect(x - 1, y - 1, 3, 3);
  }
  p.count.textContent = T >= atOff ? count : "0";
  const ctx = p.ctx, r = devicePixelRatio || 1;
  ctx.setTransform(r, 0, 0, r, 0, 0); ctx.imageSmoothingEnabled = false;
  ctx.drawImage(p.art, 0, 0, p.art.width * ART, p.art.height * ART);
  ctx.font = '600 13px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif';
  ctx.lineWidth = 4; ctx.lineJoin = "round"; ctx.strokeStyle = "rgba(251,250,247,.95)";
  for (const s of DATA.stations) {
    const hot = ev.affected.includes(s.name);
    if (!hot && !terminals.has(s.name)) continue;
    const [x, y] = P(s.xy);
    if (x < 0 || x > cssW - 60 || y < 0 || y > cssH) continue;
    ctx.strokeText(short(s.name), x + 11, y + 4); ctx.fillStyle = hot ? C.red : C.ink; ctx.fillText(short(s.name), x + 11, y + 4);
  }
}

function render() {
  for (const p of panels) drawPanel(p);
  const since = Math.floor((T - atOff) / 60);
  $("clock").innerHTML = `<b>${clock(ev.slot0, T / 60 + SLOTS[0])}</b><br>` +
    (since >= 0 ? `${since} min after the delay` : `${-since} min before the delay`);
  $("slider").value = T;
  if ($("more").open) drawChart();
}

function loop(now) {
  if (playing) {
    T = Math.min(SPAN, T + Math.min(0.25, (now - last) / 1000) * SPEED);
    if (T >= SPAN) setPlaying(false);
    render();
  }
  last = now;
  requestAnimationFrame(loop);
}
function setPlaying(on) {
  playing = on;
  $("play").textContent = on ? "❚❚" : "▶"; $("play").setAttribute("aria-label", on ? "Pause" : "Play");
}

function select(i) {
  ev = DATA.events[i];
  for (const key of ["trips", "trips_normal"]) for (const tr of ev[key]) tr.dur = Math.max(60, Math.min(tr[1] ?? 600, 3 * 3600));   // display only
  atOff = (new Date(ev.when) - new Date(ev.slot0)) / 1000 - SLOTS[0] * 60;
  document.querySelectorAll(".events button").forEach((b, j) => b.setAttribute("aria-pressed", j === i));
  const wd = weekday(ev.when), station = short(ev.from) + (ev.to ? ` to ${short(ev.to)}` : "");
  const normals = Object.values(ev.first_hour_normal), avg = Math.round(normals.reduce((a, b) => a + b, 0) / normals.length);
  const shown = ev.first_hour_normal[ev.normal_offset];
  $("headline").innerHTML = `In the hour after the subway stopped at ${station}, <span class="hot">${ev.first_hour}</span> bike trips started within 1 km. On a normal ${wd}: ${shown}.`;
  const cause = ev.cause ? `: ${ev.cause.toLowerCase().replace(/\bttc\b/g, "TTC")}` : "";
  $("sub").textContent = `Line ${ev.line}, ${longDate(ev.when)}, ${clock(ev.when, 0)}, logged as a ${ev.min_delay}-minute delay${cause}. ` +
    `The normal day shown is ${longDate(ev.normal_date)}. Across all ${normals.length} normal days that hour had ${Math.min(...normals)} to ${Math.max(...normals)} trips (average ${avg}).`;
  $("titleNormal").innerHTML = `A normal ${wd}<small>${longDate(ev.normal_date)}</small>`;
  $("titleDay").innerHTML = `Line ${ev.line} stopped at ${station}<small>${longDate(ev.when)}</small>`;
  document.querySelectorAll(".countLabel").forEach(el => el.textContent = `bike trips started within 1 km since ${clock(ev.when, 0)}`);
  $("note").textContent = `Each dot is one real Bike Share trip, moving in a straight line from the dock where it started to the dock where it ended, over its real duration (the real route is unknown). ` +
    `The normal day is the same weekday and time 1-4 weeks before or after with no delay on that line, picked by a fixed rule: the one whose trip count is closest to the average of all ${normals.length} such days. ` +
    `A single day can be partly chance. Across 3,777 delays of 10+ minutes, trips within 250 m rise 13.6% on average in the first hour, peaking at +26% 15-30 minutes after the delay.`;
  frame(); T = 0; render(); setPlaying(true);
}

function drawChart() {
  const c = $("chart"), cx = c.getContext("2d"), r = devicePixelRatio || 1, w = c.clientWidth, h = 150, padL = 24, padB = 20;
  c.style.height = h + "px"; c.width = w * r; c.height = h * r; cx.setTransform(r, 0, 0, r, 0, 0);
  const bw = (w - padL) / SLOTS.length, top = Math.max(...ev.total_actual, ...ev.total_normal_high, 4), now = Math.floor(T / 900);
  const Y = v => (h - padB) - v / top * (h - padB - 8);
  cx.font = "11px -apple-system, Helvetica, Arial, sans-serif"; cx.fillStyle = "#8e8e93";
  cx.fillText(String(top), 0, Y(top) + 4); cx.fillText("0", 0, Y(0));
  SLOTS.forEach((m, i) => {
    const x = padL + i * bw;
    cx.fillStyle = "#e4e1da"; cx.fillRect(x + 1, Y(ev.total_normal_high[i]), bw - 2, Math.max(1, Y(ev.total_normal_low[i]) - Y(ev.total_normal_high[i])));
    cx.fillStyle = i === now ? "#b93e09" : "#f47b20"; cx.fillRect(x + bw * 0.22, Y(ev.total_actual[i]), bw * 0.56, Y(0) - Y(ev.total_actual[i]));
    cx.fillStyle = "#333"; cx.fillRect(x + 1, Y(ev.total_normal[i]) - 1, bw - 2, 2);
  });
  cx.fillStyle = C.red; cx.fillRect(padL + K0 * bw, 0, 1, h - padB);
  cx.fillStyle = "#8e8e93";
  [["−1 h", 0], ["delay", K0], ["+1 h", K0 + 4], ["+2 h", K0 + 8]].forEach(([t, i]) => cx.fillText(t, padL + i * bw + 2, h - 5));
}

DATA.events.forEach((e, i) => {
  const b = document.createElement("button"), color = DATA.lines[e.line]?.color ?? "#888";
  b.innerHTML = `<span class="badge" style="background:${color};color:${e.line === "1" ? "#000" : "#fff"}">${e.line}</span>`;
  b.append(`${short(e.from)} · ${day(e.when, { month: "short", year: "numeric" })}`);
  b.onclick = () => select(i);
  $("events").append(b);
});
$("play").onclick = () => { if (!playing && T >= SPAN) T = 0; setPlaying(!playing); };
$("slider").max = SPAN;
$("slider").oninput = () => { setPlaying(false); T = +$("slider").value; render(); };
$("more").addEventListener("toggle", () => $("more").open && drawChart());
addEventListener("resize", () => { if (ev) { frame(); render(); } });
select(0);
requestAnimationFrame(loop);
