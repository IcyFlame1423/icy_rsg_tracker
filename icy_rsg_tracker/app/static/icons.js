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

// Entity models for advancement icons, like DRAGON_HEAD: [x, y, z, w, h, d, u, v].
const CHEST = [
  [1, -10, 1, 14, 10, 14, 0, 19],   // bottom
  [1, -14, 1, 14, 5, 14, 0, 0],     // lid
  [7, -11, 0, 2, 4, 1, 0, 0],       // latch
];
const SHIELD = [[-6, -11, -2, 12, 22, 1, 0, 0]];
const SKULL = [[-4, -8, -4, 8, 8, 8, 0, 0]];
const BANNER = [[-10, -40, -1, 20, 40, 1, 0, 0]];  // just the cloth
// The dragon egg: stacked slabs, narrow at the top, drawn bottom to top.
const EGG = [[3, 0, 3, 13, 1, 13], [2, 1, 2, 14, 3, 14], [1, 3, 1, 15, 8, 15], [2, 8, 2, 14, 11, 14],
             [3, 11, 3, 13, 13, 13], [4, 13, 4, 12, 14, 12], [5, 14, 5, 11, 15, 11], [6, 15, 6, 10, 16, 10]]
  .map(([x0, y0, z0, x1, y1, z1]) => [[x0, y0, z0], [x1, y1, z1]]);

const item = (t) => ({ item: `item/${t}` });
const cube = (t) => ({ shape: CUBE, top: `block/${t}`, side: `block/${t}` });
const column = (top, side) => ({ shape: CUBE, top: `block/${top}`, side: `block/${side}` });
// Each advancement's icon: the item or block shown on its tile in the game.
const ADVANCEMENT_ICONS = {
  "story/root": { shape: CUBE, top: "block/grass_block_top", topTint: "#91bd59", side: "block/grass_block_side" },
  "story/mine_stone": item("wooden_pickaxe"), "story/upgrade_tools": item("stone_pickaxe"),
  "story/smelt_iron": item("iron_ingot"), "story/obtain_armor": item("iron_chestplate"),
  "story/lava_bucket": item("lava_bucket"), "story/iron_tools": item("iron_pickaxe"),
  "story/deflect_arrow": { model: SHIELD, texture: "entity/shield_base_nopattern" },
  "story/form_obsidian": cube("obsidian"), "story/mine_diamond": item("diamond"),
  "story/enter_the_nether": item("flint_and_steel"), "story/shiny_gear": item("diamond_chestplate"),
  "story/enchant_item": item("enchanted_book"), "story/cure_zombie_villager": item("golden_apple"),
  "story/follow_ender_eye": item("ender_eye"), "story/enter_the_end": cube("end_stone"),
  "nether/root": cube("red_nether_bricks"), "nether/return_to_sender": item("fire_charge"),
  "nether/find_bastion": cube("polished_blackstone_bricks"),
  "nether/obtain_ancient_debris": column("ancient_debris_top", "ancient_debris_side"),
  "nether/fast_travel": item("map"), "nether/find_fortress": cube("nether_bricks"),
  "nether/obtain_crying_obsidian": cube("crying_obsidian"), "nether/distract_piglin": item("gold_ingot"),
  "nether/ride_strider": item("warped_fungus_on_a_stick"), "nether/uneasy_alliance": item("ghast_tear"),
  "nether/loot_bastion": { model: CHEST, texture: "entity/chest/normal" },
  "nether/use_lodestone": column("lodestone_top", "lodestone_side"),
  "nether/netherite_armor": item("netherite_chestplate"),
  "nether/get_wither_skull": { model: SKULL, texture: "entity/skeleton/wither_skeleton" },
  "nether/obtain_blaze_rod": item("blaze_rod"),
  "nether/charge_respawn_anchor": column("respawn_anchor_top_off", "respawn_anchor_side0"),
  "nether/explore_nether": item("netherite_boots"), "nether/summon_wither": item("nether_star"),
  "nether/brew_potion": { layers: [["item/potion_overlay", "#385dc6"], ["item/potion"]] },  // a water bottle
  "nether/create_beacon": cube("beacon"), "nether/all_potions": item("milk_bucket"),
  "nether/create_full_beacon": cube("beacon"), "nether/all_effects": item("bucket"),
  "end/root": cube("end_stone"),
  "end/kill_dragon": { model: DRAGON_HEAD, texture: "entity/enderdragon/dragon" },
  "end/dragon_egg": { shape: EGG, top: "block/dragon_egg", side: "block/dragon_egg" },
  "end/enter_end_gateway": item("ender_pearl"), "end/respawn_dragon": item("end_crystal"),
  "end/dragon_breath": item("dragon_breath"), "end/find_end_city": cube("purpur_block"),
  "end/elytra": item("elytra"), "end/levitate": item("shulker_shell"),
  "adventure/root": item("map"),
  "adventure/voluntary_exile": { model: BANNER, texture: "entity/banner_base" },
  "adventure/kill_a_mob": item("iron_sword"), "adventure/trade": item("emerald"),
  "adventure/honey_block_slide": column("honey_block_top", "honey_block_side"),
  "adventure/ol_betsy": item("crossbow_standby"),
  "adventure/sleep_in_bed": { parts: BED, texture: "entity/bed/red" },
  "adventure/hero_of_the_village": { model: BANNER, texture: "entity/banner_base" },
  "adventure/throw_trident": item("trident"), "adventure/shoot_arrow": item("bow"),
  "adventure/kill_all_mobs": item("diamond_sword"), "adventure/totem_of_undying": item("totem_of_undying"),
  "adventure/summon_iron_golem": { shape: CUBE, top: "block/pumpkin_top", side: "block/pumpkin_side",
                                   front: "block/carved_pumpkin" },
  "adventure/two_birds_one_arrow": item("crossbow_standby"),
  "adventure/whos_the_pillager_now": item("crossbow_standby"), "adventure/arbalistic": item("crossbow_standby"),
  "adventure/adventuring_time": item("diamond_boots"), "adventure/very_very_frightening": item("trident"),
  "adventure/sniper_duel": item("arrow"), "adventure/bullseye": column("target_top", "target_side"),
  "husbandry/root": column("hay_block_top", "hay_block_side"),
  "husbandry/safely_harvest_honey": item("honey_bottle"), "husbandry/breed_an_animal": item("wheat"),
  "husbandry/tame_an_animal": item("lead"), "husbandry/fishy_business": item("fishing_rod"),
  "husbandry/silk_touch_nest": { shape: CUBE, top: "block/bee_nest_top", side: "block/bee_nest_side",
                                 front: "block/bee_nest_front" },
  "husbandry/plant_seed": item("wheat"), "husbandry/bred_all_animals": item("golden_carrot"),
  "husbandry/complete_catalogue": item("cod"), "husbandry/tactical_fishing": item("pufferfish_bucket"),
  "husbandry/balanced_diet": item("apple"), "husbandry/obtain_netherite_hoe": item("netherite_hoe"),
};

/** What each icon is. top/side (and front, if it differs): block textures for the shape's
 *  faces, topTint a color the top is tinted (grass); model: entity boxes on one texture;
 *  layers: item textures drawn over each other, each optionally tinted (potions). */
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
  advancement: { item: "item/knowledge_book", title: "Knowledge book" },
  logo: { shape: CUBE, top: "block/packed_ice", side: "block/packed_ice", title: "Packed ice" },
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
  // "adv:<id>": the Splits page's advancements.
  ...Object.fromEntries(Object.entries(ADVANCEMENT_ICONS).map(([id, def]) => [`adv:${id}`, def])),
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

/** A copy of an image with its colors multiplied by a tint (as the game colors grass and potions). */
function tinted(img, color) {
  const canvas = document.createElement("canvas");
  canvas.width = img.width;
  canvas.height = img.height;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0);
  ctx.globalCompositeOperation = "multiply";
  ctx.fillStyle = color;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.globalCompositeOperation = "destination-in";  // keep the image's transparency
  ctx.drawImage(img, 0, 0);
  return canvas;
}

/** An item made of layers (e.g. a potion: the tinted liquid, then the bottle). */
async function renderLayers(def, px = 4) {
  const images = await Promise.all(def.layers.map(([name]) => loadImage(name)));
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 16 * px;
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  images.forEach((img, i) => {
    const tint = def.layers[i][1];
    ctx.drawImage(tint ? tinted(img, tint) : img, 0, 0, 16 * px, 16 * px);
  });
  return canvas.toDataURL();
}

// Isometric axes on screen, per block pixel: x runs right-down, z left-down, y up.
const C = Math.cos(Math.PI / 6);
const AXIS = { x: [C, 0.5], y: [0, -1], z: [-C, 0.5] };
const project = ([x, y, z]) => [x * AXIS.x[0] + z * AXIS.z[0], x * AXIS.x[1] + y * AXIS.y[1] + z * AXIS.z[1]];
const clamp = (v) => Math.min(16, Math.max(0, v));

/** The icon's picture: the item texture, or its 3D shape drawn onto a canvas. */
async function baseImage(def) {
  if (def.item) return loadImage(def.item);
  const url = await (def.layers ? renderLayers(def) : renderShape(def));
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

  const text = String(count);  // "" for none
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
  let [top, side, front] = await Promise.all([loadImage(def.top), loadImage(def.side), loadImage(def.front ?? def.side)]);
  if (def.topTint) top = tinted(top, def.topTint);
  if (def.tint) [top, side, front] = [top, side, front].map((img) => tinted(img, def.tint));  // leaves
  return def.shape.map(([a, b]) => {
    // Texture areas follow the box's position in the block, as Minecraft maps them.
    const [x0, y0, z0] = a.map(clamp), [x1, y1, z1] = b.map(clamp);
    return { a, b, top: [top, [x0, z0, x1 - x0, z1 - z0]], front: [front, [x0, 16 - y1, x1 - x0, y1 - y0]],
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
    if (!rendered.has(key)) {
      rendered.set(key, def.count ? renderCounted(def, def.count) : def.layers ? renderLayers(def) : renderShape(def));
    }
    rendered.get(key).then((url) => { img.src = url; }, () => slot.remove());
  }
  img.addEventListener("error", () => slot.remove());
  return slot;
}

/** A block icon drawn as an image (a data URL promise), or null without the game's textures. */
export function blockImage(key) {
  const def = ICONS[key];
  if (!def?.shape || !state.textures) return null;
  if (!rendered.has(key)) rendered.set(key, renderShape(def));
  return rendered.get(key);
}

// Potion colors (as the game draws the liquid), by effect.
const POTION_COLORS = {
  fire_resistance: "#e49a3a", swiftness: "#7cafc6", strength: "#932423", healing: "#f82423",
  regeneration: "#cd5cab", night_vision: "#1f1fa1", invisibility: "#7f8392", leaping: "#22ff4c",
  water_breathing: "#2e5299", slow_falling: "#ffefd1", poison: "#4e9331", weakness: "#484d48",
  slowness: "#5a6c81", harming: "#430a09", turtle_master: "#755e48",
};
const WATER = "#385dc6";
const LEATHER = "#a06540";
const itemDefs = new Map();  // item id -> Promise<icon definition or null>

/** How to draw any item ("soul_sand", "splash_potion[fire_resistance]"), from its model. */
function itemDef(id) {
  if (!itemDefs.has(id)) {
    const [, base, potion] = id.match(/^([a-z0-9_]+)(?:\[([a-z0-9_]+)\])?$/) ?? [];
    itemDefs.set(id, !base ? Promise.resolve(null) : fetch(`/api/item?${new URLSearchParams({ id: base })}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((m) => {
        if (!m) return null;
        if (m.entity?.endsWith("_bed")) return { parts: BED, texture: `entity/bed/${m.entity.replace(/_bed$/, "")}` };
        if (m.entity === "chest") return { model: CHEST, texture: "entity/chest/normal" };
        if (m.entity) return null;
        if (m.layers) {
          const color = base.endsWith("potion") ? POTION_COLORS[(potion ?? "").replace(/^(long|strong)_/, "")] ?? WATER : null;
          if (m.layers.length === 1) return { item: m.layers[0] };
          if (base.startsWith("leather_")) return { layers: m.layers.map((t, i) => [t, i === 0 ? LEATHER : null]) };
          return { layers: m.layers.map((t) => [t, color && t.endsWith("_overlay") ? color : null]) };
        }
        return { shape: m.boxes, top: m.top, side: m.side, front: m.front, tint: m.tint };
      })
      .catch(() => null));
  }
  return itemDefs.get(id);
}

/** Any item's icon with its stack count drawn in the corner (none for 1), or null without
 *  the game's textures. Removed if the item can't be drawn. */
export function itemIcon(id, count = 1, { className = "", showOne = false } = {}) {
  if (!state.textures) return null;
  const img = h("img", { class: "icon-item", alt: "" });
  const slot = h("span", { class: `icon ${className}`.trim(), "aria-hidden": "true" }, img);
  const shown = count > 1 || (showOne && count === 1) ? count : "";  // like the game: no number for one
  const key = `item:${id}:${shown}`;
  if (!rendered.has(key)) {
    rendered.set(key, itemDef(id).then((def) => {
      if (!def) throw new Error(`no icon for ${id}`);
      return renderCounted(def, shown);
    }));
  }
  rendered.get(key).then((url) => { img.src = url; }, () => slot.remove());
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
