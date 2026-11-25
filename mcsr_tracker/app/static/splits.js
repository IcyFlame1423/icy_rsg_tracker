// Splits page: one split in depth. Distribution, times over dates, top 10.
import * as fmt from "./fmt.js";
import { columnChart, scatterChart, TIME_STEPS } from "./charts.js";
import { withIcon } from "./icons.js";
import { iconSelect } from "./select.js";
import { $, getJSON, h, latestOnly, PROGRESSION, splitTime, tile, windowQuery } from "./common.js";

const MOVING_AVERAGE = 10;  // runs
// Bastion and fortress come in either order, so this page uses the first and second
// structure entered instead: every run's structure 1 comes before its structure 2.
const SPLIT_KEYS = PROGRESSION.map(([key]) => key);
// The URL can pick the split (e.g. /?split=structure2#splits), like it can the window.
let split = new URLSearchParams(location.search).get("split") || localStorage.getItem("splitsPage.split");
if (!SPLIT_KEYS.includes(split)) split = "nether";
// "total": the in-game time when the split was reached. "segment": the time since the
// previous split (the nether has none, so it's the same either way).
// Like the split, it can come from the URL (?mode=segment).
let mode = (new URLSearchParams(location.search).get("mode") || localStorage.getItem("splitsPage.mode")) === "segment"
  ? "segment" : "total";
let data = null;  // {summary, runs}
const fetchData = latestOnly(() => Promise.all([
  getJSON(`/api/summary?${windowQuery()}`),
  getJSON(`/api/runs?${windowQuery()}`),
]));

/** The split before this one (null for the nether). */
function previousSplit() {
  const i = SPLIT_KEYS.indexOf(split);
  return i > 0 ? PROGRESSION[i - 1] : null;
}

const segmentMode = () => mode === "segment" && previousSplit() != null;

/** Runs with a time for the split, oldest first: its total time, or in segment mode the
 *  time since the previous split (only runs that reached both). */
function timedRuns(runs) {
  const prev = segmentMode() ? previousSplit()[0] : null;
  return runs.map((r) => {
    const t = splitTime(r, split);
    if (!prev) return { run: r, ms: t };
    const p = splitTime(r, prev);
    return { run: r, ms: t != null && p != null ? t - p : null };
  }).filter((t) => t.ms != null);
}

function quantile(sorted, q) {
  const pos = (sorted.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

const splitName = () => Object.fromEntries(PROGRESSION)[split];

export const splitsPage = {
  id: "splits",
  usesWindow: () => true,
  init() {},

  filters() {
    const buttons = [["total", "From beginning"], ["segment", "From previous split"]].map(([value, text]) =>
      h("button", { type: "button", "data-mode": value, "aria-pressed": String(mode === value),
                    onclick: () => {
                      mode = value;
                      localStorage.setItem("splitsPage.mode", mode);
                      buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === mode)));
                      if (data) $("window-note").textContent = draw();
                    } }, text));
    const toggle = h("div", { class: "segmented", role: "group", "aria-label": "Split times measured" }, buttons);
    return [h("div", { class: "filter" }, h("span", { class: "filter-label", "aria-hidden": "true" }, "Split"),
      iconSelect({
        options: PROGRESSION.map(([value, text]) => [value, text, value]), value: split, ariaLabel: "Split",
        onChange: (v) => {
          split = v;
          localStorage.setItem("splitsPage.split", split);
          if (data) $("window-note").textContent = draw();
        },
      })), toggle];
  },

  async load() {
    const result = await fetchData();
    if (!result) return null;
    data = { summary: result[0], runs: result[1] };
    return draw();
  },

  onResize() {
    if (data) draw();
  },
};

/** How a split reads in a sentence: "the nether", "structure 1". */
function inSentence(name) {
  return name.startsWith("Structure") ? name.toLowerCase() : `the ${name.toLowerCase()}`;
}

function draw() {
  const name = splitName(), lower = inSentence(name);
  const s = data.summary.stats.splits[split];
  const timed = timedRuns(data.runs.runs);
  const sorted = timed.map((t) => t.ms).sort((a, b) => a - b);
  const segment = segmentMode();
  const prevName = segment ? previousSplit()[1] : null;
  const pb = (segment ? data.runs.segment_pbs : data.runs.pbs)[split];

  $("splits-empty").hidden = timed.length > 0;
  $("splits-content").hidden = timed.length === 0;
  $("splits-empty").textContent = `No runs reached ${lower} in this time window.`;
  const note = `${fmt.int(s.count)} of ${fmt.int(data.runs.runs.length)} runs reached ${lower}`;
  if (!timed.length) return note;

  $("splits-title").replaceChildren(withIcon(split, name));
  $("splits-mode-note").textContent = segment
    ? `Time from ${inSentence(prevName)} to ${lower}, for runs that reached both.`
    : mode === "segment" ? "The first split, so its time is the same from the beginning." : "";
  $("splits-mode-note").hidden = !$("splits-mode-note").textContent;
  $("splits-over-time-note").textContent = segment
    ? "Every run that reached both splits, oldest to newest, with a moving average."
    : "Every run that reached this split, oldest to newest, with a moving average.";
  const whole = split === "nether" ? "runs played" : "nether enters";
  const prevCount = segment ? data.summary.stats.splits[previousSplit()[0]].count : null;
  const mean = sorted.reduce((a, b) => a + b, 0) / sorted.length;
  $("splits-tiles").replaceChildren(
    tile("Reached", fmt.int(s.count), segment
      ? `${fmt.pct(prevCount ? s.count / prevCount : null)} of ${prevName.toLowerCase()} runs`
        + (timed.length !== s.count ? ` · ${fmt.int(timed.length)} after ${prevName.toLowerCase()}` : "")
      : `${fmt.pct(s.rate)} of ${whole}`),
    tile("Average", fmt.timeTenths(segment ? mean : s.avg_ms)),
    tile("Median", fmt.timeTenths(segment ? quantile(sorted, 0.5) : s.median_ms)),
    tile("Best in window", fmt.time(sorted[0]), pb ? `all-time ${segment ? "best segment" : "PB"} ${fmt.time(pb.ms)}` : ""),
    tile("Middle 50%", sorted.length >= 4
      ? `${fmt.timeShort(quantile(sorted, 0.25))}–${fmt.timeShort(quantile(sorted, 0.75))}` : "–",
      "half your times fall in here"),
  );

  const plain = segment ? `${prevName.toLowerCase()} → ${name.toLowerCase()}` : name.toLowerCase();
  drawHistogram(sorted, plain);
  drawOverTime(timed, plain);
  drawTop(timed);
  return note;
}

function drawHistogram(sorted, plain) {
  const lo = sorted[0], hi = sorted.at(-1);
  // Bin width: the smallest round step that gives at most ~24 bins.
  const step = TIME_STEPS.find((s) => (hi - lo) / s <= 24) ?? TIME_STEPS.at(-1);
  const start = Math.floor(lo / step) * step;
  const bins = [];
  for (let from = start; from <= hi; from += step) {
    bins.push({ from, to: from + step, count: 0, label: fmt.timeShort(from),
                title: `${fmt.timeShort(from)} – ${fmt.timeShort(from + step)}` });
  }
  for (const ms of sorted) bins[Math.min(bins.length - 1, Math.floor((ms - start) / step))].count++;
  $("splits-hist-note").textContent = `How your ${plain} times are spread, in ${fmt.timeShort(step)} buckets.`;
  columnChart($("splits-histogram"), bins, { name: "runs" });
}

function drawOverTime(timed, plain) {
  // Moving average of the last N runs that reached the split.
  const line = timed.map((t, i) => {
    const recent = timed.slice(Math.max(0, i - MOVING_AVERAGE + 1), i + 1);
    return { x: i, y: recent.reduce((sum, w) => sum + w.ms, 0) / recent.length };
  });
  // Runs in order, evenly spaced (real dates would squash busy days and stretch quiet ones);
  // the axis is labelled where the date changes.
  const xTicks = [];
  timed.forEach((t, i) => {
    const day = fmt.day(t.run.date);
    if (!xTicks.length || xTicks.at(-1).label !== day) xTicks.push({ x: i, label: day });
  });
  scatterChart($("splits-over-time"), timed.map((t, i) => ({
    x: i,
    y: t.ms,
    emphasis: false,
    title: `${t.run.world_number == null ? t.run.world_name : `#${t.run.world_number}`} · ${fmt.dateTime(t.run.date)}`,
    rows: [{ value: fmt.time(t.ms), name: plain },
           { value: fmt.timeTenths(line[i].y), name: `average of last ${Math.min(i + 1, MOVING_AVERAGE)}` }],
  })), {
    name: `${plain} times over time`, xAxis: "index", xTicks, yTickFormat: fmt.timeShort, line,
    legend: [{ label: "Each run", key: "muted" }, { label: `Average of last ${MOVING_AVERAGE} runs`, key: "line" }],
  });
}

function drawTop(timed) {
  const top = [...timed].sort((a, b) => a.ms - b.ms).slice(0, 10);
  $("splits-top").tBodies[0].replaceChildren(...top.map((t, i) => h("tr", {},
    h("td", {}, h("a", { class: "button small", href: `#run/${encodeURIComponent(t.run.run_id)}`,
                         "aria-label": `View run ${i + 1}` }, "View")),
    h("td", { class: "num" }, String(i + 1)),
    h("td", { class: "num" }, fmt.time(t.ms)),
    h("td", {}, fmt.dateTime(t.run.date)),
    h("td", { class: "num" }, h("a", { href: `#sessions/${t.run.session_id}` }, `#${t.run.session_id}`)),
    h("td", { class: "num" }, t.run.world_number == null ? t.run.world_name : `#${t.run.world_number}`),
  )));
}
