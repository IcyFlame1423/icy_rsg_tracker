// Overworld seed types (phases.PhaseTracker._seed_structure): names and a small 8x8 pixel-art
// icon for each, drawn here (not taken from the game) as an SVG.
import { h } from "./common.js";

export const SEED_TYPE_NAMES = {
  village: "Village", desert_pyramid: "Desert temple", ruined_portal: "Ruined portal",
  shipwreck: "Shipwreck", buried_treasure: "Buried treasure", none: "Structureless",
};

// Each picture: 8 rows of 8 characters; "." is transparent, any other a colour from its palette.
const ART = {
  village: {  // a house with a roof, a window and a door, on grass
    rows: ["...RR...", "..RRRR..", ".RRRRRR.", "RRRRRRRR", ".WGWWDW.", ".WWWWDW.", ".WWWWDW.", "CCCCCCCC"],
    colors: { R: "#8a4b2a", W: "#c8a46a", G: "#9fd3e6", D: "#5a3a1e", C: "#5f9e3c" },
  },
  desert_pyramid: {  // a stepped sandstone temple with orange bands and a dark entrance
    rows: ["...SS...", "..SOOS..", "..SSSS..", ".SOSSOS.", ".SSSSSS.", "SSSDDSSS", "SOSDDSOS", "YYYYYYYY"],
    colors: { S: "#e6d39a", O: "#d0702f", D: "#3a2614", Y: "#c9ad68" },
  },
  ruined_portal: {  // a broken obsidian frame, crying obsidian, a portal glow, netherrack and moss
    rows: ["..OOOK..", "..OPPO..", "..OPP...", "..KPPO..", "..OPPO..", "..OOOO.O", "NMNNMNON", "MSMMSMMS"],
    colors: { O: "#4b3a78", K: "#8e4fd8", P: "#c27af2", N: "#8c3333", M: "#5c7a2e", S: "#8a8a8a" },
  },
  shipwreck: {  // a mast with a torn sail on a broken hull, in water
    rows: ["...MS...", "...MSS..", "...MS.S.", "...M....", "HHHHHHH.", ".HHH.HH.", "WWHHHHWW", "WWWWWWWW"],
    colors: { M: "#5a3a1e", S: "#ece5cf", H: "#8b5a2f", W: "#3474b8" },
  },
  buried_treasure: {  // a chest with a gold latch, half buried in sand
    rows: ["........", ".BBBBBB.", "BCCCCCCB", "BLLGGLLB", "BCCGGCCB", "YYCCCCYY", "YYYYYYYY", "YYYYYYYY"],
    colors: { B: "#4a2d14", C: "#b07a34", L: "#6e4519", G: "#f4cb4a", Y: "#dcc583" },
  },
  none: {  // stone with iron ore: a structureless overworld means mining for iron
    rows: ["SSSSSSSS", "SSIISSDS", "SSIISSSS", "SDSSSSSS", "SSSSSIIS", "SSDSSIIS", "SSSSSSSS", "SIISDSSS"],
    colors: { S: "#8b8b8b", D: "#6a6a6a", I: "#d9ad8e" },
  },
};

const SVG = "http://www.w3.org/2000/svg";

/** The seed type's pixel-art icon as an <svg> (null for an unknown type). */
export function seedTypeIcon(type, size = 16) {
  const art = ART[type];
  if (!art) return null;
  const svg = document.createElementNS(SVG, "svg");
  for (const [k, v] of Object.entries({ viewBox: "0 0 8 8", width: size, height: size, class: "seed-type-icon",
                                        "shape-rendering": "crispEdges", "aria-hidden": "true" })) {
    svg.setAttribute(k, v);
  }
  art.rows.forEach((row, y) => {
    // One rect per run of same-coloured pixels.
    for (let x = 0; x < 8;) {
      let end = x;
      while (end < 8 && row[end] === row[x]) end++;
      if (row[x] !== ".") {
        const rect = document.createElementNS(SVG, "rect");
        for (const [k, v] of Object.entries({ x, y, width: end - x, height: 1, fill: art.colors[row[x]] })) {
          rect.setAttribute(k, v);
        }
        svg.append(rect);
      }
      x = end;
    }
  });
  return svg;
}

/** Icon and name together (e.g. for the run page and the runs table). */
export function seedTypeLabel(type) {
  if (!type) return null;
  return h("span", { class: "seed-type" }, seedTypeIcon(type), SEED_TYPE_NAMES[type] ?? type);
}
