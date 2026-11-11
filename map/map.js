// Line Down pixel map. Draws DATA (from data.js, written by export.py); map units are 100 m.
// The scene is drawn small (1 art pixel = 2 device pixels) one colour at a time, each colour's edge
// pixels snapped fully on or off (no blur, no blended colours), then scaled up by a whole number
// at devicePixelRatio. Labels are crisp text on top.
const [W, H] = DATA.size;
const SLOTS = DATA.slot_minutes, K0 = SLOTS.indexOf(0);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const RAMP = ["--o0", "--o1", "--o2", "--o3"].map(css), RED = css("--red");
const LAKE = "#d7e6f0", INK = "#1d1d1f", BG = "#fbfaf7", RING = "#e58b84", HALO = "#f6d5d1", FAINT = "#dcd9d2";
let ART = 2;   // css pixels per art pixel; set in draw() so one art pixel is always 2 device pixels
const art = document.createElement("canvas"), g = art.getContext("2d");
const scratch = document.createElement("canvas"), sg = scratch.getContext("2d", { willReadFrequently: true });

// paint(ctx) draws shapes in css pixels with whatever fill/stroke it uses; they land on the art canvas in one colour
function layer(color, paint) {
  scratch.width = art.width; scratch.height = art.height;
  sg.setTransform(1 / ART, 0, 0, 1 / ART, 0, 0);
  sg.fillStyle = sg.strokeStyle = color; sg.lineJoin = sg.lineCap = "round";
  paint(sg);
  const d = sg.getImageData(0, 0, scratch.width, scratch.height), a = d.data;
  for (let i = 3; i < a.length; i += 4) a[i] = a[i] >= 110 ? 255 : 0;
  sg.putImageData(d, 0, 0);
  g.drawImage(scratch, 0, 0);
}

const map = document.getElementById("map"), mx = map.getContext("2d");
const chart = document.getElementById("chart"), cx = chart.getContext("2d");
const slider = document.getElementById("slider"), playBtn = document.getElementById("play"), tip = document.getElementById("tip");
const stationXY = Object.fromEntries(DATA.stations.map(s => [s.name, s.xy]));
const terminals = new Set(Object.values(DATA.lines).flatMap(l => l.ends));
let ev = null, slot = 0, timer = null, view = null, k = 1;

const short = s => s.replace(/ Station$/, "");
const sum = a => a.reduce((x, y) => x + y, 0);
const weekday = iso => new Date(iso + ":00").toLocaleDateString("en-CA", { weekday: "long" });
const dateLong = iso => new Date(iso + ":00").toLocaleDateString("en-CA", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
function clock(iso, plus) {
  const [h, m] = iso.slice(11, 16).split(":").map(Number), t = h * 60 + m + plus, hh = Math.floor(t / 60) % 24;
  return `${(hh + 11) % 12 + 1}:${String(t % 60).padStart(2, "0")} ${hh < 12 ? "am" : "pm"}`;
}

// canvas sized in CSS pixels, drawn at devicePixelRatio so everything stays sharp
function fit(canvas, ctx, cssH) {
  const r = devicePixelRatio || 1, w = canvas.clientWidth;
  canvas.style.height = cssH + "px"; canvas.width = Math.round(w * r); canvas.height = Math.round(cssH * r);
  ctx.setTransform(r, 0, 0, r, 0, 0);
  return w;
}
const P = ([x, y]) => [(x - view.x) * k, (y - view.y) * k];

function path(ctx, pts, T) { ctx.beginPath(); pts.forEach((p, i) => { const [x, y] = T(p); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); }
function lake(T) {   // shoreline, closed off far to the south
  const s = DATA.shore, pts = [[-50, s[0][1]], ...s, [W + 50, s[s.length - 1][1]], [W + 50, H + 200], [-50, H + 200]];
  return ctx => { path(ctx, pts, T); ctx.closePath(); ctx.fill(); };
}
function lines(T, width, clip) {
  for (const id of ["2", "4", "1"]) {
    const l = DATA.lines[id];
    if (l) layer(l.color, ctx => { clip?.(ctx); path(ctx, l.points, T); ctx.lineWidth = width; ctx.stroke(); });
  }
}
const dots = (list, r) => ctx => { for (const [x, y] of list) { ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill(); } };
function label(text, [x, y], { bold = false, color = INK } = {}) {
  mx.font = `${bold ? 600 : 500} 13px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif`;
  mx.lineWidth = 4; mx.strokeStyle = "rgba(251,250,247,.95)"; mx.lineJoin = "round";
  mx.strokeText(text, x + 9, y + 4); mx.fillStyle = color; mx.fillText(text, x + 9, y + 4);
}

function draw() {
  const w = fit(map, mx, Math.round(Math.min(map.clientWidth * 0.72, innerHeight * 0.7)));
  const h = map.height / (devicePixelRatio || 1);
  // view: about 6 km across (4 km on a phone), centred on the stopped station(s), same aspect as the canvas
  const pts = ev.affected.map(s => stationXY[s]);
  const c = [sum(pts.map(p => p[0])) / pts.length, sum(pts.map(p => p[1])) / pts.length];
  const vw = Math.max(60, Math.max(...pts.map(p => p[0])) - Math.min(...pts.map(p => p[0])) + 35) * (w < 500 ? 0.7 : 1);
  ART = 2 / (devicePixelRatio || 1);
  k = w / vw; view = { x: c[0] - vw / 2, y: c[1] - h / k / 2, w: vw, h: h / k };

  art.width = Math.ceil(w / ART); art.height = Math.ceil(h / ART);
  g.fillStyle = BG; g.fillRect(0, 0, art.width, art.height);
  layer(LAKE, lake(P));
  const near = new Map(ev.stations.map((id, i) => [String(id), i]));
  layer(FAINT, ctx => { for (const [id, b] of Object.entries(DATA.bikes)) if (!near.has(id)) { const [x, y] = P(b.xy); ctx.fillRect(x - 1, y - 1, 2, 2); } });
  lines(P, 6);
  const centres = ev.affected.map(s => P(stationXY[s]));
  layer(RING, ctx => { ctx.setLineDash([6, 6]); ctx.lineWidth = 2; for (const [x, y] of centres) { ctx.beginPath(); ctx.arc(x, y, 10 * k, 0, 7); ctx.stroke(); } });
  if (slot >= K0) layer(HALO, dots(centres, 14));
  // nearby Bike Share stations: one colour ramp, extra trips vs normal in this slot (white rim, then colour)
  const bikes = [...near].map(([id, i]) => [P(DATA.bikes[id].xy), ev.actual[i][slot] - ev.normal[i][slot]]);
  const small = w < 500, size = d => (d >= 0.5 ? 7 : 5) * (small ? 0.7 : 1);
  layer("#ffffff", ctx => bikes.forEach(([[x, y], d]) => { ctx.beginPath(); ctx.arc(x, y, size(d) + 1.5, 0, 7); ctx.fill(); }));
  RAMP.forEach((color, step) => layer(color, ctx => bikes.forEach(([[x, y], d]) => {
    if (Math.max(0, Math.min(3, Math.round(d))) === step) { ctx.beginPath(); ctx.arc(x, y, size(d), 0, 7); ctx.fill(); }
  })));
  // subway stations: dark rim, white centre; the stopped one red
  const stations = DATA.stations.map(s => P(s.xy));
  layer("#555555", dots(stations, 6));
  layer("#ffffff", dots(stations, 4));
  layer("#ffffff", dots(centres, 10));
  layer(RED, dots(centres, 8));
  minimap(w, h);
  mx.imageSmoothingEnabled = false;
  mx.drawImage(art, 0, 0, art.width * ART, art.height * ART);
  // labels: stopped station and line terminals in view; others on hover
  for (const s of DATA.stations) {
    const [x, y] = P(s.xy);
    if (ev.affected.includes(s.name)) label(short(s.name), [x, y], { bold: true, color: RED });
    else if (terminals.has(s.name) && x > 0 && x < w - 60 && y > 0 && y < h) label(short(s.name), [x, y]);
  }
}

function minimap(w, h) {   // whole city in a corner, with a box where we are
  const mw = Math.min(150, w * (w < 500 ? 0.22 : 0.3)), s = mw / W, mh = H * s, ox = w - mw - 10, oy = 10;
  const T = ([x, y]) => [ox + x * s, oy + y * s];
  const clip = ctx => { ctx.beginPath(); ctx.rect(ox, oy, mw, mh); ctx.clip(); };
  layer("#e2e0da", ctx => ctx.fillRect(ox - 2, oy - 2, mw + 4, mh + 4));
  layer("#ffffff", ctx => ctx.fillRect(ox, oy, mw, mh));
  layer(LAKE, ctx => { clip(ctx); lake(T)(ctx); });
  lines(T, 3, clip);
  layer(RED, ctx => { ctx.lineWidth = 2; ctx.strokeRect(ox + view.x * s, oy + view.y * s, view.w * s, view.h * s); });
}

function drawChart() {
  const w = fit(chart, cx, 140), h = 140, padL = 24, padB = 20, bw = (w - padL) / SLOTS.length;
  const top = Math.max(...ev.total_actual, ...ev.total_normal_high, 4);
  const Y = v => (h - padB) - v / top * (h - padB - 8);
  cx.clearRect(0, 0, w, h);
  cx.font = "11px -apple-system, Helvetica, Arial, sans-serif"; cx.fillStyle = "#8e8e93";
  cx.fillText(String(top), 0, Y(top) + 4); cx.fillText("0", 0, Y(0));
  SLOTS.forEach((m, i) => {
    const x = padL + i * bw;
    cx.fillStyle = "#e4e1da";
    cx.fillRect(x + 1, Y(ev.total_normal_high[i]), bw - 2, Math.max(1, Y(ev.total_normal_low[i]) - Y(ev.total_normal_high[i])));
    cx.fillStyle = i === slot ? RAMP[3] : i < slot ? RAMP[2] : "#f6c9a6";
    cx.fillRect(x + bw * 0.22, Y(ev.total_actual[i]), bw * 0.56, Y(0) - Y(ev.total_actual[i]));
  });
  cx.beginPath(); SLOTS.forEach((m, i) => { const x = padL + i * bw; cx.moveTo(x + 1, Y(ev.total_normal[i])); cx.lineTo(x + bw - 1, Y(ev.total_normal[i])); });
  cx.strokeStyle = "#333"; cx.lineWidth = 2; cx.stroke();
  const xd = padL + K0 * bw;
  cx.fillStyle = RED; cx.fillRect(xd - 0.5, 0, 1, h - padB);
  cx.fillStyle = "#8e8e93";
  [["−1 h", 0], ["delay", K0], ["+1 h", K0 + 4], ["+2 h", K0 + 8]].forEach(([t, i]) => cx.fillText(t, padL + i * bw + 2, h - 5));
}

function describe() {
  const first = sum(ev.total_actual.slice(K0, K0 + 4)), normal = Math.round(sum(ev.total_normal.slice(K0, K0 + 4)));
  document.getElementById("headline").innerHTML =
    `<b>${first}</b> bike trips started within 1 km in the hour after, vs <b style="color:inherit">${normal}</b> on a normal ${weekday(ev.when)}`;
  const where = ev.to ? `between ${short(ev.from)} and ${short(ev.to)}` : `at ${short(ev.from)}`;
  const cause = ev.cause ? `: ${ev.cause.toLowerCase().replace(/\bttc\b/g, "TTC")}` : "";
  document.getElementById("sub").textContent =
    `Line ${ev.line} stopped ${where}, ${dateLong(ev.when)}, ${clock(ev.when, 0)}. Logged as a ${ev.min_delay}-minute delay${cause}.`;
  const m = SLOTS[slot], a = ev.total_actual[slot], n = ev.total_normal[slot];
  const when = m < 0 ? `${-m} min before the delay` : m === 0 ? "the first 15 min of the delay" : `${m} min after the delay`;
  document.getElementById("now").innerHTML =
    `<b>${clock(ev.slot0, m)}</b> · ${when}<br>${a} trip${a === 1 ? "" : "s"} within 1 km; a normal day has ${n.toFixed(1)} (range ${ev.total_normal_low[slot]}-${ev.total_normal_high[slot]})`;
}

function render() { describe(); draw(); drawChart(); }
function setSlot(i) { slot = i; slider.value = i; render(); }
function play(on) {
  clearInterval(timer); timer = null;
  if (on) timer = setInterval(() => slot < SLOTS.length - 1 ? setSlot(slot + 1) : play(false), 1000);
  playBtn.textContent = on ? "❚❚" : "▶"; playBtn.setAttribute("aria-label", on ? "Pause" : "Play");
}
function select(i) {
  ev = DATA.events[i];
  document.querySelectorAll(".events button").forEach((b, j) => b.setAttribute("aria-pressed", j === i));
  setSlot(0); play(true);
}

// hover: name of the nearest subway or Bike Share station
map.addEventListener("mousemove", e => {
  const r = map.getBoundingClientRect(), mxp = e.clientX - r.left, myp = e.clientY - r.top;
  let best = null, bd = 12;
  for (const s of DATA.stations) { const [x, y] = P(s.xy), d = Math.hypot(x - mxp, y - myp); if (d < bd) { bd = d; best = short(s.name); } }
  ev.stations.forEach((id, i) => {
    const [x, y] = P(DATA.bikes[id].xy), d = Math.hypot(x - mxp, y - myp);
    if (d < bd) { bd = d; best = `${DATA.bikes[id].name}: ${ev.actual[i][slot]} trip${ev.actual[i][slot] === 1 ? "" : "s"} (normal ${ev.normal[i][slot]})`; }
  });
  tip.style.display = best ? "block" : "none";
  if (best) { tip.textContent = best; tip.style.left = Math.min(mxp + 12, r.width - tip.offsetWidth - 4) + "px"; tip.style.top = (myp + 12) + "px"; }
});
map.addEventListener("mouseleave", () => { tip.style.display = "none"; });

const list = document.getElementById("events");
DATA.events.forEach((e, i) => {
  const b = document.createElement("button"), color = DATA.lines[e.line]?.color ?? "#888";
  b.innerHTML = `<span class="badge" style="background:${color};color:${e.line === "1" ? "#000" : "#fff"}">${e.line}</span>`;
  b.append(short(e.from) + (e.to ? " to " + short(e.to) : ""));
  const small = document.createElement("small"); small.textContent = new Date(e.when + ":00").toLocaleDateString("en-CA", { month: "short", year: "numeric" });
  b.append(small); b.onclick = () => select(i); list.append(b);
});
slider.max = SLOTS.length - 1;
slider.oninput = () => { play(false); setSlot(+slider.value); };
playBtn.onclick = () => play(!timer && (slot < SLOTS.length - 1 || (setSlot(0), true)));
addEventListener("resize", () => ev && render());
select(0);
