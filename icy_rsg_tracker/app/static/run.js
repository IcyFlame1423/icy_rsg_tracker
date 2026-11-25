// One run (#run/<run_id>): its splits against your averages, its advancements, and where
// it sits in its session.
import * as fmt from "./fmt.js";
import { countedIcon, iconSlot, withIcon } from "./icons.js";
import { $, getJSON, h, latestOnly, PROGRESSION, state, tile } from "./common.js";
import { hideTooltip, showTooltip } from "./charts.js";

const SPLIT_LABEL = Object.fromEntries(PROGRESSION);
const STRUCTURE_NAME = { bastion: "Bastion", fortress: "Fortress" };
// The diverging bar in "vs average" is full width at this fraction of the average.
const BAR_FULL = 0.25;

let compare = localStorage.getItem("runCompare") === "session" ? "session" : "all";
let detail = null;
const fetchRun = latestOnly((id) =>
  getJSON(`/api/run?${new URLSearchParams({ instance: state.instance, run_id: id })}`));

/** Signed difference: "-0:12.3" (faster) / "+0:04.0" (slower). */
function diff(ms) {
  const sign = ms < 0 ? "−" : "+";
  return sign + fmt.timeTenths(Math.abs(ms));
}

const worldName = (run) => (run.world_number == null ? run.world_name : `World #${run.world_number}`);

export const runPage = {
  id: "run",
  tab: "runs",  // highlighted in the tab bar
  usesWindow: () => false,

  init() {
    const buttons = [...document.querySelectorAll("#run-compare button")];
    const sync = () => buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.compare === compare)));
    buttons.forEach((b) => b.addEventListener("click", () => {
      compare = b.dataset.compare;
      localStorage.setItem("runCompare", compare);
      sync();
      if (detail) drawTables();
    }));
    sync();
  },

  async load(route) {
    setBack(route.from);
    const d = await fetchRun(route.runId);
    if (!d) return null;
    detail = d;
    draw();
    return "";
  },
};

/** "← Back to …" goes to where the run was opened from (default: the Runs page). */
function setBack(from) {
  const back = $("run-back");
  const [page, id] = (from ?? "").replace(/^#/, "").split("/");
  const label = { dashboard: "Dashboard", runs: "Runs", splits: "Splits" }[page];
  if (page === "sessions" && id) {
    back.href = from;
    back.textContent = `← Session ${id}`;
  } else if (label) {
    back.href = `#${page}`;
    back.textContent = `← ${label}`;
  } else {
    back.href = "#runs";
    back.textContent = "← Runs";
  }
}

function draw() {
  const { run, session, times } = detail;
  $("run-title").textContent = worldName(run);
  $("run-sub").replaceChildren(
    fmt.dateTime(run.date), " · ",
    h("a", { href: `#sessions/${session.id}` }, `Session #${session.id}`),
    ` · run ${fmt.int(session.position)} of ${fmt.int(session.runs)} played in it`);

  const steps = [];
  if (detail.previous_nether_run) {
    steps.push(h("a", { class: "button small", href: `#run/${encodeURIComponent(detail.previous_nether_run)}` },
      "← Previous nether run"));
  }
  if (detail.next_nether_run) {
    steps.push(h("a", { class: "button small", href: `#run/${encodeURIComponent(detail.next_nether_run)}` },
      "Next nether run →"));
  }
  $("run-steps").replaceChildren(...steps);

  const cheats = $("run-cheats");
  cheats.hidden = run.cheats_from_rta == null;
  cheats.textContent = run.cheats_from_rta == null ? "" :
    `Opened to LAN with cheats at ${fmt.time(run.cheats_from_rta)} real time. Splits and advancements after that aren't counted.`;

  const furthest = [...PROGRESSION].reverse().find(([k]) => times[k] != null);
  const reached = PROGRESSION.filter(([k]) => times[k] != null).length;
  $("run-tiles").replaceChildren(
    tile("Result", run.result === "finished" ? "Finished" : "Reset",
      run.result === "finished" ? "beat the game" : `at ${fmt.time(run.final_igt)}`),
    tile("In-game time", fmt.time(run.final_igt), run.result === "finished" ? "final time" : "when it was reset"),
    tile("Real time", fmt.time(run.final_rta), run.final_rta != null && run.final_igt != null
      ? `${fmt.timeTenths(Math.max(0, run.final_rta - run.final_igt))} more than in-game` : ""),
    tile("Furthest split", furthest ? withIcon(iconKey(furthest[0]), splitLabel(furthest[0])) : "None",
      `${reached} of ${PROGRESSION.length} splits`),
  );
  drawResources(run);
  drawDeaths(run);
  drawTables();
}

// The resources row: icon with the count in its corner, like the inventory.
const RESOURCES = ["blaze_rods", "ender_pearls", "beds", "respawn_anchors", "fire_resistance", "obsidian"];
// What each one means, for its hover tooltip.
const RESOURCE_NAMES = {
  blaze_rods: "Total blaze rods obtained in the run",
  ender_pearls: "Total ender pearls obtained in the run",
  beds: "Total white beds that could be made in the run",
  respawn_anchors: "Total respawn anchors that could be made in the run",
  fire_resistance: "Total fire resistance potions obtained in the run",
  obsidian: "Total obsidian obtained in the run",
};

function drawResources(run) {
  const res = detail.resources;
  $("run-resources-card").hidden = !res;
  if (!res) return;  // the record is gone, so there are no item statistics
  $("run-resources").replaceChildren(...RESOURCES.map((key) => {
    const { count, detail: text } = res[key];
    const name = RESOURCE_NAMES[key];
    // Only the beds and anchors have a worked-out detail worth showing ("10 white wool, ...").
    const rows = [{ value: fmt.int(count), name: "" }];
    if (key === "beds" || key === "respawn_anchors") rows.push({ value: "", name: text.split(": ")[1] ?? "" });
    const tip = (x, y) => showTooltip(x, y, name, rows);
    // Without the game's textures, fall back to the number and its name.
    const art = countedIcon(key, count) ?? h("span", { class: "resource-text" }, fmt.int(count));
    const el = h("div", {
      class: "resource", tabindex: "0", "aria-label": `${name}: ${count}`,
      onpointermove: (e) => tip(e.clientX, e.clientY), onpointerleave: hideTooltip,
      onfocus: () => { const r = el.getBoundingClientRect(); tip(r.right, r.top); }, onblur: hideTooltip,
    }, art, state.textures ? null : h("span", { class: "resource-name", "aria-hidden": "true" }, name));
    return el;
  }));
  const note = $("run-resources-note"), explainer = $("run-resources-explainer");
  const sentences = [];
  if (run.deaths) sentences.push("Because this run had at least 1 death, these counts are estimated.");
  if (run.cheats_from_rta != null) sentences.push("Includes anything collected after opening to LAN with cheats.");
  const parts = [sentences.join(" ")];
  if (run.deaths) {
    const more = h("button", { type: "button", class: "link", "aria-expanded": "false",
                               "aria-controls": "run-resources-explainer" }, "Learn more");
    more.addEventListener("click", () => {
      explainer.hidden = !explainer.hidden;
      more.setAttribute("aria-expanded", String(!explainer.hidden));
      more.textContent = explainer.hidden ? "Learn more" : "Show less";
    });
    parts.push(" ", more);
  }
  note.replaceChildren(...parts);
  explainer.hidden = true;
  explainer.replaceChildren(...(run.deaths ? explanation(run, res).filter(Boolean) : []));
}

/** How the counts are worked out, and why runs with deaths are only estimates. */
function explanation(run, res) {
  const n = run.deaths, divisor = res.pickup_divisor;
  const repicked = divisor - 1;  // deaths whose items were picked up again
  const thisRun = run.result === "finished"
    ? `This run had ${n === 1 ? "1 death" : `${n} deaths`} and was finished, so items are counted as picked up ` +
      `again after ${n === 1 ? "it" : "each of them"}.`
    : n === 1
      ? "This run had 1 death and was reset, so nothing is counted as picked up again."
      : `This run had ${n} deaths and was reset, so items are counted as picked up again after ${repicked === 1 ? "the first" : `the first ${repicked}`}.`;
  const times = run.death_times?.length
    ? ` The game log places ${n === 1 ? "the death" : "the deaths"} at ${run.death_times.map(fmt.time).join(", ")} (in-game).`
    : "";
  return [
    h("h3", {}, "How these are counted"),
    h("p", {}, "The counts come from the game's item statistics, which SpeedRunIGT saves with each run: items " +
      "picked up, minus items you dropped. Beds and respawn anchors are what the materials you collected could make " +
      "(beds: 3 wool of one colour and 3 planks, with 4 string making a white wool; anchors: 6 crying obsidian and " +
      "3 glowstone). Where the game shows you crafted more than your pickups explain, the crafted amount is used."),
    h("h3", {}, "Why deaths make them estimates"),
    h("p", {}, "When you die, your items drop, and picking them back up counts them as picked up again. The game " +
      "only keeps totals for the whole run, not when each item was picked up, so the extra pickups can't be found " +
      "exactly. Instead, it's assumed that everything you'd collected was in your inventory at each death, except " +
      "what you'd used up by then:"),
    h("ul", {},
      h("li", {}, "Finished: you picked your items back up after every death."),
      h("li", {}, "Reset: you picked them back up after every death but the last (with 1 death, never).")),
    h("p", {}, "Each time you pick your items back up, you pick up what you'd collected minus what you'd used, so " +
      "collected = (pickups + used before each of those deaths) ÷ (1 + those deaths). With nothing used, that's " +
      "the pickups divided by 1 + those deaths."),
    h("p", {}, thisRun + times),
    h("h3", {}, "What's assumed used up before a death"),
    h("ul", {},
      h("li", {}, "Obsidian: 10 placed once past the blind (the blind portal), 20 once in the stronghold."),
      h("li", {}, "Fire resistance: one potion kept active from a minute before entering the fortress until the " +
        "stronghold, each lasting 3:00 (drinkable and splash alike), so a potion per 3:00 of that stretch by the death."),
      h("li", {}, "Ender pearls: 2 between the first and second structures, and 2 between the blind and the " +
        "stronghold; 1 for a stretch a death came partway through."),
      h("li", {}, "Respawn anchor materials: a death reset in the nether (between entering it and the blind) " +
        "means a respawn anchor was placed and left behind, so 6 crying obsidian and 3 glowstone (12 dust) each, " +
        "from that death on."),
      h("li", {}, "Blaze rods: a run that entered the End must have had at least 6 (for 12 eyes of ender), so " +
        "the estimate is never below 6 for those runs."),
      h("li", {}, "Everything else: nothing.")),
    run.death_times?.length ? null : h("p", {}, "This run's deaths couldn't be placed in the game log, so nothing is " +
      "assumed used: pickups are simply divided by " + divisor + "."),
    h("h3", {}, "What can make them wrong"),
    h("ul", {},
      h("li", {}, "Anything you first got after a death is counted as picked up again too, so it reads low."),
      h("li", {}, "If you didn't go back for your items after a death (or went back after the last one before " +
        "resetting), the counts read low (or high)."),
      h("li", {}, "Items stored in a chest before a death don't drop, so they aren't picked up again, and the " +
        "estimate reads low for them."),
      h("li", {}, "Items used up before a death beyond the assumptions above (more pearls thrown, a potion " +
        "wasted, obsidian placed elsewhere) shift the estimate: it reads low for them."),
      h("li", {}, "Items taken straight out of a chest aren't in the game's statistics at all, unless you crafted " +
        "something from them."),
      h("li", {}, "All potions are counted as fire resistance, the only ones piglins barter."),
      h("li", {}, "Crafted amounts aren't affected by deaths, so they're used as they are.")),
  ];
}

function drawDeaths(run) {
  const known = run.deaths_with_respawn != null || run.deaths === 0;
  const count = (n) => (run.deaths === 0 ? "0" : known ? fmt.int(n) : "–");
  $("run-deaths").replaceChildren(
    tile("Deaths", fmt.int(run.deaths)),
    tile("With spawn point", count(run.deaths_with_respawn), "respawned at a bed or anchor"),
    tile("Accidental", count(run.deaths_without_respawn), "sent back to world spawn"),
  );
  $("run-deaths-note").textContent = run.deaths && !known
    ? "The game log didn't match the death count, so these deaths couldn't be told apart." : "";
}

/** The icon for a split in this run: structure 1/2 use the structure it actually was. */
function iconKey(key) {
  const i = { structure1: 0, structure2: 1 }[key];
  return i == null ? key : detail.structures[i];
}

/** "Structure 1 (Bastion)" for this run's structures, else the plain split name. */
function splitLabel(key) {
  const i = { structure1: 0, structure2: 1 }[key];
  const which = i == null ? null : detail.structures[i];
  return which ? `${SPLIT_LABEL[key]} (${STRUCTURE_NAME[which]})` : SPLIT_LABEL[key];
}

/** The signed difference with a small bar: left/green = faster, right/red = slower. */
function vsCell(ms, avg) {
  if (ms == null || avg == null) return h("span", { class: "muted" }, "–");
  const delta = ms - avg;
  const width = Math.min(1, Math.abs(delta) / avg / BAR_FULL) * 50;
  const kind = delta <= 0 ? "ahead" : "behind";
  return h("span", { class: `vs ${kind}`, title: `${fmt.pct(Math.abs(delta) / avg)} ${delta <= 0 ? "faster" : "slower"} than average` },
    h("span", { class: "vs-text" }, diff(delta)),
    h("span", { class: "vs-bar", "aria-hidden": "true" },
      h("span", { class: "vs-fill", style: delta <= 0 ? `right:50%;width:${width}%` : `left:50%;width:${width}%` })));
}

function drawTables() {
  const base = detail.compare[compare];
  const times = detail.times;
  $("run-compare-note").textContent = compare === "all"
    ? `Compared with all ${fmt.int(base.runs)} runs you've played.`
    : `Compared with the ${fmt.int(base.runs)} runs in session #${detail.session.id}, including this one.`;

  const head = ["Split", "Time", "Segment", "Average", "vs average", "Segment average"];
  const rows = PROGRESSION.map(([key], i) => {
    const t = times[key], s = base.splits[key];
    const prev = i ? times[PROGRESSION[i - 1][0]] : null;
    const segment = i === 0 ? t : t != null && prev != null ? t - prev : null;
    const segAvg = i === 0 ? s.avg_ms : s.segment_avg_ms;
    const muted = t == null ? " muted" : "";
    return h("tr", {},
      h("td", { class: muted.trim() }, iconSlot(iconKey(key)), splitLabel(key)),
      h("td", { class: "num strong" + muted }, fmt.time(t)),
      h("td", { class: "num" + muted }, segment == null ? "–" : fmt.timeTenths(segment)),
      h("td", { class: "num" }, fmt.timeTenths(s.avg_ms)),
      h("td", { class: "num" }, vsCell(t, s.avg_ms)),
      h("td", { class: "num" }, segAvg == null ? "–" : h("span", {}, fmt.timeTenths(segAvg),
        segment != null && i ? h("span", { class: `delta ${segment <= segAvg ? "ahead" : "behind"}` }, diff(segment - segAvg)) : null)));
  });
  $("run-splits").replaceChildren(
    h("thead", {}, h("tr", {}, head.map((text, i) => h("th", { scope: "col", class: i ? "num" : "" }, text)))),
    h("tbody", {}, rows));

  drawAdvancements(base);
}

function drawAdvancements(base) {
  const { run, advancement_names: names } = detail;
  const earned = Object.entries(run.advancements).sort((a, b) => a[1] - b[1]);
  $("run-adv-note").textContent = earned.length
    ? `${earned.length} earned this run, in the order you got them.`
    : "No advancements this run.";
  $("run-advancements").hidden = !earned.length;
  if (!earned.length) return;
  const runsWord = compare === "all" ? "Runs with it" : "Runs with it (session)";
  $("run-advancements").replaceChildren(
    h("thead", {}, h("tr", {}, ["Advancement", "Time", "Average", "vs average", "Best", runsWord]
      .map((text, i) => h("th", { scope: "col", class: i ? "num" : "" }, text)))),
    h("tbody", {}, earned.map(([id, ms]) => {
      const a = base.advancements[id];
      return h("tr", {},
        h("td", { title: id }, iconSlot(`adv:${id}`), names[id] ?? id),
        h("td", { class: "num strong" }, fmt.time(ms)),
        h("td", { class: "num" }, fmt.timeTenths(a?.avg_ms)),
        h("td", { class: "num" }, vsCell(ms, a?.avg_ms)),
        h("td", { class: "num" }, fmt.time(a?.best_ms), a && ms === a.best_ms ? h("span", { class: "pb" }, compare === "all" ? "PB" : "Best") : null),
        h("td", { class: "num" }, fmt.int(a?.count)));
    })));
}
