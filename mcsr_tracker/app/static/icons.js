// Minecraft icons, drawn from textures in the player's own game files (served by
// /api/texture). Items are the flat 16x16 picture; blocks, the fence and the dragon head
// are drawn as small 3D shapes the way the inventory shows them.
import { h, state } from "./common.js";

// Box shapes in block pixels (0-16): [[x0, y0, z0], [x1, y1, z1]], drawn back to front.
const CUBE = [[[0, 0, 0], [16, 16, 16]]];
// The fence's inventory model: two posts joined by two rails. The rails are cut where
// they pass through the posts so the pieces can be drawn back to front.
const rails = (z0, z1) => [[[7, 5, z0], [9, 7, z1]], [[7, 12, z0], [9, 15, z1]]];
const FENCE = [
  ...rails(-2, 0),
  [[6, 0, 0], [10, 16, 4]],    // back post
  ...rails(4, 12),
  [[6, 0, 12], [10, 16, 16]],  // front post
  ...rails(16, 18),
];

// The dragon head: Minecraft's model for it (in entity units, y pointing down, snout
// towards -z), each box with its spot [u, v] on the 256x256 dragon texture.
const DRAGON_HEAD = [
  // [x, y, z, width, height, depth, u, v]
  [-8, -8, -10, 16, 16, 16, 112, 30],  // head
  [-5, -12, -4, 2, 4, 6, 0, 0],        // scales on top
  [3, -12, -4, 2, 4, 6, 0, 0],
  [-6, 4, -24, 12, 4, 16, 176, 65],    // lower jaw
  [-6, -1, -24, 12, 5, 16, 176, 44],   // upper jaw
  [-5, -3, -22, 2, 2, 4, 112, 0],      // nostrils
  [3, -3, -22, 2, 2, 4, 112, 0],
];

// A bed as the inventory shows it: head and foot halves of the mattress on four short legs,
// from the 64x64 bed texture. Faces: [u, v, width, height]; "turned" side faces have the
// texture's long side running along the bed. Listed back to front.
const leg = (x, z) => ({ a: [x, 0, z], b: [x + 3, 3, z + 3], top: null, front: [53, 3, 3, 3], side: [53, 3, 3, 3] });
const BED = [
  leg(0, 0), leg(13, 0),
  { a: [0, 3, 0], b: [16, 9, 16], top: [6, 6, 16, 16], front: null, side: [22, 6, 6, 16], turned: true },
  leg(0, 29), leg(13, 29),
  { a: [0, 3, 16], b: [16, 9, 32], top: [6, 28, 16, 16], front: [22, 22, 16, 6], side: [22, 28, 6, 16], turned: true },
];

/** What each icon is. top/side: block textures for the shape's faces; model: entity boxes
 *  on one texture. */
const ICONS = {
  nether: { item: "item/flint_and_steel", title: "Flint and steel" },
  bastion: { shape: CUBE, top: "block/blackstone_top", side: "block/blackstone", title: "Blackstone" },
  fortress: { shape: FENCE, top: "block/nether_bricks", side: "block/nether_bricks", title: "Nether brick fence" },
  stronghold: { item: "item/ender_eye", title: "Eye of ender" },
  end: { shape: CUBE, top: "block/end_stone", side: "block/end_stone", title: "End stone" },
  // Structure 1/2 (either bastion or fortress): a compass with an inventory stack count.
  structure1: { item: "item/compass_00", count: 1, title: "Compass (structure 1)" },
  structure2: { item: "item/compass_00", count: 2, title: "Compass (structure 2)" },
  blind: { shape: CUBE, top: "block/obsidian", side: "block/obsidian", title: "Obsidian" },
  finish: { model: DRAGON_HEAD, texture: "entity/enderdragon/dragon", title: "Dragon head" },
  // Not splits: "any split" in the Reached filter, and the dashboard's tiles.
  any: { item: "item/paper", title: "Paper" },
  runs: { item: "item/golden_boots", title: "Golden boots" },
  resets: { item: "item/barrier", title: "Barrier" },
  clock: { item: "item/clock_00", title: "Clock" },
  netherrack: { shape: CUBE, top: "block/netherrack", side: "block/netherrack", title: "Netherrack" },
  // A run's resources (run page).
  blaze_rods: { item: "item/blaze_rod", title: "Blaze rods" },
  ender_pearls: { item: "item/ender_pearl", title: "Ender pearls" },
  beds: { parts: BED, texture: "entity/bed/white", title: "White beds" },
  respawn_anchors: { shape: CUBE, top: "block/respawn_anchor_top_off", side: "block/respawn_anchor_side0",
                     title: "Respawn anchors" },
  fire_resistance: { item: "mob_effect/fire_resistance", title: "Fire resistance" },
  obsidian: { shape: CUBE, top: "block/obsidian", side: "block/obsidian", title: "Obsidian" },
};

const textureUrl = (name) => `/api/texture?${new URLSearchParams({ name })}`;
const images = new Map();    // texture name -> Promise<Image>
const rendered = new Map();  // icon key -> Promise<data URL>

function loadImage(name) {
  if (!images.has(name)) {
    images.set(name, new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = textureUrl(name);
    }));
  }
  return images.get(name);
}

// Isometric axes on screen, per block pixel: x runs right-down, z left-down, y up.
const C = Math.cos(Math.PI / 6);
const AXIS = { x: [C, 0.5], y: [0, -1], z: [-C, 0.5] };
const project = ([x, y, z]) => [x * AXIS.x[0] + z * AXIS.z[0], x * AXIS.x[1] + y * AXIS.y[1] + z * AXIS.z[1]];
const clamp = (v) => Math.min(16, Math.max(0, v));

/** The icon's picture: the item texture, or its 3D shape drawn onto a canvas. */
async function baseImage(def) {
  if (def.item) return loadImage(def.item);
  const url = await renderShape(def);
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = url;
  });
}

/** An icon with a stack count in its corner, drawn the way the inventory does it: the
 *  game's own font, white with a dark shadow, right-aligned at the bottom right. */
async function renderCounted(def, count, px = 4) {
  const [item, font] = await Promise.all([baseImage(def), loadImage("font/ascii")]);
  const cell = font.width / 16;  // ascii.png: 16x16 glyphs
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 18 * px;  // the item (16) plus room for the number's shadow
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(item, 0, 0, 16 * px, 16 * px);

  const text = String(count);
  const glyphs = [...text].map((ch) => {
    const code = ch.charCodeAt(0), gx = (code % 16) * cell, gy = Math.floor(code / 16) * cell;
    // A glyph's width: up to its rightmost non-blank column.
    const scan = document.createElement("canvas");
    scan.width = scan.height = cell;
    const sctx = scan.getContext("2d");
    sctx.drawImage(font, gx, gy, cell, cell, 0, 0, cell, cell);
    const data = sctx.getImageData(0, 0, cell, cell).data;
    let width = 0;
    for (let x = 0; x < cell; x++) for (let y = 0; y < cell; y++) if (data[(y * cell + x) * 4 + 3]) width = x + 1;
    return { gx, gy, width: width * 8 / cell };
  });
  const total = glyphs.reduce((sum, g) => sum + g.width + 1, 0);
  // Tinted copies of the glyphs: shadow (#3f3f3f) one pixel down-right, then white.
  for (const [color, shift] of [["#3f3f3f", 1], ["#ffffff", 0]]) {
    const layer = document.createElement("canvas");
    layer.width = layer.height = 18 * px;
    const lctx = layer.getContext("2d");
    lctx.imageSmoothingEnabled = false;
    let x = 17 - total;  // as in the game: the number ends at the slot's right edge
    for (const g of glyphs) {
      lctx.drawImage(font, g.gx, g.gy, cell, cell, (x + shift) * px, (9 + shift) * px, 8 * px, 8 * px);
      x += g.width + 1;
    }
    lctx.globalCompositeOperation = "source-in";
    lctx.fillStyle = color;
    lctx.fillRect(0, 0, layer.width, layer.height);
    ctx.drawImage(layer, 0, 0);
  }
  return canvas.toDataURL();
}

/** The boxes to draw, each with the texture area for its three visible faces:
 *  {a: [x0, y0, z0], b: [x1, y1, z1], top, front, side: [image, [u, v, width, height]]}. */
async function boxes(def) {
  if (def.parts) {  // boxes with their own texture areas, already in drawing order
    const tex = await loadImage(def.texture);
    const area = (rect) => (rect ? [tex, rect] : null);
    return def.parts.map((p) => ({ ...p, top: area(p.top), front: area(p.front), side: area(p.side) }));
  }
  if (def.model) {
    const tex = await loadImage(def.texture);
    // Flip y (models point down) and z (so the snout faces the viewer), then draw back to front.
    return def.model.map(([x, y, z, w, h, d, u, v]) => ({
      a: [x, -(y + h), -(z + d)], b: [x + w, -y, -z],
      top: [tex, [u + d, v, w, d]], front: [tex, [u + d, v + d, w, h]], side: [tex, [u + d + w, v + d, d, h]],
    })).sort((p, q) => p.a[2] - q.a[2] || p.a[1] - q.a[1]);
  }
  const [top, side] = await Promise.all([loadImage(def.top), loadImage(def.side)]);
  return def.shape.map(([a, b]) => {
    // Texture areas follow the box's position in the block, as Minecraft maps them.
    const [x0, y0, z0] = a.map(clamp), [x1, y1, z1] = b.map(clamp);
    return { a, b, top: [top, [x0, z0, x1 - x0, z1 - z0]], front: [side, [x0, 16 - y1, x1 - x0, y1 - y0]],
             side: [side, [16 - z1, 16 - y1, z1 - z0, y1 - y0]] };
  });
}

/** Draw a shape onto a size x size canvas: top, front-left (+z) and front-right (+x)
 *  faces, shaded like the inventory (top brightest). */
async function renderShape(def, size = 64) {
  const parts = await boxes(def);
  const corners = parts.flatMap(({ a, b }) => [a[0], b[0]].flatMap((x) => [a[1], b[1]]
    .flatMap((y) => [a[2], b[2]].map((z) => project([x, y, z])))));
  const xs = corners.map((p) => p[0]), ys = corners.map((p) => p[1]);
  const scale = (size - 2) / Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
  const ox = size / 2 - ((Math.max(...xs) + Math.min(...xs)) / 2) * scale;
  const oy = size / 2 - ((Math.max(...ys) + Math.min(...ys)) / 2) * scale;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;

  // face: texture and area, the point where the area's (0,0) lands, its two directions on
  // screen (u right, v down), and how dark to make it. The area is stretched to fit.
  const face = (area, origin, u, v, [fw, fh], shade) => {
    if (!area) return;
    const [img, [su, sv, sw, sh]] = area;
    if (sw <= 0 || sh <= 0) return;
    const [px, py] = project(origin);
    ctx.setTransform(u[0] * scale, u[1] * scale, v[0] * scale, v[1] * scale, ox + px * scale, oy + py * scale);
    ctx.drawImage(img, su, sv, sw, sh, 0, 0, fw, fh);
    if (shade) {
      ctx.fillStyle = `rgba(0,0,0,${shade})`;
      ctx.fillRect(0, 0, fw, fh);
    }
  };
  const down = [0, 1];  // -y on screen
  const back = [-AXIS.z[0], -AXIS.z[1]];
  for (const { a: [x0, y0, z0], b: [x1, y1, z1], top, front, side, turned } of parts) {
    face(top, [x0, y1, z0], AXIS.x, AXIS.z, [x1 - x0, z1 - z0], 0);
    face(front, [x0, y1, z1], AXIS.x, down, [x1 - x0, y1 - y0], 0.2);
    if (turned) face(side, [x1, y1, z0], down, AXIS.z, [y1 - y0, z1 - z0], 0.4);
    else face(side, [x1, y1, z1], back, down, [z1 - z0, y1 - y0], 0.4);
  }
  return canvas.toDataURL();
}

/** An icon (a split's key, or runs/resets/clock/netherrack), or null when there's none
 *  for it or the game's textures can't be found. */
export function icon(key, { className = "" } = {}) {
  const def = ICONS[key];
  if (!def || !state.textures) return null;
  const img = h("img", { class: def.item ? "icon-item" : "icon-block", alt: "" });
  const slot = h("span", { class: `icon ${className}`.trim(), "aria-hidden": "true", title: def.title }, img);
  if (def.item && !def.count) {
    img.src = textureUrl(def.item);
  } else {
    if (!rendered.has(key)) rendered.set(key, def.count ? renderCounted(def, def.count) : renderShape(def));
    rendered.get(key).then((url) => { img.src = url; }, () => slot.remove());
  }
  img.addEventListener("error", () => slot.remove());
  return slot;
}

/** A label with its split's icon in front: [icon, text] (just the text if no icon). */
export function withIcon(key, text) {
  return h("span", { class: "with-icon" }, icon(key), text);
}

/** A fixed-size slot holding the icon (or empty), so lists of splits stay aligned. */
export function iconSlot(key) {
  return h("span", { class: "icon-slot" }, icon(key));
}

/** An icon with a stack count drawn in its corner like the inventory (e.g. 33 pearls),
 *  or null when it can't be drawn. */
export function countedIcon(key, count, { className = "" } = {}) {
  const def = ICONS[key];
  if (!def || !state.textures) return null;
  const img = h("img", { class: "icon-item", alt: "" });
  const slot = h("span", { class: `icon ${className}`.trim(), "aria-hidden": "true" }, img);
  const cacheKey = `${key}:${count}`;
  if (!rendered.has(cacheKey)) rendered.set(cacheKey, renderCounted(def, count));
  rendered.get(cacheKey).then((url) => { img.src = url; }, () => slot.remove());
  return slot;
}
