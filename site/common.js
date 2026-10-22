const NAME_COLORS = {
  "liilu:3": "#a30465",
  "pumpkin": "#FF7518",
  "exksa": "#7ba63f",
  "kuhasalaliitto": "#6495ED"
};

// Lower bound inclusive; first match from the top wins.
const SCORE_TIERS = [
  [100, "#DC2367"],
  [50,  "#E03030"],
  [10,  "#D35400"],
  [5,   "#F1C40F"],
  [3,   "#7D3C98"],
  [2,   "#2471A3"],
  [1,   "#27AE60"],
  [0.3, "#C5CAD3"],
  [-Infinity, "#565c68"]
];
const scoreColor = v => (SCORE_TIERS.find(t => v >= t[0]) || SCORE_TIERS[SCORE_TIERS.length - 1])[1];

function scoreEl(v) {
  const span = document.createElement("span");
  span.className = "score";
  span.textContent = v.toFixed(2);
  span.style.setProperty("--c", scoreColor(v));
  return span;
}

function nameEl(nick, link = true) {
  const span = document.createElement("span");
  span.className = "name";
  span.textContent = nick;
  const col = NAME_COLORS[String(nick).trim().toLowerCase()];
  if (col) span.style.setProperty("--c", col);
  if (link) {
    span.title = "View profile";
    span.onclick = () => {
      const sv = (document.getElementById("season") || document.getElementById("f-Season"))?.value;
      location.href = "profile.html?nick=" + encodeURIComponent(nick) + (sv && sv !== "0_0" ? "&season=" + encodeURIComponent(sv) : "");
    };
  } else span.style.cursor = "default";
  return span;
}

async function loadDb() {
  if (typeof initSqlJs !== "function") throw new Error("sql.js did not load (CDN blocked?)");
  const SQL = await initSqlJs({ locateFile: f => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/${f}` });
  const resp = await fetch("pp2_00.db");
  if (!resp.ok) throw new Error(`DB download failed (${resp.status})`);
  return new SQL.Database(new Uint8Array(await resp.arrayBuffer()));
}

// Front-end names for season codes: 0_0 = all time, 1_N = the season starting in 2008+N
function seasonLabel(code) {
  if (code === "0_0") return "All time";
  const m = /^1_(\d+)$/.exec(code);
  if (!m) return "Season " + code;
  const y = 2008 + Number(m[1]);
  return `Season ${y}-${String(y + 1).slice(2)}`;
}
