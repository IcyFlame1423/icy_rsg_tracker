// App shell: page routing, the shared time-window filter, status bar and live refresh.
import * as fmt from "./fmt.js";
import { $, getJSON, h, state } from "./common.js";
import { blockImage, icon } from "./icons.js";
import { dashboard } from "./dashboard.js";
import { runsPage } from "./runs.js";
import { sessionsPage } from "./sessions.js";
import { runPage } from "./run.js";
import { splitsPage } from "./splits.js";
import { settingsPage } from "./settings.js";

const PAGES = { dashboard, runs: runsPage, run: runPage, sessions: sessionsPage, splits: splitsPage, settings: settingsPage };
const POLL_MS = 3000;

/** "#sessions/39" -> {page: sessionsPage, sessionId: "39"}; "#run/<id>" -> {page: runPage, runId} */
function parseRoute() {
  const [name, id] = location.hash.replace(/^#/, "").split("/");
  let page = PAGES[name] ?? dashboard;
  const runId = page === runPage && id ? decodeURIComponent(id) : null;
  if (page === runPage && !runId) page = runsPage;
  return { page, runId, sessionId: page === sessionsPage && /^\d+$/.test(id ?? "") ? id : null,
           hash: location.hash };
}

let route = null;

function show() {
  const previous = route;
  route = parseRoute();
  // Where the page was opened from (the run page's back link goes there).
  route.from = previous?.page === runPage ? previous.from : previous?.hash;
  for (const p of Object.values(PAGES)) {
    $(`page-${p.id}`).hidden = p !== route.page;
    const top = $(`top-${p.id}`);  // a page's section above the filter row
    if (top) top.hidden = !(p === route.page && (p.showsTop?.(route) ?? true));
  }
  const tab = route.page.tab ?? route.page.id;
  document.querySelectorAll(".tab").forEach((a) => {
    if (a.getAttribute("href") === `#${tab}`) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  $("window-filters").hidden = !route.page.usesWindow(route);
  if (previous?.page !== route.page) {
    $("page-filters").replaceChildren(...(route.page.filters?.() ?? []));
    $("window-note").textContent = "";
  }
  window.scrollTo(0, 0);
  load();
}

async function load() {
  if (!state.instance || !route) return;
  const r = route;
  const pageEl = $(`page-${r.page.id}`);
  pageEl.classList.add("loading");  // keep the old render, dimmed, while refetching
  try {
    const note = await r.page.load(r);
    if (note != null && r === route) $("window-note").textContent = note;
  } catch (e) {
    if (r === route) $("window-note").textContent = e.message;
  } finally {
    pageEl.classList.remove("loading");
  }
}

// ---- Status bar + live refresh ----

// This tab, to the tracker: it stops tracking once no dashboard tab is open.
const PAGE_ID = crypto.randomUUID?.() ?? String(Math.random()).slice(2);
let stopped = false;
window.addEventListener("pagehide", () => {
  if (stopped) return;
  fetch("/api/closed", { method: "POST", keepalive: true, headers: { "Content-Type": "application/json" },
                         body: JSON.stringify({ page: PAGE_ID }) }).catch(() => {});
});

/** Stop tracking: shut the tracker down, then close the tab (or say it can be closed). */
async function stopTracking() {
  if (!confirm("Stop tracking? Runs you play after this won't be added until you start the tracker again.")) return;
  stopped = true;
  try {
    await fetch("/api/stop", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  } catch { /* already gone */ }
  window.close();  // browsers only allow this for some tabs
  document.body.replaceChildren(h("main", { class: "stopped" },
    h("h1", {}, "Tracking stopped"),
    h("p", {}, "You can close this tab. To track again, start Icy RSG Tracker again; runs you play in " +
      "the meantime are added then.")));
}
$("stop-tracking").addEventListener("click", stopTracking);

function setStatus(kind, text) {
  $("status").dataset.state = kind;
  $("status").querySelector(".status-text").textContent = text;
}

async function pollStatus() {
  try {
    if (stopped) return;
    const st = await getJSON(`/api/status?page=${encodeURIComponent(PAGE_ID)}`);
    $("stop-tracking").hidden = !st.tracking;
    const iconsChanged = !!st.textures !== state.textures;
    state.textures = !!st.textures;
    if (iconsChanged || !$("app-logo").firstChild) {
      $("app-logo").replaceChildren(icon("logo") ?? "");
      blockImage("logo")?.then((url) => { document.querySelector('link[rel="icon"]').href = url; }, () => {});
    }
    syncInstances(st.instances);
    $("app-version").textContent = st.app_version ? `v${st.app_version}` : "";
    ongoing = st.ongoing ?? {};
    showSessionState();
    if (iconsChanged && route) {  // the game's files turned up (or went): redraw with(out) icons
      $("page-filters").replaceChildren(...(route.page.filters?.() ?? []));
      if (state.version != null) await load();
    }
    if (st.warning) setStatus("warning", st.warning);
    else if (st.setup) setStatus("warning", st.setup);
    else if (!st.tracking) setStatus("idle", "Not tracking (view only)");
    else setStatus("ok", st.last_import ? `Tracking · updated ${fmt.clock(st.last_import)}` : "Tracking");
    if (st.version !== state.version) {
      state.version = st.version;
      await load();
    }
  } catch {
    $("stop-tracking").hidden = true;
    setStatus("error", "Tracker not running. Start Icy RSG Tracker again to keep tracking.");
  }
}

let knownInstances = "";

let ongoing = {};

/** The "Last session" button: a green dot and "Ongoing session" while the latest session is still going. */
function showSessionState() {
  const live = !!ongoing[state.instance];
  const button = document.querySelector('#window [data-window="last_session"]');
  button.querySelector(".live-dot").classList.toggle("on", live);
  button.querySelector(".session-label").textContent = live ? "Ongoing session" : "Last session";
  button.title = live ? "The session you're playing now" : "No session going on now: your most recent one";
}

/** Keep the instance picker in step with the server's instances (they can change in Settings). */
function syncInstances(names) {
  if (names.join("\n") === knownInstances) return;
  knownInstances = names.join("\n");
  const wanted = state.instance ?? localStorage.getItem("instance");
  state.instance = names.includes(wanted) ? wanted : names[0];
  const select = $("instance");
  select.replaceChildren(...names.map((n) => new Option(n, n, false, n === state.instance)));
  select.closest("label").hidden = names.length < 2;
  showPlayer();
}

/** The instance's player in the top bar: username, and the head cut out of their skin. */
async function showPlayer() {
  const instance = state.instance;
  let who = null;
  try {
    who = (await getJSON(`/api/player?${new URLSearchParams({ instance })}`)).player;
  } catch { /* older server or no player: leave it hidden */ }
  if (instance !== state.instance) return;  // switched instance meanwhile
  $("player").hidden = !who;
  if (!who) return;
  $("player-name").textContent = who.name;
  $("player").title = `Playing as ${who.name}`;
  const head = $("player-head");
  head.hidden = true;  // until the skin loads; no head rather than a broken one
  const url = `/api/skin?${new URLSearchParams({ instance, v: who.uuid })}`;
  const img = new Image();
  img.onload = () => {
    if (instance !== state.instance) return;
    head.style.setProperty("--skin", `url("${url}")`);
    head.hidden = false;
  };
  img.src = url;
}

$("instance").addEventListener("change", (e) => {
  state.instance = e.target.value;
  localStorage.setItem("instance", state.instance);
  showSessionState();
  showPlayer();
  load();
});

// ---- Time window ----

function initWindowPicker() {
  const buttons = [...document.querySelectorAll("#window button")];
  const sync = () => {
    buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.window === state.window)));
    $("custom-range").hidden = state.window !== "custom";
  };
  buttons.forEach((b) => b.addEventListener("click", () => {
    state.window = b.dataset.window;
    localStorage.setItem("window", state.window);
    if (state.window === "custom" && !state.start) {
      const today = new Date();
      state.start = new Date(today - 6 * 864e5).toLocaleDateString("en-CA");
      state.end = today.toLocaleDateString("en-CA");
    }
    $("range-start").value = state.start;
    $("range-end").value = state.end;
    sync();
    load();
  }));
  for (const [id, key] of [["range-start", "start"], ["range-end", "end"]]) {
    $(id).value = state[key];
    $(id).addEventListener("change", (e) => {
      state[key] = e.target.value;
      localStorage.setItem(key === "start" ? "rangeStart" : "rangeEnd", state[key]);
      if (state.start && state.end) load();
    });
  }
  sync();
}

let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => route && route.page.onResize?.(route), 150);
});
window.addEventListener("hashchange", show);

for (const p of Object.values(PAGES)) p.init();
initWindowPicker();
show();
pollStatus();
setInterval(pollStatus, POLL_MS);
