// The runs table: column picker, PB badges, session links, a View button per run. Used on
// the Runs page, in a session's detail view and (small, without the picker) on the Dashboard.
import * as fmt from "./fmt.js";
import { h, SPLITS } from "./common.js";
import { createTable } from "./table.js";
import { SEED_TYPE_NAMES, seedTypeLabel } from "./seedtypes.js";

const TIME_SPLITS = SPLITS.filter(([key]) => key !== "finish");
const TABS = [["story", "Minecraft"], ["nether", "Nether"], ["end", "The End"],
              ["adventure", "Adventure"], ["husbandry", "Husbandry"]];

function timeCell(ms, isPb) {
  if (ms == null) return h("span", { class: "muted" }, "–");
  return h("span", {}, fmt.time(ms), isPb ? h("span", { class: "pb", title: "Personal best" }, "PB") : null);
}

/** Every column the table can show. */
function allColumns(pbs, advancements) {
  const isPb = (key, run) => pbs[key]?.run_id === run.run_id;
  const cols = [
    { id: "date", group: "Run", label: "Date", value: (r) => r.date,
      cell: (r) => fmt.dateTime(r.date) },
    { id: "session", group: "Run", label: "Session", num: true, value: (r) => r.session_id,
      cell: (r) => h("a", { href: `#sessions/${r.session_id}`, title: `Open session ${r.session_id}` }, `#${r.session_id}`) },
    { id: "world", group: "Run", label: "World", num: true, value: (r) => r.world_number,
      cell: (r) => (r.world_number == null ? r.world_name : `#${r.world_number}`) },
    { id: "seed_type", group: "Run", label: "Seed type", title: "The overworld structure looted (needs Hermes)",
      value: (r) => (r.seed_type ? SEED_TYPE_NAMES[r.seed_type] ?? r.seed_type : null),
      cell: (r) => seedTypeLabel(r.seed_type) ?? h("span", { class: "muted" }, "–") },
    ...TIME_SPLITS.map(([key, name]) => ({
      id: key, group: "Splits", label: name, icon: key, num: true, value: (r) => r.splits[key],
      cell: (r) => timeCell(r.splits[key], isPb(key, r)),
    })),
    { id: "result", group: "Run", label: "Result", value: (r) => r.result,
      cell: (r) => (r.result === "finished" ? "Finished" : "Reset") },
    { id: "final_igt", group: "Run", label: "IGT", num: true, title: "IGT when the run finished or was reset",
      value: (r) => r.final_igt,
      cell: (r) => timeCell(r.final_igt, r.result === "finished" && isPb("finish", r)) },
    { id: "score", group: "Run", label: "Score", num: true,
      title: "Seconds lost against a top player on the same seed (finished Hermes runs; lower is better)",
      value: (r) => r.score,
      cell: (r) => (r.score == null ? h("span", { class: "muted" }, "–")
        : h("a", { href: `#score/${encodeURIComponent(r.run_id)}`, title: "How this score is worked out" }, fmt.signedSeconds(r.score))) },
    { id: "final_rta", group: "Run", label: "RTA", num: true, title: "RTA when the run finished or was reset",
      value: (r) => r.final_rta, cell: (r) => timeCell(r.final_rta, false) },
    { id: "deaths", group: "Deaths", label: "Deaths", num: true, value: (r) => r.deaths,
      cell: (r) => fmt.int(r.deaths) },
    { id: "deaths_with_respawn", group: "Deaths", label: "Death resets", num: true,
      title: "Deaths that respawned at a bed or respawn anchor", value: (r) => r.deaths_with_respawn,
      cell: (r) => fmt.int(r.deaths_with_respawn) },
    { id: "deaths_without_respawn", group: "Deaths", label: "Accidental deaths", num: true,
      title: "Deaths that sent you back to world spawn", value: (r) => r.deaths_without_respawn,
      cell: (r) => fmt.int(r.deaths_without_respawn) },
    { id: "worlds_generated", group: "Run", label: "Worlds generated", num: true,
      title: "How far this run pushed the world counter (wall resets + 1)",
      value: (r) => r.worlds_generated, cell: (r) => fmt.int(r.worlds_generated) },
  ];
  for (const { id, name } of advancements) {
    cols.push({ id: `adv:${id}`, group: `adv:${id.split("/")[0]}`, label: name, num: true, title: id,
                value: (r) => r.advancements[id] ?? null,
                cell: (r) => timeCell(r.advancements[id] ?? null, false) });
  }
  return cols;
}

/** Always the first column: opens the run's own page. */
const VIEW_COLUMN = {
  id: "view", label: "", title: "Open run", sortable: false, value: () => null,
  cell: (r) => h("a", { class: "button small", href: `#run/${encodeURIComponent(r.run_id)}`,
                        "aria-label": `View run ${r.world_number == null ? r.world_name : `#${r.world_number}`}` }, "View"),
};

// Added after 1.2.1: shown once to people who had already picked their columns.
const NEW_COLUMNS = ["seed_type", "score"];
export const DEFAULT_COLUMNS = ["date", "session", "world", "seed_type", ...TIME_SPLITS.map(([k]) => k), "result", "final_igt",
                         "score", "deaths"];

/**
 * container: element to fill. storageKey: where the visible columns are remembered.
 * hide: column ids never shown here (e.g. "session" inside a session's own view).
 * picker: false shows the default columns with no Columns button (and no storageKey needed).
 * columns: with picker false, the column ids to show instead of the defaults.
 * limit: show only the first N runs in the table's current sort order (sorting all the runs
 *   given), with no paging.
 * onSort(sort, column): after a header click, with the column now sorted by.
 * icons: false leaves the icons out of the column headers.
 */
export function createRunsTable(container, { storageKey, hide = [], sort = { id: "date", dir: "desc" }, empty,
                                             picker: hasPicker = true, columns: fixed = null, limit = null,
                                             icons = true, onSort = null }) {
  let visible = (hasPicker && JSON.parse(localStorage.getItem(storageKey) || "null")) || fixed || DEFAULT_COLUMNS;
  // Columns added since the visible ones were chosen are shown once; after that, the picker decides.
  const known = hasPicker && JSON.parse(localStorage.getItem(`${storageKey}:known`) || "null");
  if (hasPicker && localStorage.getItem(storageKey)) {
    const added = NEW_COLUMNS.filter((id) => !(known ?? []).includes(id) && !visible.includes(id));
    if (added.length) visible = [...visible, ...added];  // put in table order by setVisible/columns()
  }
  if (hasPicker) localStorage.setItem(`${storageKey}:known`, JSON.stringify(NEW_COLUMNS));
  let data = null;

  const picker = h("details", { class: "column-picker" }, h("summary", { class: "button" }, "Columns"));
  const panel = h("div", { class: "picker-panel" });
  picker.append(panel);
  const tableBox = h("div");
  const table = createTable(tableBox, {
    sort, limit, pageSize: 100, empty: empty ?? "No runs match these filters.",
    onSort: (s) => onSort?.(s, columns().find((c) => c.id === s.id)),
  });
  container.replaceChildren(...(hasPicker ? [h("div", { class: "table-toolbar" }, picker)] : []), tableBox);

  // Close the picker when clicking elsewhere.
  document.addEventListener("click", (e) => { if (!picker.contains(e.target)) picker.open = false; });

  function columns() {
    return [VIEW_COLUMN, ...allColumns(data.pbs, data.advancements)
      .filter((c) => visible.includes(c.id) && !hide.includes(c.id))
      .map((c) => (icons ? c : { ...c, icon: null }))];
  }

  function buildPicker() {
    const cols = allColumns(data.pbs, data.advancements).filter((c) => !hide.includes(c.id));
    const groups = [["Run"], ["Splits"], ["Deaths"], ...TABS.map(([key, name]) => [`adv:${key}`, `Advancements: ${name}`])];
    panel.replaceChildren(
      h("div", { class: "picker-actions" },
        h("button", { type: "button", class: "link", onclick: () => setVisible(DEFAULT_COLUMNS) }, "Reset to default")),
      ...groups.map(([group, title]) => {
        const items = cols.filter((c) => c.group === group);
        return h("fieldset", { class: "picker-group" }, h("legend", {}, title ?? group),
          items.map((c) => h("label", {},
            h("input", { type: "checkbox", checked: visible.includes(c.id),
                         onchange: (e) => setVisible(e.target.checked ? [...visible, c.id] : visible.filter((v) => v !== c.id)) }),
            c.label)));
      }));
  }

  function setVisible(ids) {
    // Keep the table's column order, not the click order.
    const order = allColumns(data.pbs, data.advancements).map((c) => c.id);
    visible = order.filter((id) => ids.includes(id));
    localStorage.setItem(storageKey, JSON.stringify(visible));
    buildPicker();
    table.render(data.rows, columns());
  }

  return {
    render(rows, pbs, advancements) {
      data = { rows, pbs, advancements };
      if (hasPicker) buildPicker();
      table.render(rows, columns());
    },
  };
}
