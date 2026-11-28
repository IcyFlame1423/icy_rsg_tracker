// Sortable table with paging. Used by the Runs table and the Sessions list.
import { h } from "./common.js";
import { icon } from "./icons.js";

/**
 * columns: [{id, label, value(row) -> sortable value (null sorts last),
 *            cell(row) -> node/string, num (right-aligned), title (header tooltip),
 *            sortable (false: a plain header, e.g. a column of buttons), icon (a split's icon key)}]
 * options: {sort: {id, dir: "asc"|"desc"}, pageSize, onRowClick(row), rowLabel(row),
 *           empty (text, or a function returning nodes), onSort(sort) (after a header click),
 *           limit (show only the first N rows in the current sort, with no "Show more")}
 * Returns {render(rows, columns)}.
 */
export function createTable(container, options) {
  let sort = { ...options.sort };
  let shown = options.limit ?? options.pageSize ?? 100;
  let rows = [], columns = [];
  let resizeWatch = null;  // keeps the top scrollbar as wide as the table

  function sorted() {
    const col = columns.find((c) => c.id === sort.id) ?? columns.find((c) => c.sortable !== false);
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const va = col.value(a), vb = col.value(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;   // blanks last, whichever direction
      if (vb == null) return -1;
      return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
    });
  }

  function draw() {
    container.replaceChildren();
    if (!rows.length) {
      // empty: text, or a function returning nodes (e.g. a message with a button).
      const empty = typeof options.empty === "function" ? options.empty() : options.empty ?? "Nothing to show.";
      container.append(h("div", { class: "table-empty" }, empty));
      return;
    }
    const head = h("tr", {}, columns.map((c) => {
      if (c.sortable === false) {
        return h("th", { scope: "col", class: c.num ? "num" : "" }, c.label ? c.label : h("span", { class: "sr-only" }, c.title ?? ""));
      }
      const active = c.id === sort.id;
      const button = h("button", {
        type: "button", class: "sort", title: c.title,
        onclick: () => {
          sort = active ? { id: c.id, dir: sort.dir === "asc" ? "desc" : "asc" }
                        : { id: c.id, dir: c.num ? "asc" : "desc" };
          options.onSort?.(sort);
          draw();
        },
      }, c.icon ? icon(c.icon) : null, c.label, h("span", { class: "sort-mark", "aria-hidden": "true" }, active ? (sort.dir === "asc" ? "▲" : "▼") : ""));
      return h("th", { scope: "col", class: c.num ? "num" : "",
                       "aria-sort": active ? (sort.dir === "asc" ? "ascending" : "descending") : "none" }, button);
    }));
    const all = sorted();
    const body = h("tbody", {}, all.slice(0, shown).map((row) => {
      const tr = h("tr", {}, columns.map((c) => h("td", { class: c.num ? "num" : "" }, c.cell(row))));
      if (options.onRowClick) {
        tr.classList.add("clickable");
        tr.tabIndex = 0;
        if (options.rowLabel) tr.setAttribute("aria-label", options.rowLabel(row));
        tr.addEventListener("click", (e) => { if (!e.target.closest("a")) options.onRowClick(row); });
        tr.addEventListener("keydown", (e) => { if (e.key === "Enter") options.onRowClick(row); });
      }
      return tr;
    }));
    const table = h("table", { class: "data-table sticky-head" }, h("thead", {}, head), body);
    const scroller = h("div", { class: "table-scroll bar-on-top" }, table);
    container.append(topScrollbar(scroller, table), scroller);
    if (all.length > shown && options.limit == null) {
      container.append(h("div", { class: "table-more" },
        h("span", { class: "muted" }, `Showing ${shown.toLocaleString()} of ${all.length.toLocaleString()}`),
        h("button", { type: "button", class: "button", onclick: () => { shown += options.pageSize ?? 100; draw(); } },
          "Show more")));
    }
  }

  /** A scrollbar above a table too wide for the page, kept in step with the one below it, so
   *  scrolling sideways doesn't mean going to the bottom first. Hidden when the table fits. */
  function topScrollbar(scroller, table) {
    const spacer = h("div", { class: "table-scroll-top-spacer" });
    const bar = h("div", { class: "table-scroll-top", "aria-hidden": "true" }, spacer);
    const follow = (from, to) => from.addEventListener("scroll", () => {
      if (to.scrollLeft !== from.scrollLeft) to.scrollLeft = from.scrollLeft;
    });
    follow(bar, scroller);
    follow(scroller, bar);
    const fit = () => {
      spacer.style.width = `${table.scrollWidth}px`;
      bar.hidden = table.scrollWidth <= scroller.clientWidth + 1;
    };
    resizeWatch?.disconnect();
    resizeWatch = new ResizeObserver(fit);
    resizeWatch.observe(table);
    resizeWatch.observe(scroller);
    return bar;
  }

  return {
    render(newRows, newColumns) {
      rows = newRows;
      columns = newColumns;
      if (!columns.some((c) => c.id === sort.id)) sort = { ...options.sort };
      shown = options.limit ?? options.pageSize ?? 100;
      draw();
    },
  };
}
