// Splits page: one split (or advancement) in depth. Distribution, times over dates, top 10.
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
// An advancement is "adv:<id>" (e.g. adv:nether/find_fortress).
const ADV = "adv:";
const ADV_TABS = [["story", "Minecraft"], ["nether", "Nether"], ["end", "The End"],
                  ["adventure", "Adventure"], ["husbandry", "Husbandry"]];
let split = new URLSearchParams(location.search).get("split") || localStorage.getItem("splitsPage.split");
if (!SPLIT_KEYS.includes(split) && !split?.startsWith(ADV)) split = "nether";
const isAdv = () => split.startsWith(ADV);
const advId = () => split.slice(ADV.length);
let advMenuKey = null;  // how many advancements the dropdown was built with
// Where times are measured from: "start" (the in-game time when the split was reached), or
// an earlier split (the time since it, for runs that reached both). Like the split, it can
// come from the URL (?from=blind).
const START = "start";
let from = new URLSearchParams(location.search).get("from") || localStorage.getItem("splitsPage.from") || START;
let data = null;  // {summary, runs}
const fetchData = latestOnly(() => Promise.all([
  getJSON(`/api/summary?${windowQuery()}`),
  getJSON(`/api/runs?${windowQuery()}`),
]));

/** The splits times can be measured from for the chosen split: the ones before it (for an
 *  advancement, every split but the finish). */
function fromSplits() {
  const before = isAdv() ? SPLIT_KEYS.length - 1 : SPLIT_KEYS.indexOf(split);
  return PROGRESSION.slice(0, before);
}

/** The split times are measured from, or null for the start of the run. */
const fromSplit = () => fromSplits().find(([key]) => key === from) ?? null;

/** Runs with a time for the split, oldest first: its in-game time, or the time since the
 *  "from" split (only runs that reached both; negative for an advancement got before it). */
function timedRuns(runs) {
  const start = fromSplit()?.[0];
  return runs.map((r) => {
    const t = isAdv() ? r.advancements[advId()] ?? null : splitTime(r, split);
    if (!start) return { run: r, ms: t };
    const p = splitTime(r, start);
    return { run: r, ms: t != null && p != null ? t - p : null };
  }).filter((t) => t.ms != null);
}

function quantile(sorted, q) {
  const pos = (sorted.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

const advName = (id) => data?.runs.advancements.find((a) => a.id === id)?.name ?? id;
const splitName = () => isAdv() ? advName(advId()) : Object.fromEntries(PROGRESSION)[split];

/** The advancements any run has got, grouped by tab, for the dropdown's submenu. */
function advancementChoices() {
  if (!data) return [];
  const got = data.runs.advancements.filter((a) => data.runs.advancement_pbs[a.id]);
  return ADV_TABS.flatMap(([tab, heading]) => {
    const inTab = got.filter((a) => a.id.startsWith(`${tab}/`));
    return inTab.length ? [{ heading }, ...inTab.map((a) => [ADV + a.id, a.name, ADV + a.id])] : [];
  });
}

export const splitsPage = {
  id: "splits",
  usesWindow: () => true,
  init() {},

  filters() {
    // "From": the start of the run or a split before the chosen one (rebuilt when that changes).
    const fromBox = h("div", { class: "filter" });
    const buildFrom = () => fromBox.replaceChildren(
      h("span", { class: "filter-label", "aria-hidden": "true" }, "From"),
      iconSelect({
        options: [[START, "Beginning", "clock"], ...fromSplits().map(([value, text]) => [value, text, value])],
        value: fromSplit()?.[0] ?? START, ariaLabel: "Time measured from",
        onChange: (v) => {
          from = v;
          localStorage.setItem("splitsPage.from", from);
          if (data) $("window-note").textContent = draw();
        },
      }));
    buildFrom();
    const advs = advancementChoices();
    advMenuKey = advs.length;
    const options = PROGRESSION.map(([value, text]) => [value, text, value]);
    if (advs.length) options.push(["advancements", "Advancements", "advancement", advs]);
    return [h("div", { class: "filter" }, h("span", { class: "filter-label", "aria-hidden": "true" }, "Split"),
      iconSelect({
        options, value: split, ariaLabel: "Split",
        onChange: (v) => {
          split = v;
          localStorage.setItem("splitsPage.split", split);
          buildFrom();
          if (data) $("window-note").textContent = draw();
        },
      })), fromBox];
  },

  async load() {
    const result = await fetchData();
    if (!result) return null;
    data = { summary: result[0], runs: result[1] };
    // An advancement no run has got (or that doesn't exist): back to the nether.
    if (isAdv() && !data.runs.advancement_pbs[advId()]) split = "nether";
    // The advancements are known now: rebuild the dropdown with them.
    if (advancementChoices().length !== advMenuKey) $("page-filters").replaceChildren(...this.filters());
    return draw();
  },

  onResize() {
    if (data) draw();
  },
};

/** How a split reads in a sentence: "the nether", "structure 1". */
function splitInSentence(name) {
  return name.startsWith("Structure") ? name.toLowerCase() : `the ${name.toLowerCase()}`;
}

/** How the chosen split or advancement reads in a sentence. */
function inSentence(name) {
  return isAdv() ? `“${name}”` : splitInSentence(name);
}

function draw() {
  const name = splitName(), lower = inSentence(name);
  const timed = timedRuns(data.runs.runs);
  const sorted = timed.map((t) => t.ms).sort((a, b) => a - b);
  const adv = isAdv(), played = data.runs.runs.length;
  const got = adv ? data.runs.runs.filter((r) => r.advancements[advId()] != null).length : 0;
  const s = adv
    ? { count: got, rate: played ? got / played : null,
        avg_ms: sorted.length ? sorted.reduce((a, b) => a + b, 0) / sorted.length : null,
        median_ms: sorted.length ? quantile(sorted, 0.5) : null }
    : data.summary.stats.splits[split];
  const start = fromSplit(), segment = start != null;
  const prevName = segment ? start[1] : null;
  const pb = segment ? data.runs.from_pbs[start[0]]?.[split] : adv ? data.runs.advancement_pbs[advId()] : data.runs.pbs[split];
  const verb = adv ? "got" : "reached";

  $("splits-empty").hidden = timed.length > 0;
  $("splits-content").hidden = timed.length === 0;
  $("splits-empty").textContent = segment && s.count
    ? `No runs reached both ${splitInSentence(prevName)} and ${lower} in this time window.`
    : `No runs ${verb} ${lower} in this time window.`;
  const note = `${fmt.int(s.count)} of ${fmt.int(played)} runs ${verb} ${lower}`;
  if (!timed.length) return note;

  $("splits-title").replaceChildren(withIcon(split, name));
  $("splits-mode-note").textContent = !segment ? ""
    : adv ? `Time from ${splitInSentence(prevName)} to ${lower}, for runs that reached both (negative if it came first).`
    : `Time from ${splitInSentence(prevName)} to ${lower}, for runs that reached both.`;
  $("splits-mode-note").hidden = !$("splits-mode-note").textContent;
  $("splits-over-time-note").textContent = segment
    ? `Every run that reached both${adv ? "" : " splits"}, oldest to newest, with a moving average.`
    : `Every run that ${verb} this ${adv ? "advancement" : "split"}, oldest to newest, with a moving average.`;
  const whole = split === "nether" || adv ? "runs played" : "nether enters";
  const prevCount = segment ? data.summary.stats.splits[start[0]].count : null;
  const mean = sorted.reduce((a, b) => a + b, 0) / sorted.length;
  $("splits-tiles").replaceChildren(
    tile(adv ? "Got" : "Reached", fmt.int(s.count), segment && !adv
      ? `${fmt.pct(prevCount ? s.count / prevCount : null)} of ${prevName.toLowerCase()} runs`
        + (timed.length !== s.count ? ` · ${fmt.int(timed.length)} after ${prevName.toLowerCase()}` : "")
      : `${fmt.pct(s.rate)} of ${whole}`
        + (segment && timed.length !== s.count ? ` · ${fmt.int(timed.length)} also reached ${splitInSentence(prevName)}` : "")),
    tile("Average", fmt.timeTenths(segment ? mean : s.avg_ms)),
    tile("Median", fmt.timeTenths(segment ? quantile(sorted, 0.5) : s.median_ms)),
    tile("Best in window", fmt.time(sorted[0]), pb ? `all-time best ${fmt.time(pb.ms)}` : ""),
    tile("Middle 50%", sorted.length >= 4
      ? [quantile(sorted, 0.25), quantile(sorted, 0.75)].map(fmt.timeShort).join(sorted[0] < 0 ? " to " : "–") : "–",
      "half your times fall in here"),
  );

  const target = adv ? name : name.toLowerCase();
  const plain = segment ? `${prevName.toLowerCase()} → ${target}` : target;
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
