import {
  $, q, start, setStatus, renderNav, fillSeasons, holdersSql, FISH_SQL, COMP_SQL,
  urlParams, syncUrl, pick, table, cell, scoreCell, nameCell, seasonLabel
} from "./common.js";

const COLS = "Date, Nick, Lake, Type, Weight, Rank, Out_Of, Score";
const PRESETS = {
  "Latest records": f => `SELECT ${COLS}\nFROM records\nWHERE 1 = 1${f}\nORDER BY Date DESC, Score DESC\nLIMIT 50;`,
  "Best fishes of all time": f => `SELECT ${COLS}\nFROM records\nWHERE ${FISH_SQL}${f}\nORDER BY Score DESC\nLIMIT 50;`,
  "Best competition scores of all time": f => `SELECT ${COLS}\nFROM records\nWHERE ${COMP_SQL}${f}\nORDER BY Score DESC\nLIMIT 50;`,
  // The Nick filter applies to the winners, not the candidates (same as "Team records held" on the profile page).
  "All team records": (f, noNick) => {
    const nick = fsel.Nick.value;
    const seasonal = fsel.Season.value === "seasons";  // one winner per season, so show which season
    const cols = "Nick, Lake, Type, Weight, Rank, Out_Of, Score, Date" + (seasonal ? ", Season" : "");
    return `${holdersSql("1 = 1" + noNick, cols, nick ? `Nick = '${esc(nick)}'` : "")}\nORDER BY ${seasonal ? "Season DESC, " : ""}Lake, Type;`;
  },
  "Total fish score": f => `SELECT Nick, SUM(Score) AS Score FROM records\nWHERE ${FISH_SQL}${f}\nGROUP BY Nick ORDER BY Score DESC;`,
  "Total competition score": f => `SELECT Nick, SUM(Score) AS Score FROM records\nWHERE ${COMP_SQL}${f}\nGROUP BY Nick ORDER BY Score DESC;`
};
const FILTERS = { Nick: "nicknames", Lake: "lakes", Type: "types", Season: "seasons" };
const DEFAULTS = { preset: Object.keys(PRESETS)[0], nick: "", lake: "", type: "", season: "0_0" };

const presetSel = $("presets");
const box = $("sql");
const statusEl = $("status");
const out = $("out");
const runBtn = $("run");
const fsel = Object.fromEntries(Object.keys(FILTERS).map(c => [c, $("f-" + c)]));
const selects = [presetSel, ...Object.values(fsel)];

let db;
let dirty = false;            // SQL textarea was edited by hand
const lastValue = new Map();  // select -> last accepted value, to undo a cancelled change

for (const name of Object.keys(PRESETS)) presetSel.add(new Option(name));

const esc = v => v.replace(/'/g, "''");
const filt = skip => Object.keys(FILTERS).filter(c => c !== skip).map(c => {
  const v = fsel[c].value;
  if (c === "Season") return v === "seasons" ? " AND Season <> '0_0'" : ` AND Season = '${esc(v || "0_0")}'`;
  return v ? ` AND ${c} = '${esc(v)}'` : "";
}).join("");

const state = () => ({
  preset: presetSel.value,
  nick: fsel.Nick.value,
  lake: fsel.Lake.value,
  type: fsel.Type.value,
  season: fsel.Season.value
});

// Grow the textarea to fit its content so the page, not the box, scrolls.
const fit = () => { box.style.height = "auto"; box.style.height = box.scrollHeight + 2 + "px"; };
box.closest("details").addEventListener("toggle", fit);
window.addEventListener("resize", fit);

function refresh() {
  box.value = PRESETS[presetSel.value](filt(), filt("Nick"));
  fit();
  dirty = false;
  selects.forEach(s => lastValue.set(s, s.value));
  syncUrl(state(), DEFAULTS);
  run();
}

selects.forEach(s => s.addEventListener("change", () => {
  if (dirty && !confirm("This replaces the SQL you edited. Continue?")) {
    s.value = lastValue.get(s);
    return;
  }
  refresh();
}));
box.addEventListener("input", () => { dirty = true; fit(); });

function toCell(col, v, season) {
  if (v === null) return null;
  if (col === "Nick") return nameCell(v, { season });
  if (col === "Score" && typeof v === "number") return scoreCell(v);
  if (col === "Weight" && typeof v === "number") return cell(v, v + " g");
  if (col === "Season") return seasonLabel(v);
  return v;
}

function run() {
  setStatus(statusEl, "");
  try {
    const t = performance.now();
    const res = db.exec(box.value);
    const ms = Math.round(performance.now() - t);
    out.replaceChildren();
    const first = res[0];
    if (!first) { setStatus(statusEl, "Query OK, no rows.", "ok"); return; }
    const { columns, values } = first;
    const season = fsel.Season.value;
    const num = columns.map((_, i) => i).filter(i => values.some(r => typeof r[i] === "number"));
    const rows = values.map(r => r.map((v, i) => toCell(columns[i], v, season)));
    out.append(table(columns, rows, { num, nullText: "NULL" }));
    setStatus(statusEl, `${values.length} rows \u00B7 ${ms} ms`, "ok");
  } catch (e) {
    console.error("run() failed:", e);
    out.replaceChildren();
    setStatus(statusEl, "Query failed: " + e.message, "err");
  }
}

function fillFilters() {
  for (const [c, label] of Object.entries(FILTERS)) {
    const vals = q(db, `SELECT DISTINCT ${c} FROM records WHERE ${c} IS NOT NULL ORDER BY ${c}`).map(r => r[0]);
    if (c === "Season") {
      fillSeasons(fsel[c], vals);
    } else {
      fsel[c].add(new Option("All " + label, ""));
      vals.forEach(v => fsel[c].add(new Option(v, v)));
    }
  }
}

renderNav("index.html");
start(statusEl, async database => {
  db = database;
  runBtn.disabled = false;
  runBtn.onclick = run;
  box.addEventListener("keydown", e => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") run(); });
  fillFilters();

  const p = urlParams();
  pick(presetSel, p.get("preset"), DEFAULTS.preset);
  pick(fsel.Nick, p.get("nick"), DEFAULTS.nick);
  pick(fsel.Lake, p.get("lake"), DEFAULTS.lake);
  pick(fsel.Type, p.get("type"), DEFAULTS.type);
  pick(fsel.Season, p.get("season"), DEFAULTS.season);
  refresh();
});
