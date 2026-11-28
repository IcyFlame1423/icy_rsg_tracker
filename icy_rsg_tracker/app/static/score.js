// How a run's score was worked out (#score/<run_id>): the performance model's equation, the run's
// numbers bucket by bucket, and every variable with its value for this run.
import * as fmt from "./fmt.js";
import { $, getJSON, h, latestOnly, state } from "./common.js";
import { cutoffHead, cutoffRows, rankLabel, rankWithCutoffs } from "./ranks.js";

const fetchRun = latestOnly((id) =>
  getJSON(`/api/run?${new URLSearchParams({ instance: state.instance, run_id: id })}`));

/** Seconds, signed: "+564.7 s", "−12.3 s". */
export const signedSeconds = fmt.signedSeconds;
const secs = (s) => (s == null ? "–" : `${s.toFixed(1)} s`);
const num = (x, digits = 0) => (x == null ? "–" : (Math.round(x * 10 ** digits) / 10 ** digits).toLocaleString("en-US"));
const blocks = (x) => (x == null ? "unknown" : `${num(x)} blocks`);

// ---- Equation pieces ----
const v = (sym, sub, sup) => h("span", { class: "m-var" }, sym, sup != null ? h("sup", {}, sup) : null,
  sub != null ? h("sub", {}, sub) : null);
const op = (text) => h("span", { class: "m-op" }, text);
const frac = (top, bottom) => h("span", { class: "m-frac" }, h("span", { class: "m-num" }, top), h("span", { class: "m-den" }, bottom));
const sum = (lower, upper) => h("span", { class: "m-sum" }, h("span", { class: "m-lim" }, upper ?? ""),
  h("span", { class: "m-sigma" }, "Σ"), h("span", { class: "m-lim" }, lower));
const paren = (open, ...inner) => [h("span", { class: "m-paren" }, open), ...inner,
  h("span", { class: "m-paren" }, { "(": ")", "[": "]" }[open])];
const eq = (...parts) => h("div", { class: "m-eq", role: "math" }, parts);
const bar = (sym, sub) => h("span", { class: "m-var" }, h("span", { class: "m-bar" }, sym), h("sub", {}, sub));

export const scorePage = {
  id: "score",
  tab: "runs",
  usesWindow: () => false,
  init() {},
  async load(route) {
    const d = await fetchRun(route.runId);
    if (!d) return null;
    draw(d, route.runId);
    return "";
  },
};

function draw(d, runId) {
  const run = d.run;
  const name = run.world_number == null ? run.world_name : `World #${run.world_number}`;
  const back = $("score-back");
  back.href = `#run/${encodeURIComponent(runId)}`;
  back.textContent = `← ${name}`;
  $("score-title").textContent = `How ${name}'s score is worked out`;
  const sc = d.score;
  if (!sc) {
    $("score-body").replaceChildren(h("section", { class: "card spaced" },
      h("p", {}, "This run has no score. ", d.unscored_reason ?? "")));
    return;
  }
  $("score-body").replaceChildren(
    summaryCard(sc), equationCard(), bucketsCard(sc), variablesCard(sc), allowancesCard(sc), creditsCard());
}

const UNRANKED = "Not ranked: varies little with skill-level";

function summaryCard(sc) {
  return h("section", { class: "card spaced" },
    h("div", { class: "score-hero" },
      h("div", {}, h("div", { class: "label" }, "Score"), h("div", { class: "score-value" }, signedSeconds(sc.score))),
      h("div", {}, h("div", { class: "label" }, "Rank"),
        h("div", { class: "score-value" }, rankWithCutoffs(sc, "rank-icon-big"))),
      h("p", { class: "sub" }, "A typical top-player finish scores about +25 s. ",
        `A top player would have achieved an RTA of ${fmt.timeTenths(sc.buckets.reduce((t, b) => t + b.expected, 0) * 1000)}.`)));
}

/** The lost-time cutoffs for each rank in one part of the run (shown under its rows). */
function partCutoffs(part) {
  if (!part) return h("p", { class: "sub" }, `${UNRANKED}.`);
  const together = part.buckets.length > 1 ? ` (buckets ${part.buckets.join("–")} together)` : "";
  const end = part.part === "End" ? " The End is ranked on its whole RTA, not capped." : "";
  return h("div", { class: "part-cutoffs" },
    h("p", { class: "sub" }, `${part.name}${together}: the most each tier would take on this seed.${end}`),
    h("table", { class: "data-table score-table rank-cutoffs" },
      cutoffHead(["Rank", "× top player", "RTA at most", "Lost at most"]),
      h("tbody", {}, cutoffRows(part.cutoffs, part.rank,
        (c) => [`${c.ratio.toFixed(2)}×`, secs(c.rta), signedSeconds(c.lost)]))));
}

function equationCard() {
  const i = "i";
  const expected = [
    v("W", i), op("·"), frac([v("α", i), op("+"), v("β", i), v("d", i), v("g", i)], [v("α", i), op("+"), v("β", i), bar("d", i)]),
    op("+"), sum(h("span", {}, "k")), v("γ", "i,k"), v("x", "k"),
    op("+"), v("ζ"), ...paren("(", v("C"), op("−"), v("W", "10")), h("span", { class: "m-note" }, "(End only)"),
  ];
  return h("section", { class: "card spaced" },
    h("h2", {}, "The equation"),
    h("p", { class: "sub" }, "Fully expanded: the score adds up, over the ten buckets, the run's RTA minus the RTA a top player is expected to take on this seed with this run's resources."),
    eq(v("S"), op("="), sum(h("span", {}, "i = 1"), "10"), ...paren("[", v("t", i), op("−"), ...paren("(", ...expected))),
    h("p", { class: "sub" }, "The fraction is the seed difficulty ", v("f", i), ": how much longer this seed's distance takes than an average seed's. Buckets 3, 5, 7 and 8 are fitted on MCSR Ranked (bucket 8's distance is 8", v("n"), ", in overworld blocks). Buckets 1 and 2 use a travel speed instead: ",
      v("α", "i"), op("="), v("W", "i"), op("−"), v("β", "i"), bar("d", "i"), ", with ", v("β"),
      " 0.2 s/block (0.15 on shipwreck and buried treasure seeds) and ", bar("d", "i"),
      " the middle of the seed filter's range. It is 1 for buckets 4, 6, 9 and 10, and for structureless runs in buckets 1 and 2. For bucket 7 the numerator also has the drop luck ", v("L"), ":"),
    eq(v("f", "7"), op("="), frac([v("α", "7"), op("+"), v("L"), op("+"), v("β", "7"), v("n"), v("g", "7")], [v("α", "7"), op("+"), v("β", "7"), bar("n", "")]),
      op(","), op("  "), v("L"), op("="), v("β", null, "blaze"), ...paren("[", "max(0, ", v("k"), op("−"), v("k", "0"), ")", op("−"), "max(0, 2", v("r"), op("−"), v("k", "0"), ")")),
    h("p", { class: "sub" }, "The End depends on the explosives (beds and respawn anchors) at End enter, ", v("E"),
      ". With 3 or more a zero cycle or one cycle is expected: if the one cycle killed the dragon the End is capped at ",
      v("C"), " (a bad perch isn't punished), and if it missed the whole End counts. With 2 or fewer it takes more perches: ",
      "the top-player median ", v("M", "E"), " is expected, RTA up to the 90th percentile ", v("P", "E"),
      " is free (bad luck), and RTA past it counts again (a failed cycle):"),
    eq(v("t", "10"), op("="), h("span", { class: "m-cases" },
      h("span", {}, "min(", v("t", "End"), ", ", v("C"), ")", h("span", { class: "m-note" }, "E ≥ 3, one cycle hit")),
      h("span", {}, v("t", "End"), h("span", { class: "m-note" }, "E ≥ 3, one cycle missed")),
      h("span", {}, "min(", v("t", "End"), ", ", v("M", "E"), ")", op("+"), "max(0, ", v("t", "End"), op("−"), v("P", "E"), ")",
        h("span", { class: "m-note" }, "E ≤ 2")))),
    h("p", { class: "sub" }, "With 2 or fewer explosives the End's top-player RTA is ", v("M", "E"),
      " (no allowances); otherwise its expected RTA is never more than ", v("C"), ". The pearl shortage and zero cycle term are:"),
    eq(v("x", "pearl"), op("="), "min(18, max(0, 21 ", op("−"), v("p"), "))", op(","),
      v("ζ"), op("="), "0 if ", v("p"), " ≥ 3; 0.75 if ", v("p"), " = 2; 1 if ", v("p"), " ≤ 1"));
}

function bucketsCard(sc) {
  // Each part's rank, in its first bucket's row, spanning the part's buckets.
  const rankCell = (bucket) => {
    if (sc.unranked_buckets.includes(bucket)) {
      return h("td", { class: "muted", title: UNRANKED }, "Not ranked");
    }
    const part = sc.parts.find((p) => p.buckets.includes(bucket));
    if (!part || part.buckets[0] !== bucket) return null;  // spanned from the row above
    return h("td", { rowspan: String(part.buckets.length), class: "rank-cell",
                     title: `${part.name}: ${part.ratio.toFixed(2)}× a top player's time` }, rankLabel(part.rank));
  };
  // Clicking a bucket's row shows its part's cutoffs, under the part's last row.
  const partOf = (bucket) => sc.parts.find((p) => p.buckets.includes(bucket)) ?? null;
  const details = new Map();  // part (or unranked bucket) -> its cutoffs row
  const detailFor = (bucket) => {
    const part = partOf(bucket);
    const key = part ? part.part : `b${bucket}`;
    if (!details.has(key)) {
      details.set(key, h("tr", { class: "cutoffs-row", hidden: "" }, h("td", { colspan: "9" }, partCutoffs(part))));
    }
    return details.get(key);
  };
  const toggle = (bucket) => {
    const detail = detailFor(bucket);
    detail.hidden = !detail.hidden;
    const part = partOf(bucket);
    for (const tr of body.querySelectorAll("tr[data-bucket]")) {
      const b = Number(tr.dataset.bucket);
      if (part ? part.buckets.includes(b) : b === bucket) tr.setAttribute("aria-expanded", String(!detail.hidden));
    }
  };
  const rows = sc.buckets.map((b) => h("tr", {
    class: "clickable", tabindex: "0", "data-bucket": String(b.bucket), "aria-expanded": "false",
    title: "Show each rank's cutoff for this part",
    onclick: () => toggle(b.bucket),
    onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(b.bucket); } },
  },
    h("td", {}, h("span", { class: "expand-mark", "aria-hidden": "true" }), `${b.bucket}`), h("td", {}, b.name),
    h("td", { class: "num" }, secs(b.t)),
    h("td", { class: "num" }, secs(b.W)),
    h("td", { class: "num" }, b.f.toFixed(2)),
    h("td", { class: "num" }, b.allowance ? `+${b.allowance.toFixed(1)} s` : "–"),
    h("td", { class: "num" }, secs(b.expected)),
    h("td", { class: `num strong ${b.lost > 0 ? "behind" : "ahead"}` }, signedSeconds(b.lost)),
    rankCell(b.bucket)));
  const body = h("tbody", {}, sc.buckets.flatMap((b, k) => {
    const part = partOf(b.bucket);
    const last = !part || part.buckets[part.buckets.length - 1] === b.bucket;
    return last ? [rows[k], detailFor(b.bucket)] : [rows[k]];
  }));
  const terms = sc.buckets.map((b) => `(${b.t.toFixed(1)} − ${b.expected.toFixed(1)})`).join(" + ");
  return h("section", { class: "card spaced" },
    h("h2", {}, "This run, bucket by bucket"),
    h("p", { class: "sub" }, "Expected = top-player RTA × seed difficulty + allowances. Lost = the run's RTA − expected. ",
      "Rank: the best MCSR Ranked tier whose typical run this part matches or beats (its RTA ÷ the expected RTA; the End uncapped, against the End expected with the run's explosives and pearls). ",
      "Buckets 1–2 and 4–5 are ranked together; buckets 3 and 6 aren't ranked, since they vary little with skill-level. ",
      "Click a bucket to see each rank's cutoff for its part."),
    h("div", { class: "table-scroll" }, h("table", { class: "data-table score-table" },
      h("thead", {}, h("tr", {}, ["#", "Bucket", "RTA tᵢ", "Top player Wᵢ", "Difficulty fᵢ", "Allowances", "Expected T*ᵢ", "Lost tᵢ − T*ᵢ", "Rank"]
        .map((t, k) => h("th", { scope: "col", class: k > 1 && k < 8 ? "num" : "" }, t)))),
      body,
      h("tfoot", {}, h("tr", {}, h("td", {}), h("td", { class: "strong" }, "Score S"),
        h("td", { colspan: "5" }), h("td", { class: "num strong" }, signedSeconds(sc.score)),
        h("td", { class: "strong" }, rankLabel(sc.rank)))))),
    h("p", { class: "sub score-sum" }, "S = ", terms, ` = ${signedSeconds(sc.score)}`));
}

function variablesCard(sc) {
  const x = sc.inputs, c = sc.constants;
  const [a3, b3, d3bar] = c.fits["3"], [a5, b5, d5bar] = c.fits["5"], [a7, b7, nbar] = c.fits["7"];
  const row = (sym, meaning, value) => h("tr", {}, h("td", { class: "sym" }, sym), h("td", {}, meaning), h("td", {}, value));
  const lines = [
    row(v("S"), "The score: seconds lost against a top player on the same seed", signedSeconds(sc.score)),
    row(v("i"), "Bucket number, 1 to 10", "See the table above"),
    row(v("t", "i"), "RTA the run spent in bucket i. Each moment counts towards one bucket only", "See the table above"),
    row(v("W", "i"), "A top player's median RTA in bucket i on an average seed of the run's overworld type", "See the table above"),
    row(v("s"), "The run's last overworld structure, which sets W₁ and W₂",
      x.structure_name),
    row(v("d", "3"), "Straight-line distance from the nether portal to the first structure", blocks(x.d3)),
    row(v("d", "5"), "Straight-line distance from leaving the bastion to the fortress", blocks(x.d5)),
    row(v("d", "1"), "Straight-line distance from spawn to the seed-type structure", blocks(x.d1)),
    row(v("d", "2"), "Straight-line distance from leaving that structure to the nether portal", blocks(x.d2)),
    row([bar("d", "1"), ", ", bar("d", "2"), ", ", v("β", "1,2")], "Average spawn and portal distances for this seed type (the middle of the seed filter's ranges), and the overworld travel speed",
      x.ow_travel ? `${num(x.ow_travel[1] / 2)}, ${x.ow_travel[2] == null ? "–" : num(x.ow_travel[2] / 2)} blocks; ${x.ow_travel[0]} s/block` : "– (structureless)"),
    row(v("n"), "Nether straight-line distance from the fortress to the stronghold (overworld blocks ÷ 8)", blocks(x.n)),
    row(v("g", "i"), `Terrain for buckets 3, 5 and 7: how open the nether is along the route (% of blocks from y 30 to 90 that aren't solid, in the chunks the route crosses; for bucket 3 an open lava ocean counts as closed). Below ${c.terrain_cutoffs[0]}% is poor (×${c.terrain.poor} on the RTA per block), below ${c.terrain_cutoffs[1]}% average (×${c.terrain.average}), above that good (×${c.terrain.good})`,
      ["3", "5", "7"].map((b) => { const t = x.terrain[b]; return `${b}: ${t.open == null ? "–" : `${t.open}% ${t.level} ×${t.g}`}`; }).join("; ")),
    row([bar("d", "3"), ", ", bar("d", "5"), ", ", bar("n", "")], "Distances on an average seed: the middle of the assumed ranges (n̄: the median of the simulated stronghold distances)", `${num(d3bar)}, ${num(d5bar)}, ${num(nbar, 1)} blocks`),
    row([v("α", "3"), ", ", v("β", "3")], "Bucket 3's fixed RTA and RTA per block (fitted on Ranked)", `${a3} s, ${b3} s/block`),
    row([v("α", "5"), ", ", v("β", "5")], "Bucket 5's fixed RTA and RTA per block", `${a5} s, ${b5} s/block`),
    row([v("α", "7"), ", ", v("β", "7")], "Bucket 7's fixed RTA and RTA per block", `${a7} s, ${b7} s/block`),
    row([v("α", "8"), ", ", v("β", "8"), ", ", bar("d", "8")], "Bucket 8's fixed RTA, RTA per overworld block, and average fortress-to-stronghold distance (simulated from the seed filter and the first stronghold ring)",
      `${c.fits["8"][0]} s, ${c.fits["8"][1]} s/block, ${num(c.fits["8"][2])} blocks`),
    row([v("k"), ", ", v("r")], "Blazes killed and blaze rods obtained", x.kills == null ? "unknown" : `${num(x.kills)} blazes, ${num(x.rods)} rods`),
    row(v("k", "0"), "Stray blazes, killed around the fortress at no extra RTA", `${c.strays}`),
    row(v("β", null, "blaze"), "RTA per blaze killed at a spawner (4 per 25 s cycle)", `${c.blaze_s} s`),
    row(v("L"), "Drop luck: spawner blazes killed beyond 2 per rod, in seconds (positive = unlucky)", x.luck == null ? "unknown" : signedSeconds(x.luck)),
    row(v("f", "i"), "Seed difficulty for bucket i (1 = an average seed)", "See the table above"),
    row(v("p"), "Most ender pearls held at once", x.pearls == null ? "unknown" : num(x.pearls)),
    row(v("x", "pearl"), `Pearls short for travel (of ${c.comfortable_pearls}, down to 3)`, num(x.travel_short)),
    row(v("ζ"), "Chance a pearl shortage rules out a zero cycle", `${x.zeta}`),
    row(v("x", "k"), "Each resource shortage the run had (see below)", `${sc.shortages.filter((s) => s.x).length} of ${sc.shortages.length}`),
    row("Fire resistance", "Fire resistance potions obtained", x.fire_res == null ? "unknown" : num(x.fire_res)),
    row(v("E"), `Beds and respawn anchors usable at End enter, held or craftable (3 or 4 is a shortage; 2 or fewer means more perches)`, x.explosives == null ? "unknown" : num(x.explosives)),
    row("One cycle hit", "The dragon died within 30 s of the first bed or anchor blown up in the End",
      x.one_cycle_hit == null ? "unknown (counted as hit)" : x.one_cycle_hit ? "Yes" : "No"),
    row([v("M", "E"), ", ", v("P", "E")], "With 2 or fewer explosives: a top player's median End and its 90th percentile (2: two cycle; each explosive fewer adds a perch, 1:19)",
      x.multi_cycle ? `${secs(x.multi_cycle.median)}, ${secs(x.multi_cycle.p90)}` : "– (3 or more explosives)"),
    row("Iron pickaxe", "An iron (or better) pickaxe before the nether", x.iron_pick == null ? "unknown" : x.iron_pick ? "Yes" : "No"),
    row(v("γ", "i,k"), "Allowance for shortage k in bucket i (below)", "See below"),
    row(v("C"), "End cap when the one cycle is hit: a zero cycle not done by then counts as a one cycle", `${c.C} s`),
    row(v("t", "End"), "RTA in the End: the run's final RTA minus the RTA to End enter", secs(x.end_time)),
  ];
  return h("section", { class: "card spaced" },
    h("h2", {}, "Every variable"),
    h("div", { class: "table-scroll" }, h("table", { class: "data-table vars-table" },
      h("thead", {}, h("tr", {}, ["Symbol", "Meaning", "This run"].map((t) => h("th", { scope: "col" }, t)))),
      h("tbody", {}, lines))));
}

function allowancesCard(sc) {
  const buckets = [4, 5, 6, 7, 8, 9, 10];
  return h("section", { class: "card spaced" },
    h("h2", {}, "Resource allowances"),
    h("p", { class: "sub" }, "Seconds a top player is allowed in each bucket for each shortage (γ), and how much of each shortage this run had (x). The pearl column is per pearl short; the zero cycle term ζ is separate."),
    h("div", { class: "table-scroll" }, h("table", { class: "data-table score-table" },
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Shortage"), h("th", { scope: "col", class: "num" }, "This run x"),
        ...buckets.map((b) => h("th", { scope: "col", class: "num" }, `Bucket ${b}`)))),
      h("tbody", {}, sc.shortages.map((s) => h("tr", { class: s.x ? "" : "muted" },
        h("td", {}, s.name), h("td", { class: "num strong" }, num(s.x)),
        ...buckets.map((b) => h("td", { class: "num" }, s.gamma[b] ? `${s.gamma[b]} s` : "–"))))))));
}

function creditsCard() {
  const link = (href, text) => h("a", { href, target: "_blank", rel: "noopener" }, text);
  return h("section", { class: "card spaced" },
    h("h2", {}, "Where the numbers come from"),
    h("ul", { class: "credits" },
      h("li", {}, h("strong", {}, "Top-player times and seed difficulty: "),
        "the ", link("https://mcsrranked.com", "MCSR Ranked"), " public API. The 30 highest-rated players, 20 recent ranked matches each (4 per overworld seed type), with older matches and players ranked 31–70 held out to test the model."),
      h("li", {}, h("strong", {}, "Structureless overworld: "),
        "Couriway's 100K no-reset tracker. His nether entries on structure seeds set how far behind top players they are, which gives a top player's structureless RTA (2:59)."),
      h("li", {}, h("strong", {}, "Ranks: "),
        "590 completed ", link("https://mcsrranked.com", "MCSR Ranked"), " matches from the end of season 11: 10 per overworld seed type for each tier from Iron I to Netherite, ",
        "won by a player in the middle of the tier. A tier is a multiple of a top player's time (overall and for each part), fitted against Elo with a smooth curve, ",
        "so a longer seed gives every tier a longer time, not a fixed number of seconds more. ",
        "Tiers below Emerald don't get buried treasure seeds: those are their shipwreck runs with the overworld 0.82× as long (buried treasure ÷ shipwreck from Emerald up). ",
        "Top 30 level is the top-player sample itself; below Iron I is Coal."),
      h("li", {}, h("strong", {}, "End fight times: "),
        "T_Wagz's End fight time analysis: the two cycle and full bow distributions, for runs with 2 explosives or fewer.")),
    h("p", { class: "sub" }, "Resource allowances, bastion RTA, blaze cycles and distance ranges are estimates set by hand."));
}
