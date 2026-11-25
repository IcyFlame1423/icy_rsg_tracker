// Dashboard page: headline numbers, split progression, split times, the latest runs.
import * as fmt from "./fmt.js";
import { showTooltip, hideTooltip } from "./charts.js";
import { $, getJSON, h, latestOnly, plural, PROGRESSION, SPLITS, state, tile, windowQuery } from "./common.js";
import { createRunsTable } from "./runs-table.js";
import { icon, iconSlot } from "./icons.js";
import { describeFilters, filterControls, matches, syncControls } from "./run-filters.js";

const RECENT = 10;  // runs in the Recent runs card
const local = {
  summary: null,
  runs: null,
  progressionBase: localStorage.getItem("progressionBase") || "previous",  // "runs" | "previous"
};
let recentTable = null;

const fetchData = latestOnly(() => Promise.all([
  getJSON(`/api/summary?${windowQuery()}`),
  getJSON(`/api/runs?${windowQuery()}`),
]));

export const dashboard = {
  id: "dashboard",
  usesWindow: () => true,

  init() {
    const buttons = [...document.querySelectorAll("#progression-base button")];
    const sync = () => buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.base === local.progressionBase)));
    buttons.forEach((b) => b.addEventListener("click", () => {
      local.progressionBase = b.dataset.base;
      localStorage.setItem("progressionBase", local.progressionBase);
      sync();
      if (local.summary?.stats.runs_played) renderMeters(local.summary.stats);
    }));
    sync();

    recentTable = createRunsTable($("recent-runs"), {
      picker: false, icons: false, limit: RECENT, empty: () => `No runs in this time window match the filters (${describeFilters()}).`,
    });
  },

  async load() {
    const result = await fetchData();
    if (!result) return null;  // superseded by a newer load
    const [s, runs] = result;
    local.summary = s;
    local.runs = runs;
    if (filtersBuiltWith !== state.textures) buildRecentFilters();  // icons became available
    syncControls($("recent-filters"));  // they may have changed on the Runs page
    render(s);
    const st = s.stats;
    return st.runs_played
      ? `${fmt.int(st.runs_played)} runs · ${fmt.dateTime(s.first_run)} – ${fmt.dateTime(s.last_run)}`
      : "";
  },
};

function render(s) {
  const st = s.stats;
  const empty = st.runs_played === 0;
  $("dashboard-content").hidden = empty;
  $("dashboard-empty").hidden = !empty;
  $("dashboard-empty").textContent = s.total_runs === 0
    ? "No runs tracked yet. Play a run with SpeedRunIGT and it will show up here."
    : "No runs in this time window.";
  if (empty) return;
  renderKpis(st, s.sessions.length);
  renderMeters(st);
  renderSplitTable(st);
  renderRecent();
}

function renderKpis(st, sessionCount) {
  const nether = st.splits.nether, finish = st.splits.finish;
  $("hero-art").replaceChildren(icon("nether") ?? "");
  $("hero-value").textContent = st.nethers_per_hour == null ? "–" : fmt.num(st.nethers_per_hour, 2);
  $("hero-sub").textContent = `${plural(nether.count, "nether")} in ${fmt.duration(st.time_span_s)}`;
  const playedResets = st.runs_played - st.finished;
  $("tiles").replaceChildren(
    withArt(tile("Runs played", fmt.int(st.runs_played), plural(sessionCount, "session")), "runs"),
    withArt(tile("Total resets", fmt.int(st.total_resets), `${fmt.int(st.wall_resets)} wall · ${fmt.int(playedResets)} played`), "resets"),
    withArt(tile("Resets per nether", fmt.num(st.resets_per_nether, 1)), "netherrack"),
    withArt(tile("Average nether", fmt.timeTenths(nether.avg_ms), nether.best_ms == null ? "" : `best ${fmt.time(nether.best_ms)}`), "nether"),
    withArt(tile("Time played", fmt.duration(st.time_span_s), `${fmt.duration(st.playtime_s)} in worlds`), "clock"),
    withArt(tile("Completions", fmt.int(st.finished), finish.best_ms == null ? "" : `PB ${fmt.time(finish.best_ms)}`), "finish"),
  );
}

/** A tile with a big split icon on its right. */
function withArt(tileNode, key) {
  const art = icon(key);
  if (art) {
    tileNode.classList.add("has-art");
    tileNode.append(h("span", { class: "tile-art" }, art));
  }
  return tileNode;
}

function renderMeters(st) {
  const byRuns = local.progressionBase === "runs";
  $("progression-note").textContent = byRuns
    ? "Share of all runs played that reached each split."
    : "Share of runs that reached the previous split (nether: of runs played).";
  $("meters").replaceChildren(...PROGRESSION.flatMap(([key, name], i) => {
    const s = st.splits[key];
    const prev = i === 0 || byRuns ? null : PROGRESSION[i - 1];
    const wholeCount = prev ? st.splits[prev[0]].count : st.runs_played;
    const whole = prev ? `${prev[1].toLowerCase()} runs` : "runs played";
    const rate = wholeCount ? s.count / wholeCount : null;
    const tip = (x, y) => showTooltip(x, y, name, [
      { value: fmt.pct(rate), name: `of ${whole}` },
      { value: `${fmt.int(s.count)} of ${fmt.int(wholeCount)}`, name: "runs" },
    ]);
    const track = h("div", {
      class: "meter-track", tabindex: "0", role: "meter",
      "aria-label": `${name}: ${fmt.pct(rate)} of ${whole} (${s.count} of ${wholeCount})`,
      "aria-valuemin": "0", "aria-valuemax": "100",
      "aria-valuenow": String(rate == null ? 0 : Math.min(100, Math.round(rate * 1000) / 10)),
      onpointermove: (e) => tip(e.clientX, e.clientY), onpointerleave: hideTooltip,
      onfocus: () => { const r = track.getBoundingClientRect(); tip(r.right, r.top); }, onblur: hideTooltip,
    }, h("div", { class: "meter-fill", style: `width:${Math.min(1, rate ?? 0) * 100}%` }));  // never overflows
    return [
      h("div", { class: "meter-name" }, iconSlot(key), name),
      track,
      h("div", { class: "meter-figure" }, fmt.pct(rate), h("span", { class: "count" }, `(${fmt.int(s.count)})`)),
    ];
  }));
}

function renderSplitTable(st) {
  $("split-table").tBodies[0].replaceChildren(...SPLITS.map(([key, name]) => {
    const s = st.splits[key];
    const cls = "num" + (s.count ? "" : " muted");
    return h("tr", {}, h("td", {}, iconSlot(key), name),
      ...[fmt.int(s.count), fmt.timeTenths(s.avg_ms), fmt.timeTenths(s.median_ms), fmt.time(s.best_ms)]
        .map((text) => h("td", { class: cls }, text)));
  }));
}

let filtersBuiltWith = null;  // state.textures when the filters were made

/** Same filters as the Runs page, so "All matching runs" continues where this leaves off. */
function buildRecentFilters() {
  filtersBuiltWith = state.textures;
  $("recent-filters").replaceChildren(...filterControls(() => { if (local.runs) renderRecent(); }));
}

function renderRecent() {
  const { runs, pbs, advancements } = local.runs;
  const matching = runs.filter(matches);
  recentTable.render(matching, pbs, advancements);
  $("recent-note").textContent = matching.length > RECENT
    ? `The latest ${RECENT} of ${fmt.int(matching.length)} matching runs in this window`
    : `${plural(matching.length, "matching run")} in this window`;
}
