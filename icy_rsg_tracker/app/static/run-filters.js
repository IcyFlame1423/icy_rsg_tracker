// The run filters (Reached), shared by the Runs page and the Dashboard's
// recent runs: changing them in one place changes them in the other.
import { h, SPLITS } from "./common.js";
import { iconSelect } from "./select.js";

export const FILTERS = {
  reached: {
    label: "Reached",
    // [value, text, icon]
    options: [["any", "Any split", "any"], ...SPLITS.filter(([k]) => k !== "finish").map(([k, name]) => [k, name, k]),
              ["finish", "Finished", "finish"]],
    icons: true,  // a dropdown that shows the split icons
    // Most runs reset before the nether, so by default show the ones that got somewhere.
    default: "nether",
    test: (v, r) => v === "any" || (v === "finish" ? r.result === "finished" : r.splits[v] != null),
  },
};

for (const old of ["deaths", "result"]) localStorage.removeItem(`runsFilter.${old}`);  // filters that were removed

export const filters = Object.fromEntries(Object.entries(FILTERS).map(([k, f]) =>
  [k, localStorage.getItem(`runsFilter.${k}`) ?? f.default]));

export function setFilter(key, value) {
  filters[key] = value;
  localStorage.setItem(`runsFilter.${key}`, value);
}

export const matches = (run) => Object.entries(FILTERS).every(([k, f]) => f.test(filters[k], run));

/** "Reached: Nether" for the filters that aren't "any". */
export function describeFilters() {
  return Object.entries(FILTERS).filter(([k]) => filters[k] !== "any")
    .map(([k, f]) => `${f.label}: ${f.options.find(([v]) => v === filters[k])[1]}`).join(", ");
}

/** One labelled select per filter; onChange runs after a filter changes.
 *  icons: false uses plain selects even for filters that could show icons. */
export function filterControls(onChange, { icons = true } = {}) {
  return Object.entries(FILTERS).map(([key, f]) => (icons && f.icons
    ? h("div", { class: "filter" }, h("span", { class: "filter-label", "aria-hidden": "true" }, f.label),
        iconSelect({ options: f.options, value: filters[key], ariaLabel: f.label, attrs: { "data-filter": key },
                     onChange: (v) => { setFilter(key, v); onChange(); } }))
    : h("label", { class: "filter" },
    h("span", { class: "filter-label" }, f.label),
    h("select", {
      "data-filter": key,
      onchange: (e) => { setFilter(key, e.target.value); onChange(); },
    }, f.options.map(([value, text]) => h("option", { value, selected: value === filters[key] }, text))))));
}

/** After filters change elsewhere: show the current values in these selects. */
export function syncControls(root) {
  root.querySelectorAll("[data-filter]").forEach((s) => { s.value = filters[s.dataset.filter]; });
}
