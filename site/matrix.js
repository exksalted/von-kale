import {
  $, el, q, start, setStatus, renderNav, fillSeasons, holdersSql, isComp,
  urlParams, syncUrl, pick, nameEl, scoreEl
} from "./common.js";

const seasonSel = $("season");
const lakeSel = $("lake");
const grid = $("grid");
const statusEl = $("status");
const DEFAULTS = { season: "0_0", lake: "" };
let db;

// Best record per lake and fish type (competitions are Fish_ID > 100)
const SQL = `${holdersSql("Season = ?", "Lake_ID, Lake, Fish_ID, Type, Nick, Weight, Rank, Out_Of, Score, Date")}\nORDER BY Lake_ID, Fish_ID`;

const toRec = ([lakeId, lake, fishId, type, nick, weight, rank, outOf, score, date]) =>
  ({ lakeId, lake, fishId, type, nick, weight, rank, outOf, score, date });

function draw() {
  grid.replaceChildren();
  const season = seasonSel.value;
  const rows = q(db, SQL, [season]).map(toRec).filter(r => !lakeSel.value || String(r.lakeId) === lakeSel.value);

  const lakes = new Map();
  for (const r of rows) {
    if (!lakes.has(r.lakeId)) lakes.set(r.lakeId, []);
    lakes.get(r.lakeId).push(r);
  }
  if (!lakes.size) {
    grid.append(el("div", "empty", "No records for this selection."));
    setStatus(statusEl, "");
    return;
  }

  const byName = [...lakes.values()].sort((a, b) => String(a[0].lake).localeCompare(String(b[0].lake), "fi"));
  for (const recs of byName) {
    const card = el("div", "lake");
    const h = el("h2", "", recs[0].lake);
    h.append(el("span", "", recs.length + " records"));
    card.append(h);

    let sepDone = false;
    for (const r of recs) {
      if (isComp(r.fishId) && !sepDone) { card.append(el("div", "sep", "Competitions")); sepDone = true; }
      const row = el("div", "rec");
      row.title = r.date || "";
      const who = el("div");
      who.append(nameEl(r.nick, { season }));
      const sc = el("div", "s");
      sc.append(scoreEl(r.score));
      row.append(
        who,
        el("div", "t", r.type),
        el("div", "w", r.weight == null ? "\u2013" : r.weight + " g"),
        el("div", "r", r.rank == null ? "\u2013" : `${r.rank} / ${r.outOf ?? "?"}`),
        sc
      );
      card.append(row);
    }
    grid.append(card);
  }
  setStatus(statusEl, `${lakes.size} lakes \u00B7 ${rows.length} records`, "ok");
}

function onChange() {
  syncUrl({ season: seasonSel.value, lake: lakeSel.value }, DEFAULTS);
  draw();
}

renderNav("matrix.html");
start(statusEl, async database => {
  db = database;
  fillSeasons(seasonSel, q(db, "SELECT DISTINCT Season FROM records WHERE Season IS NOT NULL").map(r => r[0]), { allSeasonal: false });
  lakeSel.add(new Option("All lakes", ""));
  q(db, "SELECT DISTINCT Lake_ID, Lake FROM records WHERE Lake_ID IS NOT NULL")
    .sort((x, y) => String(x[1]).localeCompare(String(y[1]), "fi"))
    .forEach(([id, name]) => lakeSel.add(new Option(name, id)));

  const p = urlParams();
  pick(seasonSel, p.get("season"), DEFAULTS.season);
  pick(lakeSel, p.get("lake"), DEFAULTS.lake);
  seasonSel.onchange = lakeSel.onchange = onChange;
  draw();
});
