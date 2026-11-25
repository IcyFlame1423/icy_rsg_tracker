// A dropdown whose options can show icons (a native <select> can only show text).
// Behaves like a select: click or Enter/Space/arrows to open, arrows to move, Enter to
// pick, Esc to close, typing jumps to an option starting with that letter.
// An option can have a submenu (its choices open beside it on hover, click or →); then
// one of those is what gets picked, not the option itself.
import { h } from "./common.js";
import { icon } from "./icons.js";

let openMenu = null;  // the one open dropdown's close function
document.addEventListener("click", () => openMenu?.());

/**
 * options: [[value, text, iconKey?, sub?]]; sub: [[value, text, iconKey?] | {heading}], the
 * submenu's choices (without an icon of their own, they show the option's when picked). Returns the element, with .value
 * (get/set, without calling onChange) like a select. ariaLabel names it for screen readers.
 */
export function iconSelect({ options, value, onChange, ariaLabel, attrs = {} }) {
  // Every value that can be picked -> [text, iconKey]
  const choices = new Map();
  for (const [v, text, key, sub] of options) {
    if (sub) for (const c of sub) { if (Array.isArray(c)) choices.set(c[0], [c[1], c[2] ?? key]); }
    else choices.set(v, [text, key]);
  }
  let current = choices.has(value) ? value : choices.keys().next().value;
  let active = 0;  // highlighted option while open
  const id = `menu-${Math.random().toString(36).slice(2)}`;

  const face = h("span", { class: "icon-select-face" });
  const button = h("button", {
    type: "button", class: "icon-select-button", "aria-haspopup": "listbox", "aria-expanded": "false",
    "aria-controls": id, "aria-label": ariaLabel,
  }, face, h("span", { class: "icon-select-caret", "aria-hidden": "true" }, "▾"));
  const list = h("ul", { class: "icon-select-list", role: "listbox", id, tabindex: "-1", hidden: true });
  const items = options.map(([v, text, key, sub], i) => h("li", {
    role: "option", id: `${id}-${i}`, "data-value": v, class: sub ? "has-sub" : "",
    "aria-haspopup": sub ? "listbox" : null,
    onclick: (e) => { e.stopPropagation(); sub ? openSub(i, true) : choose(v); },
    onpointermove: () => { highlight(i); if (sub) openSub(i, false); else closeSub(); },
  }, h("span", { class: "icon-select-slot" }, key ? icon(key) : null), text,
     sub ? h("span", { class: "icon-select-more", "aria-hidden": "true" }, "›") : null));
  list.append(...items);

  // The open submenu: its list (a sibling of the main one, so the main list's scrolling
  // doesn't clip it), which option it belongs to, and its highlighted choice.
  const subList = h("ul", { class: "icon-select-list icon-select-sub", role: "listbox", id: `${id}-sub`,
                            tabindex: "-1", hidden: true, "aria-label": "" });
  let subOf = -1, subActive = 0, subItems = [];
  const root = h("div", { class: "icon-select", ...attrs }, button, list, subList);

  function render() {
    const [text, key] = choices.get(current);
    face.replaceChildren(h("span", { class: "icon-select-slot" }, key ? icon(key) : null), text);
    items.forEach((li, i) => {
      const sub = options[i][3];
      li.setAttribute("aria-selected", String(sub ? sub.some((c) => c[0] === current) : li.dataset.value === current));
    });
  }

  function highlight(i) {
    active = i;
    items.forEach((li, j) => li.classList.toggle("active", j === i));
    list.setAttribute("aria-activedescendant", items[i].id);
    items[i].scrollIntoView({ block: "nearest" });
  }

  function openSub(i, focus) {
    if (subOf !== i) {
      subOf = i;
      const [, text, , sub] = options[i];
      subList.setAttribute("aria-label", text);
      subItems = [];
      subList.replaceChildren(...sub.map((c) => {
        if (!Array.isArray(c)) return h("li", { class: "icon-select-heading", role: "presentation" }, c.heading);
        const li = h("li", {
          role: "option", id: `${id}-sub-${subItems.length}`, "data-value": c[0], "aria-selected": String(c[0] === current),
          onclick: (e) => { e.stopPropagation(); choose(c[0]); },
          onpointermove: ((n) => () => subHighlight(n))(subItems.length),
        }, c[2] ? h("span", { class: "icon-select-slot" }, icon(c[2])) : null, c[1]);
        subItems.push(li);
        return li;
      }));
      // Beside its option, kept inside the window.
      subList.hidden = false;
      subList.style.left = `${list.offsetLeft + list.offsetWidth + 4}px`;
      const top = list.offsetTop + items[i].offsetTop - list.scrollTop - 4;
      subList.style.top = `${top}px`;
      const overflow = subList.getBoundingClientRect().bottom - (window.innerHeight - 8);
      if (overflow > 0) subList.style.top = `${Math.max(list.offsetTop, top - overflow)}px`;
      subHighlight(Math.max(0, subItems.findIndex((li) => li.dataset.value === current)), !focus);
    }
    if (focus) { subList.focus(); subHighlight(subActive); }
  }

  function closeSub() {
    subOf = -1;
    subList.hidden = true;
  }

  function subHighlight(n, quiet = false) {
    if (!subItems.length) return;
    subActive = n;
    subItems.forEach((li, j) => li.classList.toggle("active", j === n && !quiet));
    subList.setAttribute("aria-activedescendant", subItems[n].id);
    if (!quiet) subItems[n].scrollIntoView({ block: "nearest" });
  }

  function open() {
    openMenu?.();
    list.hidden = false;
    button.setAttribute("aria-expanded", "true");
    highlight(Math.max(0, items.findIndex((li) => li.getAttribute("aria-selected") === "true")));
    list.focus();
    openMenu = close;
  }

  function close(focusButton = false) {
    list.hidden = true;
    closeSub();
    button.setAttribute("aria-expanded", "false");
    if (openMenu === close) openMenu = null;
    if (focusButton) button.focus();
  }

  function choose(v) {
    close(true);
    if (v === current) return;
    current = v;
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
    const sub = options[active][3];
    if (e.key === "ArrowDown") { highlight(Math.min(items.length - 1, active + 1)); closeSub(); }
    else if (e.key === "ArrowUp") { highlight(Math.max(0, active - 1)); closeSub(); }
    else if (e.key === "Home") { highlight(0); closeSub(); }
    else if (e.key === "End") { highlight(items.length - 1); closeSub(); }
    else if (sub && ["Enter", " ", "ArrowRight"].includes(e.key)) openSub(active, true);
    else if (e.key === "Enter" || e.key === " ") choose(options[active][0]);
    else if (e.key === "Escape" || e.key === "Tab") { close(e.key === "Escape"); return; }
    else if (e.key.length === 1) {
      const start = options.findIndex(([, text], i) => i > active && text.toLowerCase().startsWith(e.key.toLowerCase()));
      const i = start >= 0 ? start : options.findIndex(([, text]) => text.toLowerCase().startsWith(e.key.toLowerCase()));
      if (i >= 0) { highlight(i); closeSub(); }
      return;
    } else return;
    e.preventDefault();
  });
  subList.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") subHighlight(Math.min(subItems.length - 1, subActive + 1));
    else if (e.key === "ArrowUp") subHighlight(Math.max(0, subActive - 1));
    else if (e.key === "Home") subHighlight(0);
    else if (e.key === "End") subHighlight(subItems.length - 1);
    else if (e.key === "Enter" || e.key === " ") choose(subItems[subActive].dataset.value);
    else if (e.key === "ArrowLeft" || e.key === "Escape") { closeSub(); list.focus(); }
    else if (e.key === "Tab") { close(); return; }
    else if (e.key.length === 1) {
      const k = e.key.toLowerCase();
      const at = (li) => li.textContent.toLowerCase().startsWith(k);
      const next = subItems.findIndex((li, n) => n > subActive && at(li));
      const n = next >= 0 ? next : subItems.findIndex(at);
      if (n >= 0) subHighlight(n);
      return;
    } else return;
    e.preventDefault();
  });

  Object.defineProperty(root, "value", {
    get: () => current,
    set: (v) => { if (choices.has(v)) { current = v; render(); } },
  });
  render();
  return root;
}
