// Runs page: every run in the time window, filterable, sortable, with a column picker.
import * as fmt from "./fmt.js";
import { $, getJSON, h, latestOnly, windowQuery } from "./common.js";
import { createRunsTable } from "./runs-table.js";
import { describeFilters, FILTERS, filterControls, matches, setFilter, syncControls } from "./run-filters.js";

let data = null;
let table = null;
const fetchRuns = latestOnly(() => getJSON(`/api/runs?${windowQuery()}`));

const filtered = () => data.runs.filter(matches);

function note() {
  if (!data) return "";
  return `${fmt.int(filtered().length)} of ${fmt.int(data.runs.length)} runs in this window`;
}

/** Shown when runs exist in the window but the filters hide all of them. */
function emptyMessage() {
  return [
    h("div", {}, `None of the ${fmt.int(data.runs.length)} runs in this time window match the filters (${describeFilters()}).`),
    h("button", { type: "button", class: "button", style: "margin-top:12px", onclick: clearFilters }, "Show all runs"),
  ];
}

function clearFilters() {
  for (const k of Object.keys(FILTERS)) setFilter(k, "any");
  syncControls($("page-filters"));
  draw();
}

function draw() {
  $("runs-empty").hidden = data.runs.length > 0;
  $("runs-empty").textContent = data.total_runs === 0
    ? "No runs tracked yet. Play a run with SpeedRunIGT and it will show up here."
    : "No runs in this time window.";
  $("runs-table").hidden = data.runs.length === 0;
  table.render(filtered(), {}, data.advancements);  // no PB badges here
  $("window-note").textContent = note();
}

export const runsPage = {
  id: "runs",
  usesWindow: () => true,

  init() {
    table = createRunsTable($("runs-table"), { storageKey: "runsColumns", empty: emptyMessage });
  },

  /** Page-specific filters, shown in the shared filter row. */
  filters() {
    return filterControls(() => { if (data) draw(); });
  },

  async load() {
    const d = await fetchRuns();
    if (!d) return null;
    data = d;
    draw();
    return note();
  },
};
