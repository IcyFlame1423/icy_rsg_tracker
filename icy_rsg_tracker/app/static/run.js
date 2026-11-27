// One run (#run/<run_id>): its splits against your averages, its advancements, and where
// it sits in its session.
import * as fmt from "./fmt.js";
import { countedIcon, iconSlot, itemIcon, withIcon } from "./icons.js";
import { $, getJSON, h, latestOnly, PROGRESSION, state, tile } from "./common.js";
import { hideTooltip, showTooltip } from "./charts.js";
import { signedSeconds } from "./score.js";

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
    // The overworld/nether/stronghold/End cards open and close from their headings.
    for (const toggle of document.querySelectorAll(".phase-toggle")) {
      toggle.addEventListener("click", () => openPhase(toggle, toggle.getAttribute("aria-expanded") !== "true"));
    }
  },

  async load(route) {
    setBack(route.from);
    // They start closed each time a run is opened.
    for (const toggle of document.querySelectorAll(".phase-toggle")) openPhase(toggle, false);
    const d = await fetchRun(route.runId);
    if (!d) return null;
    detail = d;
    draw();
    return "";
  },
};

function openPhase(toggle, open) {
  toggle.setAttribute("aria-expanded", String(open));
  $(toggle.getAttribute("aria-controls")).hidden = !open;
}

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

/** A small button that copies text to the clipboard, and says so for a moment. */
function copyButton(text, label) {
  const button = h("button", { type: "button", class: "copy-button", "aria-label": label, title: label }, "Copy");
  button.addEventListener("click", async () => {
    let ok;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch {
      // Older way, for when the clipboard API isn't allowed.
      const area = h("textarea", { style: "position:fixed;opacity:0" }, text);
      document.body.append(area);
      area.select();
      ok = document.execCommand("copy");
      area.remove();
    }
    button.textContent = ok ? "Copied" : "Couldn't copy";
    clearTimeout(button.reset);
    button.reset = setTimeout(() => { button.textContent = "Copy"; }, 1500);
  });
  return button;
}

function draw() {
  const { run, session, times } = detail;
  $("run-title").textContent = worldName(run);
  $("run-seed").replaceChildren("Seed: ", ...(run.seed
    ? [h("code", {}, run.seed), copyButton(run.seed, "Copy seed")]
    : ["/seed was not run in the world"]));
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
    scoreTile(),
  );
  drawResources(run);
  drawPhases();
  drawDeaths(run);
  drawTables();
}

/** The run's score against a top player (finished Hermes runs only), linking to how it's worked out. */
function scoreTile() {
  const link = h("a", { href: `#score/${encodeURIComponent(detail.run.run_id)}` }, "How it's worked out →");
  return detail.score
    ? tile("Score", signedSeconds(detail.score.score), h("span", {}, "vs a top player · ", link))
    : tile("Score", "–", h("span", { title: detail.unscored_reason ?? "" }, "not scored · ", link));
}

// The items row: icon with the count in its corner, like the inventory.
const ITEMS = ["blaze_rods", "ender_pearls", "beds", "respawn_anchors", "fire_resistance", "obsidian"];
// What each count is, for its hover tooltip.
const ITEM_NAMES = {
  blaze_rods: "Blaze rods picked up from blazes",
  ender_pearls: "Most ender pearls held at once",
  beds: "Beds obtained (crafted or found)",
  respawn_anchors: "Respawn anchors obtained",
  fire_resistance: "Fire resistance potions obtained",
  obsidian: "Most obsidian held at once",
};

// The breakdown under each count in its tooltip: [detail name, what it means].
const ITEM_DETAILS = {
  blaze_rods: [["blazes_killed", "blazes killed"]],
  ender_pearls: [["pearls_used", "thrown before the End"], ["pearls_into_eyes", "crafted into eyes of ender"]],
  beds: [["beds_nether", "blown up in the nether (outside a fortress)"], ["beds_fortress", "blown up in a fortress"],
         ["beds_end", "used in the End"], ["beds_lost", "lost (left placed, or dropped and not picked up)"]],
  respawn_anchors: [["anchors_end", "used in the End"],
                    ["anchors_lost", "lost (blown up or left placed, or dropped and not picked up)"]],
  fire_resistance: [["fire_resistance_used", "drunk or thrown"]],
  obsidian: [["obsidian_bastion", "from inside a bastion"]],
};

/** Tooltip rows for an item: its count, then what happened to it. */
function itemRows(key, count) {
  const details = detail.item_details ?? {};
  const rows = [{ value: fmt.int(count), name: "in total", key: false }];
  for (const [name, text] of ITEM_DETAILS[key]) {
    if (details[name] != null) rows.push({ value: fmt.int(details[name]), name: text, key: false });
  }
  if (key === "obsidian" && details.diamond_pickaxe != null) {
    rows.push({ value: details.diamond_pickaxe ? "Yes" : "No", name: "diamond pickaxe", key: false });
  }
  return rows;
}

function drawResources(run) {
  const items = detail.items;
  const note = $("run-resources-note");
  if (!items) {
    // Counted from the Hermes mod's play log, which older runs don't have.
    $("run-resources").replaceChildren();
    note.textContent = "Item counts aren't available for this run: they come from the Hermes mod's play log, " +
      "and this run doesn't have one (it was played before Hermes was installed, or its world was deleted " +
      "before the tracker read it).";
    return;
  }
  $("run-resources").replaceChildren(...ITEMS.map((key) => {
    const count = items[key], name = ITEM_NAMES[key];
    const rows = itemRows(key, count);
    const tip = (x, y) => showTooltip(x, y, name, rows);
    // Without the game's textures, fall back to the number and its name.
    const art = countedIcon(key, count) ?? h("span", { class: "resource-text" }, fmt.int(count));
    const el = h("div", {
      class: "resource", tabindex: "0", "aria-label": `${name}: ${rows.map((r) => `${r.value} ${r.name}`).join(", ")}`,
      onpointermove: (e) => tip(e.clientX, e.clientY), onpointerleave: hideTooltip,
      onfocus: () => { const r = el.getBoundingClientRect(); tip(r.right, r.top); }, onblur: hideTooltip,
    }, art, state.textures ? null : h("span", { class: "resource-name", "aria-hidden": "true" }, name));
    return el;
  }));
  note.textContent = run.cheats_from_rta != null ? "Only counts what was obtained before the world was opened to LAN." : "";
}

// ---- Overworld, nether, stronghold, End (from the Hermes play log and ghost) ----------------

const STRUCTURE_NAMES = {
  buried_treasure: "Buried treasure", shipwreck: "Shipwreck", village: "Village", ruined_portal: "Ruined portal",
  desert_pyramid: "Desert temple", jungle_pyramid: "Jungle temple", ocean_ruin: "Ocean ruin",
  mineshaft: "Mineshaft", igloo: "Igloo", swamp_hut: "Witch hut", pillager_outpost: "Pillager outpost",
  monument: "Ocean monument", mansion: "Woodland mansion", stronghold: "Stronghold",
  bastion_remnant: "Bastion", fortress: "Fortress",
};
const lower = (s) => s.charAt(0).toLowerCase() + s.slice(1);

/** "spruce_planks" -> "Spruce planks", "splash_potion[fire_resistance]" -> "Splash potion of fire resistance". */
function itemName(id) {
  const [, base, potion] = id.match(/^([^[]+)(?:\[(.+)\])?$/) ?? [null, id];
  const name = base.replaceAll("_", " ");
  const text = potion ? `${name} of ${potion.replace(/^(long|strong)_/, "").replaceAll("_", " ")}` : name;
  return text.charAt(0).toUpperCase() + text.slice(1);
}
const structureName = (s) => STRUCTURE_NAMES[s] ?? itemName(s);

// [key, name, the item whose icon stands for it]
const RAW = [
  ["planks", "Planks", "oak_planks"], ["other_blocks", "Other blocks", "dirt"], ["iron", "Iron", "iron_ingot"],
  ["gold", "Gold", "gold_ingot"], ["diamonds", "Diamonds", "diamond"], ["cobblestone", "Cobblestone", "cobblestone"],
  ["food", "Food", "bread"],
];
const RAW_HELP = {
  planks: "Planks (logs count as 4, sticks as half; tools, boats and crafting tables as the planks in them)",
  other_blocks: "Other blocks (any block that isn't one of the others; beds aren't counted)",
  iron: "Iron (ingots, plus the iron in tools, buckets and armor: a bucket is 3)",
  gold: "Gold (ingots, plus the gold in tools and armor: a nugget is a ninth)",
  diamonds: "Diamonds (plus the diamonds in tools and armor)",
  cobblestone: "Cobblestone (plus the cobblestone in stone tools and furnaces)",
  food: "Food items",
};

const blocks = (n) => (n == null ? "–" : `${fmt.int(n)} ${n === 1 ? "block" : "blocks"}`);
const amount = (n) => (Number.isInteger(n) ? fmt.int(n) : fmt.num(n));

/** Show a tooltip while hovering or focusing an element. */
function withTip(el, title, rows) {
  if (!rows?.length) return el;
  const tip = (x, y) => showTooltip(x, y, title, rows);
  el.tabIndex = 0;
  el.addEventListener("pointermove", (e) => tip(e.clientX, e.clientY));
  el.addEventListener("pointerleave", hideTooltip);
  el.addEventListener("focus", () => { const r = el.getBoundingClientRect(); tip(r.right, r.top); });
  el.addEventListener("blur", hideTooltip);
  return el;
}
const tipTile = (label, value, note, title, rows) => withTip(tile(label, value, note), title, rows);

/** A tile with an item's picture on its right (left as it is without the game's textures). */
function art(tileNode, itemId) {
  const pic = itemIcon(itemId);
  if (pic) {
    tileNode.classList.add("has-art");
    tileNode.append(h("span", { class: "tile-art" }, pic));
  }
  return tileNode;
}
/** Two columns: main on the left, side (tiles) taking the rest of the width. */
const split = (main, side) => h("div", { class: "phase-split" },
  h("div", { class: "phase-main" }, main), h("div", { class: "phase-side" }, side));
const partRows = (parts) => Object.entries(parts ?? {}).map(([id, n]) => ({ value: fmt.int(n), name: itemName(id), key: false }));
const section = (title, ...body) => [h("h3", {}, title), ...body.filter((x) => x != null)];
const tiles = (...list) => h("div", { class: "tiles" }, list);
const nothing = (text) => h("p", { class: "sub" }, text);

function drawPhases() {
  const phases = detail.phases;
  const cards = ["overworld", "nether", "stronghold", "end"];
  for (const k of cards) $(`run-${k}-note`).textContent = "";
  if (!phases) {
    const why = detail.items
      ? "Not filled in yet for this run: use Settings → Rebuild from records."
      : "Not available for this run: this comes from the Hermes mod's play log, which this run doesn't have.";
    for (const k of cards) {
      $(`run-${k}`).replaceChildren();
      $(`run-${k}-note`).textContent = why;
    }
    return;
  }
  const notes = [];
  if (!phases.distances) notes.push("Distances need the Hermes ghost file, which this run doesn't have.");
  if (detail.run.cheats_from_rta != null) notes.push("Only counts what happened before the world was opened to LAN.");
  drawOverworld(phases.overworld);
  drawNether(phases.nether);
  drawStronghold(phases.stronghold);
  drawEnd();
  $("run-overworld-note").textContent = notes.join(" ");
  if (notes.length) $("run-nether-note").textContent = notes.join(" ");
}

function drawOverworld(ow) {
  const looted = ow.structures.filter((s) => s.looted);
  const visited = [...new Set(ow.structures.filter((s) => !s.looted).map((s) => structureName(s.structure)))];
  const body = section("Structures looted",
    looted.length
      ? h("ul", { class: "chips" }, looted.map((s) => h("li", { class: "chip" }, structureName(s.structure))))
      : nothing("None (no chest opened in a structure before the nether)."),
    visited.length ? h("p", { class: "sub" }, `Also went into (no chest opened): ${visited.join(", ")}.`) : null);
  if (!ow.materials) {
    body.push(nothing("Didn't enter the nether."));
  } else {
    const materials = section("Raw materials at nether enter", h("div", { class: "table-scroll" },
      h("table", { class: "data-table materials" },
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Material"), h("th", { scope: "col", class: "num" }, "Amount"))),
        h("tbody", {}, RAW.map(([k, label, icon]) => withTip(h("tr", {},
          h("td", {}, itemIcon(icon), label),
          h("td", { class: "num strong" }, amount(ow.materials[k]))), RAW_HELP[k], partRows(ow.materials_from?.[k])))))));
    const to = ow.to_nether;
    const travel = section("From the last structure to enter", to
      ? tiles(
        art(tile("Time", fmt.timeTenths(to.ms), `from leaving the ${lower(structureName(to.structure))}`), "clock"),
        art(tile("Distance", blocks(to.distance)), "oak_boat"))
      : nothing("No structure before the nether (ocean ruins don't count)."));
    body.push(split(materials, travel));
  }
  $("run-overworld").replaceChildren(...body);
}

function drawNether(ne) {
  if (detail.times.nether == null) {
    $("run-nether").replaceChildren(nothing("Didn't enter the nether."));
    return;
  }
  const to = ne.to_structure;
  const items = detail.items ?? {}, details = detail.item_details ?? {};
  const stats = tiles(
    art(to ? tile(`To the ${lower(structureName(to.structure))}`, blocks(to.distance), `Time: ${fmt.timeTenths(to.ms)}`)
      : tile("To the first structure", "–", "no bastion or fortress"), "leather_boots"),
    art(to ? tipTile("Blocks used on the way", fmt.int(to.blocks), null,
      "Blocks placed on the way to the first structure", partRows(to.blocks_from))
      : tile("Blocks used on the way", "–"), "dirt"),
    art(tile("Fortress to first rod", ne.first_rod_ms == null ? "–" : fmt.timeTenths(ne.first_rod_ms)), "nether_brick_fence"),
    art(tile("Blaze rate", details.blazes_killed ? `${fmt.int(items.blaze_rods)} / ${fmt.int(details.blazes_killed)}` : "–"),
      "blaze_rod"),
    art(ne.blind
      ? tile("Blind to stronghold portal", blocks(ne.blind.nether_distance),
        ne.blind.nether_distance ? `${blocks(ne.blind.nether_distance * 8)} in the overworld` : "the same portal")
      : tile("Blind to stronghold portal", "–"), "obsidian"),
  );
  $("run-nether").replaceChildren(ne.fortress_slots
    ? split(section("Inventory at fortress enter", inventory(ne.fortress_slots)), stats)
    : stats);
}

// Empty armor and offhand slots show the game's outline of what goes there.
const EMPTY_SLOT = { 39: "helmet", 38: "chestplate", 37: "leggings", 36: "boots", 40: "shield" };

/** The inventory laid out as the game shows it: armor and offhand, the 27 slots, the hotbar.
 *  slots: {slot number: [item id, count]}. Without the game's textures, a list instead. */
function inventory(slots) {
  if (!state.textures) {
    const totals = new Map();
    for (const [, [id, n]] of Object.entries(slots).sort((a, b) => a[0] - b[0])) totals.set(id, (totals.get(id) ?? 0) + n);
    return h("ul", { class: "chips" }, [...totals].map(([id, n]) =>
      h("li", { class: "chip" }, itemName(id), n > 1 ? h("span", { class: "count" }, `×${fmt.int(n)}`) : null)));
  }
  const slot = (i) => {
    const [id, n] = slots[i] ?? [];
    const el = h("div", { class: "inventory-slot", "aria-label": id ? `${itemName(id)} ×${n}` : null },
      id ? itemIcon(id, n)
        : EMPTY_SLOT[i] ? h("img", { class: "inventory-empty", alt: "", src: `/api/texture?name=item/empty_armor_slot_${EMPTY_SLOT[i]}` }) : null);
    return id ? withTip(el, itemName(id), [{ value: fmt.int(n), name: n === 1 ? "item" : "items", key: false }]) : el;
  };
  const row = (from, cls = "") => h("div", { class: `inventory-row ${cls}`.trim() },
    Array.from({ length: 9 }, (_, k) => slot(from + k)));
  return h("div", { class: "inventory", role: "img", "aria-label": "Inventory" },
    h("div", { class: "inventory-main" }, row(9), row(18), row(27), row(0, "hotbar")),
    h("div", { class: "inventory-side" },
      h("div", { class: "inventory-armor" }, [39, 38, 37, 36].map(slot)),
      slot(40)));
}

function drawStronghold(sh) {
  $("run-stronghold").replaceChildren(sh.eyes_placed == null
    ? nothing("Didn't enter a stronghold.")
    : tiles(art(tile("Eyes placed in the portal", fmt.int(sh.eyes_placed)), "ender_eye")));
}

function drawEnd() {
  const d = detail.item_details ?? {};
  $("run-end").replaceChildren(detail.times.end == null
    ? nothing("Didn't enter the End.")
    : tiles(art(tile("Beds used", fmt.int(d.beds_end)), "white_bed"),
      art(tile("Respawn anchors used", fmt.int(d.anchors_end)), "respawn_anchor")));
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
        h("td", { class: "num" }, fmt.time(a?.best_ms)),
        h("td", { class: "num" }, fmt.int(a?.count)));
    })));
}
