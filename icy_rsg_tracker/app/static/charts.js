// Small hand-built SVG charts. Specs: 2px lines, >=8px dots with a 2px surface ring,
// hairline solid grid, crosshair + tooltip on hover/keyboard, and a table view so no
// value is only reachable by hovering.

const SVG = "http://www.w3.org/2000/svg";

function el(tag, attrs = {}, parent) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

// ---- Tooltip (one shared element) ----

const tooltip = () => document.getElementById("tooltip");

/** rows: [{value, name}]; text only (textContent), never HTML. */
export function showTooltip(clientX, clientY, title, rows) {
  const tip = tooltip();
  tip.replaceChildren();
  const t = document.createElement("div");
  t.className = "tt-title";
  t.textContent = title;
  tip.appendChild(t);
  for (const r of rows) {
    const row = document.createElement("div");
    row.className = "tt-row";
    const key = document.createElement("span");
    key.className = "tt-key";
    const value = document.createElement("span");
    value.className = "tt-value";
    value.textContent = r.value;
    const name = document.createElement("span");
    name.className = "tt-name";
    name.textContent = r.name;
    row.append(key, value, name);
    tip.appendChild(row);
  }
  tip.hidden = false;
  const { width, height } = tip.getBoundingClientRect();
  let x = clientX + 14, y = clientY - height - 10;
  if (x + width > window.innerWidth - 8) x = clientX - width - 14;
  if (y < 8) y = clientY + 16;
  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
}

export function hideTooltip() {
  tooltip().hidden = true;
}

// ---- Scales ----

/** Round tick values covering [lo, hi]. steps: allowed step sizes (ascending). */
function ticks(lo, hi, target, steps) {
  const span = Math.max(hi - lo, 1e-9);
  let step = steps ? steps.find((s) => span / s <= target) ?? steps.at(-1) : null;
  if (!step) {
    const raw = span / target;
    const mag = 10 ** Math.floor(Math.log10(raw));
    step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
  }
  const start = Math.floor(lo / step) * step;
  const end = Math.ceil(hi / step) * step;
  const out = [];
  for (let v = start; v <= end + step / 2; v += step) out.push(+v.toFixed(10));
  return out;
}

export const TIME_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800].map((s) => s * 1000);

// ---- Line chart ----

/**
 * points: [{label, title, y}]  (y may be null: a gap; label: x tick text)
 * opts: {name, format(y), tickFormat(y), zero (start y at 0), steps (tick steps), height,
 *        connectGaps (draw straight across points with no value instead of breaking the line),
 *        missing (tooltip text for a point with no value)}
 */
export function lineChart(container, points, opts) {
  container.replaceChildren();
  const valid = points.filter((p) => p.y != null);
  if (valid.length < 2) {
    const msg = document.createElement("div");
    msg.className = "chart-empty";
    msg.textContent = valid.length ? "Needs at least 2 sessions to show a trend." : "No data in this window.";
    container.appendChild(msg);
    return;
  }

  const width = Math.max(container.clientWidth, 280);
  const height = opts.height ?? 220;
  const ys = valid.map((p) => p.y);
  let lo = opts.zero ? 0 : Math.min(...ys), hi = Math.max(...ys);
  const yt = ticks(lo, hi, 4, opts.steps);
  lo = yt[0]; hi = yt.at(-1);

  const tickText = yt.map((v) => opts.tickFormat(v));
  const left = 10 + Math.max(...tickText.map((t) => t.length)) * 6.5;
  const m = { top: 10, right: 60, bottom: 26, left };
  const pw = width - m.left - m.right, ph = height - m.top - m.bottom;
  const x = (i) => m.left + (points.length === 1 ? pw / 2 : (i / (points.length - 1)) * pw);
  const y = (v) => m.top + ph - ((v - lo) / (hi - lo || 1)) * ph;

  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, width, height, tabindex: 0,
                          role: "img", "aria-label": `${opts.name}: line chart. Use arrow keys to read values.` }, container);

  yt.forEach((v, i) => {
    el("line", { class: i === 0 ? "baseline" : "gridline", x1: m.left, x2: m.left + pw, y1: y(v), y2: y(v) }, svg);
    el("text", { class: "tick", x: m.left - 8, y: y(v) + 4, "text-anchor": "end" }, svg).textContent = tickText[i];
  });

  // X labels: thin out so they don't collide (~70px each).
  const every = Math.max(1, Math.ceil(points.length / Math.max(1, Math.floor(pw / 70))));
  points.forEach((p, i) => {
    if (i % every !== 0 && i !== points.length - 1) return;
    if (i !== points.length - 1 && points.length - 1 - i < every) return; // keep the last one clear
    el("text", { class: "tick", x: x(i), y: height - 6, "text-anchor": "middle" }, svg).textContent = p.label;
  });

  // Line: broken at gaps, or joined straight across them with connectGaps.
  let d = "", pen = false;
  points.forEach((p, i) => {
    if (p.y == null) { if (!opts.connectGaps) pen = false; return; }
    d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(p.y).toFixed(1)}`;
    pen = true;
  });
  el("path", { class: "series-line", d }, svg);

  // Dots mark real values, so joined-up gaps stay visible as "no dot here".
  if (points.length <= 40 || opts.connectGaps) {
    points.forEach((p, i) => { if (p.y != null) el("circle", { class: "dot", cx: x(i), cy: y(p.y), r: 4 }, svg); });
  }

  // Direct label: the latest value only.
  const lastIdx = points.map((p) => p.y != null).lastIndexOf(true);
  el("text", { class: "end-label", x: x(lastIdx) + 10, y: y(points[lastIdx].y) + 4 }, svg).textContent =
    opts.format(points[lastIdx].y);

  // Hover / keyboard layer: crosshair snaps to the nearest point.
  const cross = el("line", { class: "crosshair", y1: m.top, y2: m.top + ph, visibility: "hidden" }, svg);
  const focusDot = el("circle", { class: "dot", r: 5, visibility: "hidden" }, svg);
  const hit = el("rect", { x: m.left - 10, y: m.top, width: pw + 20, height: ph, fill: "transparent" }, svg);
  let current = -1;

  const show = (i, clientX, clientY) => {
    current = i;
    const p = points[i];
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i));
    cross.setAttribute("visibility", "visible");
    if (p.y != null) {
      focusDot.setAttribute("cx", x(i)); focusDot.setAttribute("cy", y(p.y));
      focusDot.setAttribute("visibility", "visible");
    } else focusDot.setAttribute("visibility", "hidden");
    if (clientX == null) {
      const box = svg.getBoundingClientRect();
      const scale = box.width / width;
      clientX = box.left + x(i) * scale;
      clientY = box.top + (p.y != null ? y(p.y) : m.top) * scale;
    }
    showTooltip(clientX, clientY, p.title,
      [p.y == null ? { value: "–", name: opts.missing ?? opts.name } : { value: opts.format(p.y), name: opts.name }]);
  };
  const hide = () => {
    current = -1;
    cross.setAttribute("visibility", "hidden");
    focusDot.setAttribute("visibility", "hidden");
    hideTooltip();
  };
  hit.addEventListener("pointermove", (e) => {
    const box = svg.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * width;
    const i = Math.round(((px - m.left) / pw) * (points.length - 1));
    show(Math.min(points.length - 1, Math.max(0, i)), e.clientX, e.clientY);
  });
  hit.addEventListener("pointerleave", hide);
  svg.addEventListener("blur", hide);
  svg.addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    let i = current < 0 ? points.length - 1 : current;
    if (e.key === "ArrowLeft") i = Math.max(0, i - 1);
    if (e.key === "ArrowRight") i = Math.min(points.length - 1, i + 1);
    if (e.key === "Home") i = 0;
    if (e.key === "End") i = points.length - 1;
    show(i);
  });

  // Table view.
  const details = document.createElement("details");
  details.className = "table-view";
  const summary = document.createElement("summary");
  summary.textContent = "Show as table";
  const table = document.createElement("table");
  table.className = "data-table";
  const head = table.createTHead().insertRow();
  for (const [text, cls] of [["Session", ""], [opts.name, "num"]]) {
    const th = document.createElement("th");
    th.textContent = text;
    th.className = cls;
    head.appendChild(th);
  }
  const body = table.createTBody();
  for (const p of [...points].reverse()) {
    const r = body.insertRow();
    r.insertCell().textContent = p.title;
    const c = r.insertCell();
    c.className = "num";
    c.textContent = p.y == null ? "–" : opts.format(p.y);
  }
  details.append(summary, table);
  container.appendChild(details);
}

// ---- Scatter: a session's runs over time ----

/**
 * points: [{x: epoch ms, y: ms, emphasis: bool, title, rows: [{value, name}]}]
 * opts: {name, yTickFormat, height, empty (message),
 *        legend: [{label, key: "emphasis" | "muted" | "line"}],
 *        xAxis: "time" (time of day, default) | "date" | "index" (x is a position; label with xTicks),
 *        xTicks: [{x, label}] for xAxis "index" (thinned so labels don't collide),
 *        line: [{x, y}] drawn over the points (e.g. a moving average)}
 * Emphasis points are drawn in the series colour on top; the rest are muted context.
 */
export function scatterChart(container, points, opts) {
  container.replaceChildren();
  if (!points.length) {
    const msg = document.createElement("div");
    msg.className = "chart-empty";
    msg.textContent = opts.empty ?? "No runs in this session.";
    container.appendChild(msg);
    return;
  }

  // Legend: two kinds of mark -> always a legend.
  const legend = document.createElement("div");
  legend.className = "legend";
  for (const { label, key } of opts.legend) {
    const item = document.createElement("span");
    item.className = "legend-item";
    const mark = document.createElement("span");
    mark.className = key === "line" ? "legend-line" : `legend-dot key-${key}`;
    item.append(mark, document.createTextNode(label));
    legend.appendChild(item);
  }
  container.appendChild(legend);

  const width = Math.max(container.clientWidth, 280);
  const height = opts.height ?? 260;
  const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
  let x0 = Math.min(...xs), x1 = Math.max(...xs);
  if (opts.xAxis === "index") { x0 -= 0.5; x1 += 0.5; }
  else if (x1 - x0 < 60_000) { x0 -= 30_000; x1 += 30_000; }
  // From 0, or below it when there are negative times (an advancement before the split).
  const yt = ticks(Math.min(0, ...ys), Math.max(...ys, ...(opts.line ?? []).map((p) => p.y), 1000), 4, TIME_STEPS);
  const yMin = yt[0], yMax = yt.at(-1);
  const tickText = yt.map((v) => opts.yTickFormat(v));
  const m = { top: 10, right: 16, bottom: 26, left: 10 + Math.max(...tickText.map((t) => t.length)) * 6.5 };
  const pw = width - m.left - m.right, ph = height - m.top - m.bottom;
  const x = (v) => m.left + ((v - x0) / (x1 - x0)) * pw;
  const y = (v) => m.top + ph - ((v - yMin) / (yMax - yMin)) * ph;

  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, width, height, tabindex: 0, role: "img",
                          "aria-label": `${opts.name}. Use arrow keys to step through runs.` }, container);
  yt.forEach((v, i) => {
    el("line", { class: v === 0 ? "baseline" : "gridline", x1: m.left, x2: m.left + pw, y1: y(v), y2: y(v) }, svg);
    el("text", { class: "tick", x: m.left - 8, y: y(v) + 4, "text-anchor": "end" }, svg).textContent = tickText[i];
  });
  const span = x1 - x0;
  if (opts.xAxis === "index") {
    let lastX = -Infinity;
    for (const t of opts.xTicks ?? []) {
      if (x(t.x) - lastX < 64) continue;  // keep labels apart
      lastX = x(t.x);
      el("text", { class: "tick", x: x(t.x), y: height - 6, "text-anchor": "middle" }, svg).textContent = t.label;
    }
  } else if (opts.xAxis === "date") {
    // Day ticks every 1/2/7/14/30 days, at midnight.
    const stepDays = [1, 2, 7, 14, 30, 60].find((d) => span / (d * 864e5) <= Math.max(2, pw / 80)) ?? 60;
    const first = new Date(x0); first.setHours(24, 0, 0, 0);
    for (let t = first.getTime(); t <= x1; t += stepDays * 864e5) {
      el("text", { class: "tick", x: x(t), y: height - 6, "text-anchor": "middle" }, svg).textContent =
        new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric" });
    }
  } else {
    // Time-of-day ticks on round 5/10/15/30/60-minute marks.
    const stepMin = [5, 10, 15, 30, 60, 120, 240].find((s) => span / (s * 60_000) <= Math.max(2, pw / 90)) ?? 240;
    const first = new Date(x0); first.setSeconds(0, 0);
    first.setMinutes(Math.ceil(first.getMinutes() / stepMin) * stepMin);
    for (let t = first.getTime(); t <= x1; t += stepMin * 60_000) {
      el("text", { class: "tick", x: x(t), y: height - 6, "text-anchor": "middle" }, svg).textContent =
        new Date(t).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    }
  }

  // Muted context first, emphasis on top.
  const order = points.map((p, i) => i).sort((a, b) => points[a].emphasis - points[b].emphasis);
  for (const i of order) {
    const p = points[i];
    el("circle", { class: p.emphasis ? "dot" : "dot-muted", cx: x(p.x), cy: y(p.y), r: p.emphasis ? 4.5 : 3 }, svg);
  }

  if (opts.line?.length > 1) {
    const d = opts.line.map((p, i) => `${i ? "L" : "M"}${x(p.x).toFixed(1)},${y(p.y).toFixed(1)}`).join("");
    el("path", { class: "series-line", d }, svg);
  }

  const ring = el("circle", { class: "focus-ring", r: 7, visibility: "hidden" }, svg);
  const hit = el("rect", { x: m.left - 10, y: m.top - 10, width: pw + 20, height: ph + 20, fill: "transparent" }, svg);
  const byTime = points.map((p, i) => i).sort((a, b) => points[a].x - points[b].x);
  let current = -1;

  const show = (i, clientX, clientY) => {
    current = i;
    const p = points[i];
    ring.setAttribute("cx", x(p.x)); ring.setAttribute("cy", y(p.y));
    ring.setAttribute("visibility", "visible");
    if (clientX == null) {
      const box = svg.getBoundingClientRect(), scale = box.width / width;
      clientX = box.left + x(p.x) * scale; clientY = box.top + y(p.y) * scale;
    }
    showTooltip(clientX, clientY, p.title, p.rows);
  };
  const hide = () => { current = -1; ring.setAttribute("visibility", "hidden"); hideTooltip(); };
  // Nearest point, so the pointer only has to be closest, not dead-centre.
  hit.addEventListener("pointermove", (e) => {
    const box = svg.getBoundingClientRect(), scale = width / box.width;
    const px = (e.clientX - box.left) * scale, py = (e.clientY - box.top) * scale;
    let best = -1, bestD = Infinity;
    points.forEach((p, i) => {
      const d = (x(p.x) - px) ** 2 + (y(p.y) - py) ** 2 - (p.emphasis ? 40 : 0);  // prefer emphasis on ties
      if (d < bestD) { bestD = d; best = i; }
    });
    if (bestD < 40 ** 2) show(best, e.clientX, e.clientY); else hide();
  });
  hit.addEventListener("pointerleave", hide);
  svg.addEventListener("blur", hide);
  svg.addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    let k = current < 0 ? byTime.length - 1 : byTime.indexOf(current);
    if (e.key === "ArrowLeft") k = Math.max(0, k - 1);
    if (e.key === "ArrowRight") k = Math.min(byTime.length - 1, k + 1);
    if (e.key === "Home") k = 0;
    if (e.key === "End") k = byTime.length - 1;
    show(byTime[k]);
  });
}

// ---- Columns: a histogram ----

/**
 * bins: [{label (axis text), title (tooltip title), count}]
 * opts: {name ("runs"), height}
 */
export function columnChart(container, bins, opts) {
  container.replaceChildren();
  if (!bins.length) {
    const msg = document.createElement("div");
    msg.className = "chart-empty";
    msg.textContent = "No runs reached this split in this window.";
    container.appendChild(msg);
    return;
  }
  const width = Math.max(container.clientWidth, 280);
  const height = opts.height ?? 220;
  const maxCount = Math.max(...bins.map((b) => b.count));
  const yt = ticks(0, Math.max(maxCount, 1), 4).filter((v) => Number.isInteger(v));
  const yMax = yt.at(-1);
  const m = { top: 10, right: 10, bottom: 26, left: 12 + String(yMax).length * 7 };
  const pw = width - m.left - m.right, ph = height - m.top - m.bottom;
  const band = pw / bins.length;
  const barW = Math.max(1, Math.min(24, band - 2));  // thin bars, 2px surface gap between neighbours
  const y = (v) => m.top + ph - (v / yMax) * ph;

  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, width, height, role: "img",
                          "aria-label": `${opts.name}: histogram` }, container);
  yt.forEach((v, i) => {
    el("line", { class: i === 0 ? "baseline" : "gridline", x1: m.left, x2: m.left + pw, y1: y(v), y2: y(v) }, svg);
    el("text", { class: "tick", x: m.left - 8, y: y(v) + 4, "text-anchor": "end" }, svg).textContent = String(v);
  });
  const every = Math.max(1, Math.ceil(bins.length / Math.max(1, Math.floor(pw / 56))));
  bins.forEach((b, i) => {
    const cx = m.left + band * i + band / 2;
    if (i % every === 0) {
      el("text", { class: "tick", x: m.left + band * i, y: height - 6, "text-anchor": "middle" }, svg).textContent = b.label;
    }
    if (b.count) {
      // Rounded 4px data end, square at the baseline.
      const top = y(b.count), r = Math.min(4, m.top + ph - top, barW / 2), x0 = cx - barW / 2;
      el("path", { class: "bar", d: `M${x0},${m.top + ph}V${top + r}Q${x0},${top} ${x0 + r},${top}` +
        `H${x0 + barW - r}Q${x0 + barW},${top} ${x0 + barW},${top + r}V${m.top + ph}Z` }, svg);
    }
    // Hit target: the whole band, taller than the bar.
    const hit = el("rect", { x: m.left + band * i, y: m.top, width: band, height: ph, fill: "transparent",
                             tabindex: 0, class: "bar-hit", "aria-label": `${b.title}: ${b.count} ${opts.name}` }, svg);
    const tip = (px, py) => showTooltip(px, py, b.title, [{ value: String(b.count), name: opts.name }]);
    hit.addEventListener("pointermove", (e) => tip(e.clientX, e.clientY));
    hit.addEventListener("pointerleave", hideTooltip);
    hit.addEventListener("focus", () => { const r = hit.getBoundingClientRect(); tip(r.left + r.width / 2, r.top + 20); });
    hit.addEventListener("blur", hideTooltip);
  });

  // Table view.
  const details = document.createElement("details");
  details.className = "table-view";
  const summary = document.createElement("summary");
  summary.textContent = "Show as table";
  const table = document.createElement("table");
  table.className = "data-table";
  const head = table.createTHead().insertRow();
  for (const [text, cls] of [["Time", ""], ["Runs", "num"]]) {
    const th = document.createElement("th"); th.textContent = text; th.className = cls; head.appendChild(th);
  }
  const body = table.createTBody();
  for (const b of bins) {
    const r = body.insertRow();
    r.insertCell().textContent = b.title;
    const c = r.insertCell(); c.className = "num"; c.textContent = String(b.count);
  }
  details.append(summary, table);
  container.appendChild(details);
}
