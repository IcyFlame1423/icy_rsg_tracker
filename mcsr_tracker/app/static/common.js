// Shared state and helpers for all pages.

export const SPLITS = [
  ["nether", "Nether"], ["bastion", "Bastion"], ["fortress", "Fortress"], ["blind", "Blind"],
  ["stronghold", "Stronghold"], ["end", "End"], ["finish", "Finish"],
];
export const SPLIT_NAMES = Object.fromEntries(SPLITS);
// Progression order. Bastion/fortress can come in either order, so it uses the first
// and second structure entered (computed on the server) to keep the order strict.
export const PROGRESSION = [
  ["nether", "Nether"], ["structure1", "Structure 1"], ["structure2", "Structure 2"], ["blind", "Blind"],
  ["stronghold", "Stronghold"], ["end", "End"], ["finish", "Finish"],
];

/** A run's in-game time for a split (nether..end, structure1/2, finish), or null.
 *  Same rules as stats.split_time on the server. */
export function splitTime(run, key) {
  if (key === "finish") return run.result === "finished" ? run.final_igt : null;
  if (key === "structure1" || key === "structure2") {
    const entered = [run.splits.bastion, run.splits.fortress].filter((t) => t != null).sort((a, b) => a - b);
    return entered[key === "structure1" ? 0 : 1] ?? null;
  }
  return run.splits[key] ?? null;
}

export const $ = (id) => document.getElementById(id);

// The URL can pick the window (e.g. /?window=all#runs), so views can be bookmarked.
const params = new URLSearchParams(location.search);
export const state = {
  instance: null,
  window: params.get("window") || localStorage.getItem("window") || "last_session",
  start: localStorage.getItem("rangeStart") || "",
  end: localStorage.getItem("rangeEnd") || "",
  version: null,
  textures: false,  // the game's textures were found, so split icons can be drawn
};

/** Query string for the current instance and time window, plus extra params. */
export function windowQuery(extra = {}) {
  const q = new URLSearchParams({ instance: state.instance, window: state.window });
  if (state.window === "custom") { q.set("start", state.start); q.set("end", state.end); }
  for (const [k, v] of Object.entries(extra)) q.set(k, v);
  return q;
}

export async function getJSON(url) {
  const res = await fetch(url);
  // An API the server doesn't know: the page was updated but the server is the old one.
  if (res.status === 404 && url.startsWith("/api/")) {
    throw new Error("The tracker running is an older version than this page. Close track.bat and start it again.");
  }
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || res.statusText);
  return body;
}

/** Tiny DOM builder. Children are nodes or strings (always inserted as text, never HTML). */
export function h(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (k in node && typeof v !== "string") node[k] = v;
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c != null && c !== false) node.append(c);
  return node;
}

export function tile(label, value, note) {
  return h("div", { class: "tile" },
    h("div", { class: "label" }, label),
    h("div", { class: "value" }, value),
    note ? h("div", { class: "note" }, note) : null);
}

/** plural(1, "nether") -> "1 nether", plural(1234, "run") -> "1,234 runs" */
export const plural = (n, word) => `${n.toLocaleString("en-US")} ${word}${n === 1 ? "" : "s"}`;

/** Runs a load function; drops results superseded by a newer call. */
export function latestOnly(fn) {
  let seq = 0;
  return async (...args) => {
    const mine = ++seq;
    const result = await fn(...args);
    return mine === seq ? result : undefined;
  };
}
