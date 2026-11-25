// Settings page: edit config.toml, detect instances, rebuild from the records folder.
import * as fmt from "./fmt.js";
import { $, getJSON, h } from "./common.js";

const RSG_PATTERN = "^Random Speedrun #\\d+$";
let current = null;     // settings as last loaded/saved
let instances = [];     // the instance rows being edited
let detected = null;    // results of "Detect instances"
let dirty = false;      // unsaved edits: don't replace them when the page refreshes

async function postJSON(url, body) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
                                 body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || res.statusText);
    err.fields = data.fields || {};
    throw err;
  }
  return data;
}

function field(label, input, help, errorKey) {
  return h("label", { class: "field" },
    h("span", { class: "field-label" }, label),
    input,
    help ? h("span", { class: "field-help" }, help) : null,
    h("span", { class: "field-error", "data-error": errorKey }));
}

function showErrors(fields = {}) {
  document.querySelectorAll("#page-settings [data-error]").forEach((el) => {
    el.textContent = fields[el.dataset.error] ?? "";
  });
}

function setMessage(text, kind = "") {
  const m = $("settings-message");
  m.textContent = text;
  m.dataset.kind = kind;
}

// ---- Rendering ----

function renderGeneral() {
  const s = current;
  const records = s.records_found == null
    ? "Folder not found. SpeedRunIGT keeps it in your user folder (e.g. C:\\Users\\you\\speedrunigt)."
    : `${fmt.int(s.records_found)} run records found in its records folder.`;
  $("settings-general").replaceChildren(
    field("SpeedRunIGT folder", h("input", { type: "text", id: "set-folder", value: s.speedrunigt_dir, spellcheck: "false" }),
      records, "speedrunigt_dir"),
    h("div", { class: "field-row" },
      field("Session gap (minutes)", h("input", { type: "number", id: "set-gap", min: "1", max: "1440", step: "1",
                                                  value: String(s.session_gap_minutes) }),
        "A break longer than this starts a new session.", "session_gap_minutes"),
      field("Check for new runs every (seconds)", h("input", { type: "number", id: "set-interval", min: "1", max: "60",
                                                               step: "1", value: String(s.watch_interval_seconds) }),
        "How often the tracker looks at the records folder.", "watch_interval_seconds")),
  );
}

let helpCount = 0;

/** A "?" that shows how world name patterns work, on hover or keyboard focus. */
function patternHelp() {
  const id = `pattern-help-${++helpCount}`;
  const examples = [
    ["^Random Speedrun #\\d+$", "Atum's RSG worlds: \"Random Speedrun #\" and a number, nothing else"],
    ["^Set Speedrun #", "names that start with \"Set Speedrun #\""],
    ["Ranked", "names with \"Ranked\" anywhere in them"],
  ];
  const symbols = [
    ["^", "the start of the name"],
    ["$", "the end of the name"],
    ["\\d", "one digit (0-9); \\d+ is one or more digits"],
    [".", "any one character; .* is anything at all"],
    ["\\. \\( \\+", "a backslash makes a symbol mean itself (a dot, a bracket, a plus)"],
    ["a|b", "either a or b"],
  ];
  return h("span", { class: "help", tabindex: "0", role: "button", "aria-label": "How world name patterns work",
                     "aria-describedby": id, onclick: (e) => e.preventDefault() }, "?",
    h("span", { class: "help-pop", role: "tooltip", id },
      h("strong", {}, "World name pattern"),
      h("span", {}, "A regular expression that each world's name is checked against. Letters, numbers, spaces " +
        "and # match themselves; it's case-sensitive. Without ^ and $ it matches anywhere in the name."),
      h("table", {}, h("tbody", {}, symbols.map(([sym, text]) => h("tr", {}, h("td", {}, h("code", {}, sym)), h("td", {}, text))))),
      h("span", {}, "Examples:"),
      h("table", {}, h("tbody", {}, examples.map(([pat, text]) => h("tr", {}, h("td", {}, h("code", {}, pat)), h("td", {}, text)))))));
}

function renderInstances() {
  const rows = instances.map((inst, i) => h("div", { class: "instance-row" },
    field("Name", h("input", { type: "text", value: inst.name, oninput: (e) => { inst.name = e.target.value; } }),
      "Its CSVs go in data\\<name>\\", `instances.${i}.name`),
    field(["World name pattern ", patternHelp()], h("input", { type: "text", value: inst.world_name_pattern, spellcheck: "false",
                                              oninput: (e) => { inst.world_name_pattern = e.target.value; } }),
      "Runs whose world name matches go to this instance (a regular expression).", `instances.${i}.world_name_pattern`),
    field("Minecraft folder", h("input", { type: "text", value: inst.minecraft_dir, spellcheck: "false",
                                           placeholder: "Leave empty to use the Prism instance with this name",
                                           oninput: (e) => { inst.minecraft_dir = e.target.value; } }),
      inst.minecraft_dir
        ? (inst.logs_found === false ? "No logs folder here, so deaths can't be split by spawn point." : "Its logs are used to tell death resets from accidental deaths.")
        : "Optional. Used to tell death resets from accidental deaths.",
      `instances.${i}.minecraft_dir`),
    h("button", { type: "button", class: "button danger", title: "Remove this instance",
                  disabled: instances.length === 1,
                  onclick: () => { instances.splice(i, 1); renderInstances(); } }, "Remove"),
  ));
  const shared = sharedPatterns();
  // (DOM replaceChildren would print null/false as text, so wrap in h(), which skips them.)
  $("settings-instances").replaceChildren(h("div", { class: "form" }, ...rows,
    shared ? h("p", { class: "field-error" },
      `${shared.join(" and ")} use the same world name pattern. Runs go to the first one only.`) : null,
    h("span", { class: "field-error", "data-error": "instances" }),
    h("div", { class: "button-row" },
      h("button", { type: "button", class: "button", onclick: () => {
        instances.push({ name: "", world_name_pattern: RSG_PATTERN, minecraft_dir: "" });
        renderInstances();
      } }, "Add instance"),
      h("button", { type: "button", class: "button", onclick: detect }, "Detect instances")),
    detected ? renderDetected() : null));
}

function sharedPatterns() {
  const byPattern = {};
  for (const i of instances) (byPattern[i.world_name_pattern] ??= []).push(i.name || "(unnamed)");
  return Object.values(byPattern).find((names) => names.length > 1) ?? null;
}

function renderDetected() {
  if (!detected.length) {
    return h("p", { class: "sub" }, "No Prism Launcher or MultiMC instances found in the usual folders. Enter the Minecraft folder by hand.");
  }
  const added = new Set(instances.map((i) => i.minecraft_dir.toLowerCase()));
  return h("div", { class: "detected" },
    h("p", { class: "sub" }, "Found these instances. RSG ones have Atum installed or \"Random Speedrun\" worlds."),
    h("table", { class: "data-table" },
      h("thead", {}, h("tr", {}, h("th", {}, "Instance"), h("th", {}, "Folder"), h("th", {}, ""), h("th", {}, ""))),
      h("tbody", {}, detected.map((d) => h("tr", {},
        h("td", {}, d.name),
        h("td", { class: "path" }, d.minecraft_dir),
        h("td", {}, d.rsg ? "RSG" : h("span", { class: "muted" }, "other")),
        h("td", {}, added.has(d.minecraft_dir.toLowerCase())
          ? h("span", { class: "muted" }, "Added")
          : h("button", { type: "button", class: "button", onclick: () => {
              instances.push({ name: d.name.replace(/[^A-Za-z0-9 _.\-]/g, "").slice(0, 40) || "instance",
                               world_name_pattern: d.world_name_pattern || "", minecraft_dir: d.minecraft_dir });
              renderInstances();
            } }, "Add")))))));
}

function renderData() {
  $("settings-data").replaceChildren(
    h("p", {}, "Your CSVs are in ", h("code", {}, current.output_dir), "."),
    h("p", {}, "Settings are saved in ", h("code", {}, current.config_path), "."),
    h("p", { class: "sub" },
      "Rebuild reads every SpeedRunIGT record again and rewrites each instance's runs.csv. Use it after changing " +
      "world name patterns. Runs whose records were deleted are lost, but the old file is kept as runs.csv.bak."),
    h("div", { class: "button-row" },
      h("button", { type: "button", class: "button", onclick: rebuild }, "Rebuild from records")),
  );
}

function render() {
  dirty = false;
  instances = current.instances.map((i) => ({ ...i }));
  renderGeneral();
  renderInstances();
  renderData();
  showErrors();
}

// ---- Actions ----

async function save() {
  const body = {
    speedrunigt_dir: $("set-folder").value,
    session_gap_minutes: $("set-gap").value,
    watch_interval_seconds: $("set-interval").value,
    include_set_seed: current.include_set_seed,  // not on the page any more; keep what config.toml says
    instances: instances.map(({ name, world_name_pattern, minecraft_dir }) => ({ name, world_name_pattern, minecraft_dir })),
  };
  setMessage("Saving…");
  try {
    current = await postJSON("/api/settings", body);
    render();
    setMessage("Saved. The tracker is using the new settings.", "ok");
  } catch (e) {
    showErrors(e.fields);
    setMessage(e.message, "error");
  }
}

async function detect() {
  setMessage("Looking for instances…");
  try {
    detected = (await getJSON("/api/detect")).instances;
    renderInstances();
    setMessage("");
  } catch (e) {
    setMessage(e.message, "error");
  }
}

async function rebuild() {
  if (!confirm("Rebuild every runs.csv from the SpeedRunIGT records? The old files are kept as runs.csv.bak.")) return;
  setMessage("Rebuilding…");
  try {
    const result = await postJSON("/api/rebuild", {});
    setMessage("Rebuilt: " + Object.entries(result.runs).map(([n, c]) => `${n} ${fmt.int(c)} runs`).join(", "), "ok");
  } catch (e) {
    setMessage(e.message, "error");
  }
}

export const settingsPage = {
  id: "settings",
  usesWindow: () => false,

  init() {
    const page = $("page-settings");
    page.addEventListener("input", () => { dirty = true; });
    page.addEventListener("click", (e) => {
      if (e.target.closest("#settings-instances button")) dirty = true;  // add/remove/detect-add
    });
    $("settings-save").addEventListener("click", save);
    $("settings-revert").addEventListener("click", () => { if (current) { render(); setMessage(""); } });
  },

  async load() {
    // Don't overwrite unsaved edits when the tracker imports a run.
    if (current && dirty) return "";
    current = await getJSON("/api/settings");
    render();
    return "";
  },
};
