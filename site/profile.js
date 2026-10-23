import {
  $, el, q, start, setStatus, renderNav, fillSeasons, holdersSql, FISH_SQL, COMP_SQL, isFish, isComp,
  urlParams, syncUrl, pick, table, cell, scoreEl, scoreCell, weightCell, nameEl
} from "./common.js";

const nickSel = $("nick");
const seasonSel = $("season");
const statusEl = $("status");
const kindSel = $("kind");
const TABS = [["overview", "Overview"], ["records", "All records"], ["lakes", "By lake"], ["species", "By species"], ["team", "Team records"]];
let db;

const REC_COLS = "Date, Lake, Type, Weight, Rank, Out_Of, Score, Fish_ID";
const REC_HEADS = ["Date", "Lake", "Type", "Weight", "Rank", "Score"];
const REC_NUM = [3, 4, 5];

const toRec = ([date, lake, type, weight, rank, outOf, score, fishId]) =>
  ({ date, lake, type, weight, rank, outOf, score, fishId });

const recRow = r => [
  r.date,
  r.lake,
  r.type,
  weightCell(r.weight),
  r.rank == null ? null : cell(r.rank, `${r.rank} / ${r.outOf ?? "?"}`),
  scoreCell(r.score)
];
const recTable = rs => table(REC_HEADS, rs.map(recRow), { num: REC_NUM });
const sum = rs => rs.reduce((t, r) => t + (r.score || 0), 0);

// One All/Fish/Competitions filter (in the tab row) drives both the "All records" and "Team records" panes.
let mineRows = [], heldRows = [];
const KINDS = { All: () => true, Fish: r => isFish(r.fishId), Competitions: r => isComp(r.fishId) };
function drawKind() {
  const keep = KINDS[kindSel.value];
  $("p-records").replaceChildren(recTable(mineRows.filter(keep)));
  $("p-team").replaceChildren(recTable(heldRows.filter(keep)));
}

// Groups records by a field; returns [key, { s: total score, best, w: heaviest }] sorted by total score.
function group(rows, key) {
  const m = new Map();
  for (const r of rows) {
    const g = m.get(r[key]) ?? { s: 0, best: null, w: null };
    g.s += r.score || 0;
    if (r.score != null && (g.best == null || r.score > g.best)) g.best = r.score;
    if (r.weight != null && (g.w == null || r.weight > g.w)) g.w = r.weight;
    m.set(r[key], g);
  }
  return [...m].sort((a, b) => b[1].s - a[1].s);
}

function showTab(t) {
  TABS.forEach(([id]) => { $("p-" + id).hidden = id !== t; });
  kindSel.hidden = t !== "records" && t !== "team";
  $("tabs").querySelectorAll("button").forEach(b => {
    if (b.dataset.t === t) b.setAttribute("aria-current", "true"); else b.removeAttribute("aria-current");
  });
}

function render() {
  const season = seasonSel.value, nick = nickSel.value;
  syncUrl({ nick, season });

  const seasonal = season === "seasons";
  const sc = seasonal ? "Season <> '0_0'" : "Season = ?";
  const sp = seasonal ? [] : [season];

  const mine = q(db, `SELECT ${REC_COLS} FROM records WHERE ${sc} AND Nick = ? ORDER BY Score DESC`, [...sp, nick]).map(toRec);
  const held = q(db, `SELECT ${REC_COLS} FROM (${holdersSql(sc)}) WHERE Nick = ? ORDER BY Score DESC`, [...sp, nick]).map(toRec);
  const team = q(db, `SELECT Nick, SUM(CASE WHEN ${FISH_SQL} THEN Score END), SUM(CASE WHEN ${COMP_SQL} THEN Score END)
                      FROM records WHERE ${sc} GROUP BY Nick`, sp);

  const fish = mine.filter(r => isFish(r.fishId));
  const comp = mine.filter(r => isComp(r.fishId));
  const me = team.find(t => t[0] === nick);
  const rankOf = i => `#${1 + team.filter(t => t[0] !== nick && (t[i] || 0) > (me?.[i] || 0)).length} of ${team.length} in team`;

  const heading = nameEl(nick, { link: false });
  heading.classList.add("big");
  $("name").replaceChildren(heading);
  setStatus(statusEl, `${mine.length} records`, "ok");

  // Overview
  const big = v => { const b = scoreEl(v); b.classList.add("big"); return b; };
  const cards = el("div", "cards");
  for (const [k, v, sub, go] of [
    ["Fish score", big(sum(fish)), rankOf(1)],
    ["Competition score", big(sum(comp)), rankOf(2)],
    ["Records", mine.length, `${fish.length} fish \u00B7 ${comp.length} competition`],
    ["Team records held", held.length, "best in team \u00B7 click to view", "team"]
  ]) {
    const c = el(go ? "button" : "div", "stat"), val = el("span", "v");
    if (go) { c.type = "button"; c.classList.add("link"); c.onclick = () => showTab(go); }
    val.append(v);
    c.append(el("span", "k", k), val, el("span", "sub", sub));
    cards.append(c);
  }
  $("p-overview").replaceChildren(
    cards,
    el("h3", "", "Best fish"), recTable(fish.slice(0, 5)),
    el("h3", "", "Best competitions"), recTable(comp.slice(0, 5))
  );

  mineRows = mine;
  heldRows = held;
  drawKind();

  // By lake: fish and competition sums side by side
  const lakes = new Map();
  for (const r of mine) {
    const g = lakes.get(r.lake) ?? { fish: 0, comp: 0 };
    g[isComp(r.fishId) ? "comp" : "fish"] += r.score || 0;
    lakes.set(r.lake, g);
  }
  $("p-lakes").replaceChildren(table(
    ["Lake", "Fish score", "Competition score", "Total score"],
    [...lakes]
      .sort((a, b) => (b[1].fish + b[1].comp) - (a[1].fish + a[1].comp))
      .map(([lake, g]) => [lake, scoreCell(g.fish), scoreCell(g.comp), scoreCell(g.fish + g.comp)]),
    { num: [1, 2, 3] }
  ));

  // By species / competition type
  const byType = rs => table(
    ["Type", "Heaviest", "Best score", "Total score"],
    group(rs, "type").map(([t, g]) => [t, weightCell(g.w), scoreCell(g.best), scoreCell(g.s)]),
    { num: [1, 2, 3] }
  );
  $("p-species").replaceChildren(el("h3", "", "Fish species"), byType(fish), el("h3", "", "Competition types"), byType(comp));
}

renderNav();
start(statusEl, async database => {
  db = database;
  TABS.forEach(([id, label]) => {
    const b = el("button", "tab", label);
    b.type = "button";
    b.dataset.t = id;
    b.onclick = () => showTab(id);
    kindSel.before(b);
  });
  Object.keys(KINDS).forEach(k => kindSel.add(new Option(k)));
  kindSel.onchange = drawKind;

  const nicks = q(db, "SELECT DISTINCT Nick FROM records WHERE Nick IS NOT NULL ORDER BY Nick").map(r => r[0]);
  nicks.forEach(n => nickSel.add(new Option(n, n)));
  fillSeasons(seasonSel, q(db, "SELECT DISTINCT Season FROM records WHERE Season IS NOT NULL").map(r => r[0]));

  const p = urlParams();
  pick(seasonSel, p.get("season"), "0_0");
  const top = q(db, "SELECT Nick FROM records WHERE Season = '0_0' GROUP BY Nick ORDER BY SUM(Score) DESC LIMIT 1")[0]?.[0];
  pick(nickSel, p.get("nick"), top || nicks[0] || "");
  nickSel.onchange = seasonSel.onchange = render;
  render();
  showTab("overview");
});
