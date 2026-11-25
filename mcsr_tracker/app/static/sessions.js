// Sessions page: statistics over every session, then a table of the sessions in the time
// window; #sessions/<id> shows one session in detail.
import * as fmt from "./fmt.js";
import { lineChart, scatterChart, TIME_STEPS } from "./charts.js";
import { $, getJSON, h, latestOnly, plural, PROGRESSION, SPLITS, tile, windowQuery } from "./common.js";
import { createTable } from "./table.js";
import { createRunsTable } from "./runs-table.js";

let listTable = null, runsTable = null;
let detail = null;  // {summary, runs} of the open session, for redraws
// The statistics above the filter row have their own period (not the shared time window).
const PERIODS = { "7d": "the last 7 days", "30d": "the last 30 days", "1y": "the last year", all: "all time" };
let period = localStorage.getItem("sessionStatsPeriod");
if (!(period in PERIODS)) period = "all";
let allSessions = null;  // sessions in the period (oldest first), for the statistics
const fetchList = latestOnly(() => getJSON(`/api/sessions?${windowQuery()}`));
const fetchStats = latestOnly(() => getJSON(`/api/summary?${windowQuery({ window: period })}`));

// A short session's rate is mostly noise, so "best nethers per hour" needs this much play.
const MIN_RATE_SECONDS = 30 * 60;
// The left trend chart: what to plot for each session.
const METRICS = [
  { id: "nph", label: "Nethers per hour", value: (s) => s.nethers_per_hour, format: (v) => fmt.num(v, 2),
    tick: (v) => fmt.num(v, v % 1 ? 1 : 0) },
  { id: "nethers", label: "Nethers", value: (s) => s.splits.nether.count, format: fmt.int, tick: fmt.int },
  { id: "runs", label: "Runs played", value: (s) => s.runs_played, format: fmt.int, tick: fmt.int },
  { id: "rpn", label: "Resets per nether", value: (s) => s.resets_per_nether, format: (v) => fmt.num(v, 1),
    tick: (v) => fmt.num(v, 0), missing: "no nethers this session" },
  { id: "length", label: "Session length", value: (s) => s.time_span_s / 3600, format: (v) => fmt.duration(v * 3600),
    tick: (v) => `${fmt.num(v, v % 1 ? 1 : 0)}h` },
];
const trend = {
  metric: localStorage.getItem("sessionMetric") || "nph",
  split: localStorage.getItem("trendSplit") || "nether",
  // "total": time the split was reached; "segment": time since the previous split.
  mode: localStorage.getItem("trendMode") === "segment" ? "segment" : "total",
};
if (!METRICS.some((m) => m.id === trend.metric)) trend.metric = "nph";
if (!PROGRESSION.some(([k]) => k === trend.split)) trend.split = "nether";
const fetchDetail = latestOnly((id) => Promise.all([
  getJSON(`/api/summary?${windowQuery({ window: "session", session: id })}`),
  getJSON(`/api/runs?${windowQuery({ window: "session", session: id })}`),
]));

const timeRange = (s) => `${fmt.clock(s.start)} – ${fmt.clock(s.end)}`;

const LIST_COLUMNS = [
  { id: "session", label: "Session", num: true, value: (s) => s.session_id,
    cell: (s) => h("a", { href: `#sessions/${s.session_id}` }, `#${s.session_id}`) },
  { id: "date", label: "Date", value: (s) => s.start, cell: (s) => fmt.day(s.start) },
  { id: "time", label: "Time", value: (s) => s.start, cell: timeRange },
  { id: "length", label: "Length", num: true, value: (s) => s.time_span_s, cell: (s) => fmt.duration(s.time_span_s) },
  { id: "runs", label: "Runs", num: true, value: (s) => s.runs_played, cell: (s) => fmt.int(s.runs_played) },
  { id: "wall", label: "Wall resets", num: true, value: (s) => s.wall_resets, cell: (s) => fmt.int(s.wall_resets) },
  { id: "nethers", label: "Nethers", num: true, value: (s) => s.splits.nether.count, cell: (s) => fmt.int(s.splits.nether.count) },
  { id: "nph", label: "Nethers/h", num: true, value: (s) => s.nethers_per_hour, cell: (s) => fmt.num(s.nethers_per_hour, 2) },
  { id: "avg_nether", label: "Avg nether", num: true, value: (s) => s.splits.nether.avg_ms,
    cell: (s) => fmt.timeTenths(s.splits.nether.avg_ms) },
  { id: "best_nether", label: "Best nether", num: true, value: (s) => s.splits.nether.best_ms,
    cell: (s) => fmt.time(s.splits.nether.best_ms) },
  { id: "finished", label: "Completions", num: true, value: (s) => s.finished, cell: (s) => fmt.int(s.finished) },
];

export const sessionsPage = {
  id: "sessions",
  // A single session is picked explicitly, so the time window doesn't apply to it.
  usesWindow: (route) => !route.sessionId,
  showsTop: (route) => !route.sessionId,

  init() {
    const periodButtons = [...document.querySelectorAll("#stats-period button")];
    const syncPeriod = () => periodButtons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.period === period)));
    periodButtons.forEach((b) => b.addEventListener("click", () => {
      period = b.dataset.period;
      localStorage.setItem("sessionStatsPeriod", period);
      syncPeriod();
      loadStats().catch((e) => { $("stats-period-note").textContent = e.message; });
    }));
    syncPeriod();
    const metric = $("session-metric");
    metric.replaceChildren(...METRICS.map((m) => new Option(m.label, m.id, false, m.id === trend.metric)));
    metric.addEventListener("change", () => {
      trend.metric = metric.value;
      localStorage.setItem("sessionMetric", trend.metric);
      if (allSessions) drawTrends();
    });
    const modeButtons = [...document.querySelectorAll("#trend-mode button")];
    const syncMode = () => modeButtons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === trend.mode)));
    modeButtons.forEach((b) => b.addEventListener("click", () => {
      trend.mode = b.dataset.mode;
      localStorage.setItem("trendMode", trend.mode);
      syncMode();
      if (allSessions) drawTrends();
    }));
    syncMode();
    const split = $("trend-split");
    split.replaceChildren(...PROGRESSION.map(([k, name]) => new Option(name, k, false, k === trend.split)));
    split.addEventListener("change", () => {
      trend.split = split.value;
      localStorage.setItem("trendSplit", trend.split);
      if (allSessions) drawTrends();
    });
    listTable = createTable($("sessions-table"), {
      sort: { id: "session", dir: "desc" }, pageSize: 100, empty: "No sessions in this time window.",
      onRowClick: (s) => { location.hash = `#sessions/${s.session_id}`; },
      rowLabel: (s) => `Session ${s.session_id}, ${fmt.day(s.start)}`,
    });
    runsTable = createRunsTable($("session-runs"), {
      storageKey: "sessionRunsColumns", hide: ["session"], sort: { id: "date", dir: "asc" }, icons: false,
    });
  },

  async load(route) {
    $("sessions-list").hidden = !!route.sessionId;
    $("session-detail").hidden = !route.sessionId;
    return route.sessionId ? loadDetail(route.sessionId) : loadList();
  },

  onResize(route) {
    if (route.sessionId && detail) drawTimeline(detail.runs);
    else if (!route.sessionId && allSessions) drawTrends();
  },
};

async function loadList() {
  const [d] = await Promise.all([fetchList(), loadStats()]);
  if (!d) return null;
  listTable.render(d.sessions, LIST_COLUMNS);
  return plural(d.sessions.length, "session");
}

async function loadStats() {
  const s = await fetchStats();
  if (!s) return;
  allSessions = s.sessions;
  $("stats-period-note").textContent =
    `${plural(allSessions.length, "session")} in ${PERIODS[period]}, oldest to newest.`;
  drawStats();
  drawTrends();
}

async function loadDetail(id) {
  const result = await fetchDetail(id);
  if (!result) return null;
  const [summary, runs] = result;
  detail = { summary, runs: runs.runs };
  const st = summary.stats;
  if (!st.runs_played) {
    $("session-title").textContent = `Session ${id}`;
    $("session-sub").textContent = "This session doesn't exist (any more).";
    $("session-body").hidden = true;
    return "";
  }
  $("session-body").hidden = false;
  const s = summary.sessions[0];
  $("session-title").textContent = `Session ${id}`;
  $("session-sub").textContent = `${fmt.day(s.start)} · ${timeRange(s)} · ${fmt.duration(st.time_span_s)}`;
  const nether = st.splits.nether, finish = st.splits.finish;
  $("session-tiles").replaceChildren(
    tile("Runs played", fmt.int(st.runs_played), `${fmt.int(st.wall_resets)} wall resets`),
    tile("Nethers", fmt.int(nether.count), st.nethers_per_hour == null ? "" : `${fmt.num(st.nethers_per_hour, 2)} per hour`),
    tile("Average nether", fmt.timeTenths(nether.avg_ms), nether.best_ms == null ? "" : `best ${fmt.time(nether.best_ms)}`),
    tile("Resets per nether", fmt.num(st.resets_per_nether, 1)),
    tile("Time played", fmt.duration(st.time_span_s), `${fmt.duration(st.playtime_s)} in worlds`),
    tile("Completions", fmt.int(st.finished), finish.best_ms == null ? "" : `best ${fmt.time(finish.best_ms)}`),
  );
  drawTimeline(runs.runs);
  runsTable.render(runs.runs, runs.pbs, runs.advancements);
  return "";
}

function drawTimeline(runs) {
  scatterChart($("session-timeline"), runs.map((r) => {
    const reached = SPLITS.filter(([k]) => k !== "finish" && r.splits[k] != null)
      .map(([k, name]) => ({ value: fmt.time(r.splits[k]), name }));
    return {
      x: new Date(r.date).getTime(),
      y: r.final_igt ?? 0,
      emphasis: r.splits.nether != null,
      title: `${r.world_number == null ? r.world_name : `#${r.world_number}`} · ${fmt.clock(r.date)}`,
      rows: [{ value: fmt.time(r.final_igt), name: r.result === "finished" ? "finished" : "reset at" }, ...reached],
    };
  }), {
    name: "Runs in this session: time of day against in-game time when the run ended",
    yTickFormat: fmt.timeShort,
    legend: [{ label: "Entered nether", key: "emphasis" }, { label: "Other runs", key: "muted" }],
  });
}

// ---- Session statistics (every session) ----

const sessionName = (s) => `Session #${s.session_id} · ${fmt.day(s.start)}`;

/** The session with the highest value (null if none has one). */
function best(sessions, value) {
  return sessions.filter((s) => value(s) != null).reduce((a, b) => (!a || value(b) > value(a) ? b : a), null);
}

function drawStats() {
  const all = allSessions;
  if (!all.length) {
    $("session-stat-tiles").replaceChildren(tile("Sessions", "0", "none in this period"));
    return;
  }
  const n = all.length;
  const sum = (f) => all.reduce((t, s) => t + (f(s) ?? 0), 0);
  const fastest = best(all.filter((s) => s.time_span_s >= MIN_RATE_SECONDS), (s) => s.nethers_per_hour);
  const mostNethers = best(all, (s) => s.splits.nether.count);
  const longest = best(all, (s) => s.time_span_s);
  $("session-stat-tiles").replaceChildren(
    tile("Sessions", fmt.int(n), `since ${fmt.day(all[0].start)}`),
    tile("Average length", fmt.duration(sum((s) => s.time_span_s) / n), `${fmt.duration(sum((s) => s.time_span_s))} in total`),
    tile("Per session", `${fmt.num(sum((s) => s.splits.nether.count) / n, 1)} nethers`,
      `${fmt.num(sum((s) => s.runs_played) / n, 0)} runs played`),
    tile("Best nethers/hour", fastest ? fmt.num(fastest.nethers_per_hour, 2) : "–",
      fastest ? sessionName(fastest) : "needs a 30-minute session"),
    tile("Most nethers", mostNethers ? fmt.int(mostNethers.splits.nether.count) : "–", mostNethers ? sessionName(mostNethers) : ""),
    tile("Longest session", fmt.duration(longest.time_span_s), sessionName(longest)),
  );
}

function drawTrends() {
  const points = (getY) => allSessions.map((s) => ({
    label: fmt.day(s.start),
    title: `Session ${s.session_id} · ${fmt.dateTime(s.start)} · ${fmt.int(s.runs_played)} runs`,
    y: getY(s),
  }));
  const m = METRICS.find((x) => x.id === trend.metric);
  $("session-metric-title").replaceChildren(m.label, " ", h("span", { class: "sub" }, "by session"));
  lineChart($("chart-session-metric"), points(m.value), {
    name: m.label, zero: true, format: m.format, tickFormat: m.tick, connectGaps: true, missing: m.missing,
  });
  // Sessions that never reached the split have no value: the line joins its neighbours.
  const i = PROGRESSION.findIndex(([k]) => k === trend.split);
  const name = PROGRESSION[i][1].toLowerCase();
  const segment = trend.mode === "segment" && i > 0;  // the nether has no previous split
  const label = segment ? `Average ${PROGRESSION[i - 1][1].toLowerCase()} → ${name}` : `Average ${name}`;
  lineChart($("chart-split"), points((s) => s.splits[trend.split][segment ? "segment_avg_ms" : "avg_ms"]), {
    name: label, steps: TIME_STEPS, connectGaps: true, format: fmt.timeTenths, tickFormat: fmt.timeShort,
    missing: segment ? `no run reached both this session` : `no ${name} this session`,
  });
}
