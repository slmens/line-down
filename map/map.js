// Line Down pixel map. Draws DATA (from data.js, written by export.py) on a canvas: one map pixel = 100 m.
const [W, H] = DATA.size;
const SLOTS = DATA.slot_minutes;
const C = { bg: "#101218", street: "#1f232c", lake: "#12304f", bikeOff: "#5a6070", normal: "#d0d4dc",
            hot: [255, 210, 63], cold: "#4a7bd0", red: "#ff3b30", station: "#ffffff" };

// base layer: streets from bus/streetcar routes; lake = everything south of a column's last street pixel
const bits = Uint8Array.from(atob(DATA.streets), c => c.charCodeAt(0));
const street = i => (bits[i >> 3] >> (i & 7)) & 1;
const base = document.createElement("canvas");
base.width = W; base.height = H;
{
  const bx = base.getContext("2d"), img = bx.createImageData(W, H);
  const put = (i, hex) => { const v = parseInt(hex.slice(1), 16); img.data.set([v >> 16, (v >> 8) & 255, v & 255, 255], i * 4); };
  for (let x = 0; x < W; x++) {
    let last = -1;
    for (let y = 0; y < H; y++) if (street(y * W + x)) last = y;
    for (let y = 0; y < H; y++) put(y * W + x, street(y * W + x) ? C.street : y > last + 2 ? C.lake : C.bg);
  }
  bx.putImageData(img, 0, 0);
  for (const id of ["2", "4", "1"]) {   // Line 1 on top where they cross
    const l = DATA.lines[id];
    if (!l) continue;
    bx.fillStyle = l.color;
    l.points.slice(1).forEach(([x1, y1], i) => {   // solid 1-pixel steps, no anti-aliasing
      const [x0, y0] = l.points[i], n = Math.ceil(Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0)) * 2) || 1;
      for (let t = 0; t <= n; t++) bx.fillRect(Math.floor(x0 + (x1 - x0) * t / n), Math.floor(y0 + (y1 - y0) * t / n), 1, 1);
    });
  }
}

const map = document.getElementById("map"), mx = map.getContext("2d");
const chart = document.getElementById("chart"), cx = chart.getContext("2d");
const slider = document.getElementById("slider"), playBtn = document.getElementById("play");
const stationXY = Object.fromEntries(DATA.stations.map(s => [s.name, s.xy]));
let ev = null, slot = 0, timer = null, view = { x: 0, y: 0, w: W, h: H };

const fmtDay = iso => new Date(iso + ":00").toLocaleDateString("en-CA", { weekday: "long", day: "numeric", month: "short", year: "numeric" });
function clock(iso, plusMin) {
  const [h, m] = iso.slice(11, 16).split(":").map(Number), t = h * 60 + m + plusMin;
  const hh = Math.floor(t / 60) % 24, mm = t % 60;
  return `${(hh + 11) % 12 + 1}:${String(mm).padStart(2, "0")} ${hh < 12 ? "am" : "pm"}`;
}
const short = s => s.replace(/ Station$/, "");
const lineColor = id => DATA.lines[id]?.color ?? "#888";

function bikeColor(actual, normal) {
  const diff = actual - normal;
  if (actual === 0 && normal < 0.25) return C.bikeOff;
  if (diff >= 0.5) { const a = Math.min(1, 0.45 + diff / 3); return `rgb(${C.hot.map(v => Math.round(v * a)).join()})`; }
  if (diff <= -0.5) return C.cold;
  return C.normal;
}

function draw() {
  // fit the map canvas to its CSS width, whole pixels per map pixel
  const scale = Math.max(1, Math.floor(map.clientWidth / view.w));
  map.width = view.w * scale; map.height = view.h * scale;
  mx.imageSmoothingEnabled = false;
  mx.drawImage(base, view.x, view.y, view.w, view.h, 0, 0, map.width, map.height);
  const P = ([x, y]) => [Math.floor(x - view.x) * scale, Math.floor(y - view.y) * scale];
  const dot = (xy, color, size = 1) => { const [px, py] = P(xy); mx.fillStyle = color; mx.fillRect(px - (size - 1) / 2 * scale, py - (size - 1) / 2 * scale, size * scale, size * scale); };

  const near = ev ? new Map(ev.stations.map((id, i) => [String(id), i])) : new Map();
  for (const [id, b] of Object.entries(DATA.bikes)) {
    if (near.has(id)) continue;
    dot(b.xy, "#353a46");
  }
  if (ev) {
    const blink = slot >= 4 && Math.floor(Date.now() / 400) % 2;
    for (const [id, i] of near) dot(DATA.bikes[id].xy, bikeColor(ev.actual[i][slot], ev.normal[i][slot]));
    // 1 km ring around each stopped station
    mx.strokeStyle = "rgba(255,59,48,0.7)"; mx.lineWidth = Math.max(1, Math.round(scale / 2)); mx.setLineDash([scale, scale]);
    for (const s of ev.affected) { const [px, py] = P(stationXY[s]); mx.beginPath(); mx.arc(px + scale / 2, py + scale / 2, 10 * scale, 0, 7); mx.stroke(); }
    mx.setLineDash([]);
  }
  for (const s of DATA.stations) dot(s.xy, C.station);
  if (ev) for (const s of ev.affected) dot(stationXY[s], slot >= 4 && Math.floor(Date.now() / 400) % 2 ? "#7a1a14" : C.red, 2);

  // labels: affected stations first, then as many others as fit without overlapping; a few anchors citywide
  // (inside the 1 km ring only the stopped station is labelled, so labels never hide bike stations)
  const outside = n => ev.affected.every(a => Math.hypot(stationXY[n][0] - stationXY[a][0], stationXY[n][1] - stationXY[a][1]) > 12);
  const labels = ev ? [...ev.affected, ...DATA.stations.map(s => s.name).filter(outside)] : ["Union Station", "Bloor-Yonge Station", "Finch Station", "Kipling Station", "Kennedy Station", "Vaughan Metropolitan Centre Station", "Don Mills Station"];
  mx.font = `${Math.max(11, Math.min(16, Math.round(scale * 2)))}px ui-monospace, Menlo, monospace`;
  mx.textBaseline = "middle";
  const placed = [];
  for (const name of labels) {
    const xy = stationXY[name];
    if (!xy || xy[0] < view.x || xy[0] > view.x + view.w || xy[1] < view.y || xy[1] > view.y + view.h) continue;
    const [px, py] = P(xy), hot = ev?.affected.includes(name);
    const t = short(name), tw = mx.measureText(t).width;
    const box = [px + scale * 2, py - scale, tw + 6, scale * 2.6];
    if (placed.some(b => box[0] < b[0] + b[2] && b[0] < box[0] + box[2] && box[1] < b[1] + b[3] && b[1] < box[1] + box[3])) continue;
    placed.push(box);
    mx.fillStyle = "rgba(16,18,24,0.75)";
    mx.fillRect(px + scale * 2, py - scale, tw + 6, scale * 2.6);
    mx.fillStyle = hot ? C.red : "#d8d6cf";
    mx.fillText(t, px + scale * 2 + 3, py + scale * 0.3);
  }
  if (!ev || view.y + view.h > H - 20) {
    mx.fillStyle = "#4f78a6";
    mx.fillText("LAKE ONTARIO", (Math.min(W - 40, view.x + view.w * 0.5) - view.x) * scale, (H - 6 - view.y) * scale);
  }
  drawChart();
}

function drawChart() {
  const w = chart.width, h = chart.height, padL = 26, padB = 22, bw = (w - padL) / SLOTS.length;
  cx.fillStyle = C.bg; cx.fillRect(0, 0, w, h);
  if (!ev) return;
  const top = Math.max(...ev.total_actual, ...ev.total_normal_high, 4) * 1.15;
  const Y = v => (h - padB) - v / top * (h - padB - 6);
  cx.font = "11px ui-monospace, Menlo, monospace"; cx.fillStyle = "#8b8f9a";
  cx.fillText(String(Math.round(top / 1.15)), 2, Y(top / 1.15) + 4); cx.fillText("0", 2, Y(0));
  SLOTS.forEach((m, i) => {
    const x = padL + i * bw;
    cx.fillStyle = "#3c4252";   // normal-day range
    cx.fillRect(x + 1, Y(ev.total_normal_high[i]), bw - 2, Math.max(2, Y(ev.total_normal_low[i]) - Y(ev.total_normal_high[i])));
    cx.fillStyle = i === slot ? "#ffd23f" : i < slot ? "#b8962c" : "#4a4434";
    const bh = Math.round(Y(0) - Y(ev.total_actual[i]));
    cx.fillRect(x + bw * 0.25, Y(0) - bh, bw * 0.5, bh);
    cx.fillStyle = "#fff";
    cx.fillRect(x + 1, Math.round(Y(ev.total_normal[i])) - 1, bw - 2, 3);
  });
  const x0 = padL + 4 * bw;
  cx.fillStyle = C.red; cx.fillRect(x0 - 1, 0, 2, h - padB);
  cx.fillStyle = "#8b8f9a";
  cx.fillText("-1 h", padL, h - 6); cx.fillText("delay", x0 + 3, h - 6); cx.fillText("+3 h", w - 30, h - 6);
}

function describe() {
  if (!ev) return;
  const first = ev.total_actual.slice(4, 8).reduce((a, b) => a + b, 0), normal = ev.total_normal.slice(4, 8).reduce((a, b) => a + b, 0);
  const verdict = first > normal * 1.1 ? "more than" : first < normal * 0.9 ? "fewer than" : "about the same as";
  const where = ev.to ? `between ${short(ev.from)} and ${short(ev.to)}` : `at ${short(ev.from)}`;
  document.getElementById("caption").textContent =
    `${fmtDay(ev.when)}, ${clock(ev.when, 0)}. Line ${ev.line} was stopped ${where}, logged as a ${ev.min_delay}-minute delay` +
    `${ev.cause ? ` (${ev.cause.toLowerCase().replace(/\bttc\b/g, "TTC")})` : ""}. In the hour after, ${first} Bike Share trips started within 1 km: ` +
    `${verdict} a normal ${fmtDay(ev.when).split(",")[0]} at that time (${normal.toFixed(0)} on average over ${ev.normal_days} normal days).`;
  const m = SLOTS[slot], a = ev.total_actual[slot], n = ev.total_normal[slot];
  document.getElementById("clock").textContent = clock(ev.slot0, m);
  document.getElementById("now").textContent =
    `${m < 0 ? `${-m} min before` : `${m} min after`} the delay: ${a} trip${a === 1 ? "" : "s"} started within 1 km ` +
    `(normal day: ${n.toFixed(1)}, range ${ev.total_normal_low[slot]}-${ev.total_normal_high[slot]}).`;
}

function select(i) {
  ev = DATA.events[i];
  document.querySelectorAll(".events button").forEach((b, j) => b.setAttribute("aria-pressed", j === i));
  // zoom to the stopped stretch: about 7 km across, kept inside the map
  const pts = ev.affected.map(s => stationXY[s]);
  const cxm = pts.reduce((a, p) => a + p[0], 0) / pts.length, cym = pts.reduce((a, p) => a + p[1], 0) / pts.length;
  const vw = Math.max(100, Math.max(...pts.map(p => p[0])) - Math.min(...pts.map(p => p[0])) + 40), vh = Math.round(vw * 0.75);
  view = { x: Math.round(Math.min(W - vw, Math.max(0, cxm - vw / 2))), y: Math.round(Math.min(H - vh, Math.max(0, cym - vh / 2))), w: vw, h: vh };
  setSlot(0); play(true);
}

function setSlot(k) { slot = k; slider.value = k; describe(); draw(); }
function play(on) {
  clearInterval(timer); timer = null;
  if (on) timer = setInterval(() => slot < SLOTS.length - 1 ? setSlot(slot + 1) : play(false), 900);
  playBtn.textContent = on ? "❚❚" : "▶"; playBtn.setAttribute("aria-label", on ? "Pause" : "Play");
}

const list = document.getElementById("events");
DATA.events.forEach((e, i) => {
  const b = document.createElement("button");
  b.innerHTML = `<span class="badge" style="background:${lineColor(e.line)}">${e.line}</span>`;
  b.append(`${short(e.from)}${e.to ? " to " + short(e.to) : ""} · ${e.when.slice(0, 10)} · ${e.min_delay} min`);
  b.onclick = () => select(i);
  list.append(b);
});
slider.max = SLOTS.length - 1;
slider.oninput = () => { play(false); setSlot(+slider.value); };
playBtn.onclick = () => ev ? play(!timer && (slot < SLOTS.length - 1 || (setSlot(0), true))) : select(0);
addEventListener("resize", draw);
setInterval(() => ev && slot >= 4 && draw(), 400);   // blink the stopped station
document.getElementById("caption").textContent = "Pick a disruption to replay it. These are the longest subway delays since 2023 (weather left out), each with real Bike Share trips from 1 hour before to 3 hours after.";
draw();
