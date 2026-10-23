// Shared helpers for all pages. Loaded as an ES module.

// ---------- DOM ----------

export const $ = id => document.getElementById(id);

export function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

export function setStatus(node, text, cls = "") {
  node.className = cls;
  node.textContent = text;
}

const PAGES = [["index.html", "Records"], ["matrix.html", "Records matrix"]];

// Fills <nav id="nav">. `current` is the file name of the active page (omit on profile.html).
export function renderNav(current) {
  $("nav").replaceChildren(...PAGES.map(([href, label]) => {
    const a = el("a", "", label);
    a.href = href;
    if (href === current) a.setAttribute("aria-current", "page");
    return a;
  }));
}

// ---------- Record classification ----------

// Fish_ID < 50 are fish species, >= 110 are competitions; 100 is the split point.
export const FISH_SQL = "Fish_ID < 100";
export const COMP_SQL = "Fish_ID > 100";
export const isFish = id => id < 100;
export const isComp = id => id > 100;

// ---------- Database ----------

const SQLJS_VERSION = "1.10.3";

export async function loadDb() {
  if (typeof initSqlJs !== "function") throw new Error("sql.js did not load (CDN blocked or integrity check failed?)");
  const SQL = await initSqlJs({ locateFile: f => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/${SQLJS_VERSION}/${f}` });
  const resp = await fetch("pp2_00.db");
  if (!resp.ok) throw new Error(`DB download failed (${resp.status})`);
  return new SQL.Database(new Uint8Array(await resp.arrayBuffer()));
}

// Runs a query and returns the rows of the first result set (or []).
export const q = (db, sql, params) => db.exec(sql, params)[0]?.values ?? [];

// Loads the DB, runs init(db), and reports any failure in the status element.
export async function start(statusNode, init) {
  try {
    await init(await loadDb());
  } catch (e) {
    console.error("Startup failed:", e);
    setStatus(statusNode, "Startup failed: " + e.message, "err");
  }
}

// One row per (lake, fish type): the record holder. Ties go to the earlier date, then to the nick.
// `where` filters which records compete (may contain ? placeholders). `cols` is the outer select list.
// `outer` filters the winners afterwards, e.g. "Nick = ?" = records held by that player.
export const holdersSql = (where = "1 = 1", cols = "*", outer = "") => `SELECT ${cols}
FROM (
  SELECT r.*, ROW_NUMBER() OVER (
    PARTITION BY Lake_ID, Fish_ID
    ORDER BY Score DESC, Date IS NULL, Date, Nick
  ) AS rn
  FROM records r
  WHERE ${where}
)
WHERE rn = 1${outer ? ` AND ${outer}` : ""}`;

// ---------- Seasons ----------

// Front-end names for season codes: 0_0 = all time, 1_N = the season starting in 2008+N
export function seasonLabel(code) {
  if (code === "0_0") return "All time";
  const m = /^1_(\d+)$/.exec(code);
  if (!m) return "Season " + code;
  const y = 2008 + Number(m[1]);
  return `Season ${y}-${String(y + 1).slice(2)}`;
}

// "0_0" (all time) first, then newest season first
export function sortSeasons(codes) {
  const n = c => c.split("_").map(Number);
  return [...codes].sort((a, b) => {
    if (a === b) return 0;
    if (a === "0_0") return -1;
    if (b === "0_0") return 1;
    const [a1, a2] = n(a), [b1, b2] = n(b);
    return (b1 - a1) || (b2 - a2) || b.localeCompare(a);
  });
}

export function fillSeasons(sel, codes, { allSeasonal = true } = {}) {
  sel.add(new Option(seasonLabel("0_0"), "0_0"));
  if (allSeasonal) sel.add(new Option("All seasonal records", "seasons"));
  sortSeasons(codes).filter(c => c !== "0_0").forEach(c => sel.add(new Option(seasonLabel(c), c)));
}

// ---------- URL state ----------

export const urlParams = () => new URLSearchParams(location.search);

// Writes non-empty, non-default values to the query string without adding history entries.
export function syncUrl(state, defaults = {}) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(state)) if (v && v !== defaults[k]) p.set(k, v);
  const s = p.toString();
  history.replaceState(null, "", s ? "?" + s : location.pathname);
}

// Sets a <select> to `value` if it has such an option, otherwise to `fallback`.
export function pick(sel, value, fallback) {
  sel.value = [...sel.options].some(o => o.value === value) ? value : fallback;
}

// ---------- Colors, scores and names ----------

const NAME_COLORS = {
  "liilu:3": "#a30465",
  "pumpkin": "#FF7518",
  "exksa": "#7ba63f",
  "kuhasalaliitto": "#6495ED",
  "ademan": "#40E0D0"
};

// Lower bound inclusive; first match from the top wins.
const SCORE_TIERS = [
  [100, "#DC2367"],
  [50, "#E03030"],
  [25, "#D35400"],
  [10, "#F1C40F"],
  [5, "#7D3C98"],
  [3, "#2471A3"],
  [2, "#27AE60"],
  [1, "#C5CAD3"],
  [-Infinity, "#565c68"]
];
const scoreColor = v => (SCORE_TIERS.find(t => v >= t[0]) || SCORE_TIERS[SCORE_TIERS.length - 1])[1];

// Non-numbers render as a muted dash instead of throwing.
export function scoreEl(v) {
  const ok = typeof v === "number" && Number.isFinite(v);
  const span = el("span", "score", ok ? v.toFixed(2) : "\u2013");
  if (ok) span.style.setProperty("--c", scoreColor(v));
  return span;
}

export function profileUrl(nick, season) {
  const p = new URLSearchParams({ nick });
  if (season && season !== "0_0") p.set("season", season);
  return "profile.html?" + p;
}

// A link to the player's profile, or a plain pill with { link: false }.
export function nameEl(nick, { link = true, season } = {}) {
  let e;
  if (link) {
    e = el("a", "name", nick);
    e.href = profileUrl(nick, season);
    e.title = "View profile";
  } else {
    e = el("span", "name static", nick);
  }
  const col = NAME_COLORS[String(nick).trim().toLowerCase()];
  if (col) e.style.setProperty("--c", col);
  return e;
}

// ---------- Sortable table ----------

// A table cell with a separate sort value and display: cell(850, "850 g").
// `show` may be a string or a Node; `cls` is an optional class for the <td>.
export const cell = (sort, show, cls) => ({ sort, show, cls });
export const scoreCell = v => cell(typeof v === "number" ? v : null, scoreEl(v));
export const weightCell = w => (w == null ? null : cell(w, `${w} g`));
export const nameCell = (nick, opts) => cell(nick, nameEl(nick, opts), "nick");

const isCell = c => c !== null && typeof c === "object" && !(c instanceof Node);
const sortVal = c => (c instanceof Node ? c.textContent : isCell(c) ? c.sort : c);

// Nulls always go last, whatever the direction.
const byColumn = (i, dir) => (x, y) => {
  const a = sortVal(x[i]), b = sortVal(y[i]);
  const na = a == null, nb = b == null;
  if (na || nb) return na === nb ? 0 : na ? 1 : -1;
  const r = typeof a === "number" && typeof b === "number"
    ? a - b
    : String(a).localeCompare(String(b), "fi", { numeric: true });
  return r * dir;
};

// rows: arrays of cells (primitive, Node or cell()). num: indexes of right-aligned columns.
// Click a header to sort ascending, again for descending, a third time to reset.
export function table(heads, rows, { num = [], nullText = "\u2013" } = {}) {
  const wrap = el("div", "wrap");
  if (!rows.length) { wrap.append(el("div", "empty", "Nothing here yet.")); return wrap; }

  const scroller = el("div", "scroll");
  const t = el("table");
  const hr = t.createTHead().insertRow();
  const tb = t.createTBody();
  const ths = [];
  let col = -1, dir = 1;

  const fill = () => {
    const sorted = col < 0 ? rows : [...rows].sort(byColumn(col, dir));
    tb.replaceChildren();
    for (const r of sorted) {
      const tr = tb.insertRow();
      r.forEach((c, i) => {
        const td = tr.insertCell();
        const show = isCell(c) ? c.show : c;
        td.append(show == null ? nullText : show);
        td.className = [num.includes(i) && "num", isCell(c) && c.cls].filter(Boolean).join(" ");
      });
    }
    ths.forEach((th, i) => {
      if (i === col) th.setAttribute("aria-sort", dir > 0 ? "ascending" : "descending");
      else th.removeAttribute("aria-sort");
    });
  };

  heads.forEach((h, i) => {
    const th = el("th", num.includes(i) ? "num" : "");
    const b = el("button", "th-btn", h);
    b.type = "button";
    b.onclick = () => {
      if (col !== i) { col = i; dir = 1; } else if (dir === 1) dir = -1; else col = -1;
      fill();
    };
    th.append(b);
    ths.push(th);
    hr.append(th);
  });

  fill();
  scroller.append(t);
  wrap.append(scroller);
  return wrap;
}
