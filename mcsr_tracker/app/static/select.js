// A dropdown whose options can show icons (a native <select> can only show text).
// Behaves like a select: click or Enter/Space/arrows to open, arrows to move, Enter to
// pick, Esc to close, typing jumps to an option starting with that letter.
import { h } from "./common.js";
import { icon } from "./icons.js";

let openMenu = null;  // the one open dropdown's close function
document.addEventListener("click", () => openMenu?.());

/**
 * options: [[value, text, iconKey?]]. Returns the element, with .value (get/set, without
 * calling onChange) like a select. ariaLabel names it for screen readers.
 */
export function iconSelect({ options, value, onChange, ariaLabel, attrs = {} }) {
  let current = options.some(([v]) => v === value) ? value : options[0][0];
  let active = 0;  // highlighted option while open
  const id = `menu-${Math.random().toString(36).slice(2)}`;

  const face = h("span", { class: "icon-select-face" });
  const button = h("button", {
    type: "button", class: "icon-select-button", "aria-haspopup": "listbox", "aria-expanded": "false",
    "aria-controls": id, "aria-label": ariaLabel,
  }, face, h("span", { class: "icon-select-caret", "aria-hidden": "true" }, "▾"));
  const list = h("ul", { class: "icon-select-list", role: "listbox", id, tabindex: "-1", hidden: true });
  const items = options.map(([v, text, key], i) => h("li", {
    role: "option", id: `${id}-${i}`, "data-value": v,
    onclick: (e) => { e.stopPropagation(); choose(i); },
    onpointermove: () => highlight(i),
  }, h("span", { class: "icon-select-slot" }, key ? icon(key) : null), text));
  list.append(...items);
  const root = h("div", { class: "icon-select", ...attrs }, button, list);

  function render() {
    const [, text, key] = options.find(([v]) => v === current);
    face.replaceChildren(h("span", { class: "icon-select-slot" }, key ? icon(key) : null), text);
    items.forEach((li) => li.setAttribute("aria-selected", String(li.dataset.value === current)));
  }

  function highlight(i) {
    active = i;
    items.forEach((li, j) => li.classList.toggle("active", j === i));
    list.setAttribute("aria-activedescendant", items[i].id);
    items[i].scrollIntoView({ block: "nearest" });
  }

  function open() {
    openMenu?.();
    list.hidden = false;
    button.setAttribute("aria-expanded", "true");
    highlight(Math.max(0, options.findIndex(([v]) => v === current)));
    list.focus();
    openMenu = close;
  }

  function close(focusButton = false) {
    list.hidden = true;
    button.setAttribute("aria-expanded", "false");
    if (openMenu === close) openMenu = null;
    if (focusButton) button.focus();
  }

  function choose(i) {
    close(true);
    if (options[i][0] === current) return;
    current = options[i][0];
    render();
    onChange(current);
  }

  button.addEventListener("click", (e) => {
    e.stopPropagation();
    if (list.hidden) open(); else close();
  });
  button.addEventListener("keydown", (e) => {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) { e.preventDefault(); open(); }
  });
  list.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") highlight(Math.min(items.length - 1, active + 1));
    else if (e.key === "ArrowUp") highlight(Math.max(0, active - 1));
    else if (e.key === "Home") highlight(0);
    else if (e.key === "End") highlight(items.length - 1);
    else if (e.key === "Enter" || e.key === " ") choose(active);
    else if (e.key === "Escape" || e.key === "Tab") { close(e.key === "Escape"); return; }
    else if (e.key.length === 1) {
      const start = options.findIndex(([, text], i) => i > active && text.toLowerCase().startsWith(e.key.toLowerCase()));
      const i = start >= 0 ? start : options.findIndex(([, text]) => text.toLowerCase().startsWith(e.key.toLowerCase()));
      if (i >= 0) highlight(i);
      return;
    } else return;
    e.preventDefault();
  });

  Object.defineProperty(root, "value", {
    get: () => current,
    set: (v) => { if (options.some(([o]) => o === v)) { current = v; render(); } },
  });
  render();
  return root;
}
