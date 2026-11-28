// Rank tiers (model.RANKS) and how they're shown: the tier's material from the game's own
// textures (coal, iron ingot, gold ingot, emerald, diamond, netherite ingot), with the tier
// number (I, II, III) as the stack count. Without the game's textures, just the name.
import * as fmt from "./fmt.js";
import { h } from "./common.js";
import { itemIcon } from "./icons.js";

const MATERIAL = {
  Coal: "coal", Iron: "iron_ingot", Gold: "gold_ingot",
  Emerald: "emerald", Diamond: "diamond", Netherite: "netherite_ingot",
  "Top 30": "nether_star",
};
const NUMBER = { I: 1, II: 2, III: 3 };

/** "Gold III" -> a gold ingot with 3 on it. */
export function rankIcon(rank, className = "") {
  const [family, tier] = rank === "Top 30" ? [rank, null] : rank.split(" ");
  const id = MATERIAL[family];
  return id ? itemIcon(id, NUMBER[tier] ?? 1, { className: `rank-icon ${className}`.trim(), showOne: tier === "I" }) : null;
}

/** "Top 30" reads as "Top 30 level"; tiers as they are. */
export function rankName(rank) {
  return rank === "Top 30" ? "Top 30 level" : rank;
}

/** Icon and name together. */
export function rankLabel(rank, className = "") {
  return h("span", { class: "rank-label" }, rankIcon(rank, className), rankName(rank));
}

/** "The model predicts that the run was as good as a run by an Emerald I player." */
export function rankSentence(rank) {
  const lead = "The model predicts that the run was";
  if (rank === "Coal") return `${lead} below a typical Iron I run (Coal level).`;
  if (rank === "Top 30") return `${lead} as good as a run by a top 30 player.`;
  const article = /^[AEIOU]/.test(rank) ? "an" : "a";  // an Iron I, an Emerald II
  return `${lead} as good as a run by ${article} ${rank} player.`;
}

/** Rows of a rank cutoff table, best first, Coal last; the run's own rank highlighted.
 *  cells(cutoff) -> the texts after the rank. */
export function cutoffRows(cutoffs, current, cells) {
  const rows = [...cutoffs].reverse().map((c) => h("tr", { class: c.rank === current ? "current" : "" },
    h("td", {}, rankLabel(c.rank)), ...cells(c).map((text) => h("td", { class: "num" }, text))));
  const iron = cutoffs[0];
  rows.push(h("tr", { class: current === "Coal" ? "current" : "" }, h("td", {}, rankLabel("Coal")),
    ...cells(iron).map((text) => h("td", { class: "num muted" }, `over ${text}`))));
  return rows;
}

export const cutoffHead = (names) => h("thead", {}, h("tr", {},
  names.map((t, k) => h("th", { scope: "col", class: k ? "num" : "" }, t))));

/** The run's rank; hovering it (or focusing it) shows each rank's cutoff on this seed.
 *  sc: the run's score (model.score). */
export function rankWithCutoffs(sc, className = "") {
  return h("span", { class: "rank-hover", tabindex: "0", "aria-label": `${rankName(sc.rank)}: show each rank's cutoff on this seed` },
    rankLabel(sc.rank, className),
    h("div", { class: "rank-popover", role: "tooltip" },
      h("div", { class: "rank-popover-title" }, "Rank cutoffs on this seed"),
      h("table", { class: "data-table rank-cutoffs" },
        cutoffHead(["Rank", "× top player", "RTA at most", "Score at most"]),
        h("tbody", {}, cutoffRows(sc.cutoffs, sc.rank,
          (c) => [`${c.ratio.toFixed(2)}×`, fmt.timeTenths(c.rta * 1000), fmt.signedSeconds(c.score)])))));
}
