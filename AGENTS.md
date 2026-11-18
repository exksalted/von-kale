# Team Von-Kale records: context for AI agents

Last updated: 2026-11-18. Read this before changing anything. It records decisions made with the
owner, including things that look like bugs but are intentional. Don't "fix" those without asking.

## What this is

A static website showing fishing records of a small team in **Propilkki 2** (a Finnish ice-fishing game). Python scripts scrape the game's leaderboards into a small SQLite DB
(`pp2_00.db`, ~370 KB, growing ~100 KB/year). The site loads that DB in the browser with sql.js and queries it
client-side. No server, no logins, no secrets (so security hardening is not a priority).

Data flow:

```
totals.py  -> totalrecords table (players per lake/fish board)
records.py -> records table (team members' ranks) + scores
   -> DB uploaded as asset pp2_00.db on GitHub release "db-latest"
   -> deploy.yml: site/ + latest DB -> GitHub Pages
```

## Repo layout

```
.github/workflows/  update-db.yml, deploy.yml, test.yml
config.py db.py scraper.py totals.py records.py   (repo root; scripts run as `python totals.py`)
tests/              pytest suite (49 tests, no network)
site/               index.html matrix.html profile.html + index.js matrix.js profile.js common.js style.css favicon.svg
pytest.ini  requirements.txt  requirements-dev.txt  .gitignore (*.db is ignored)

```
Local use: `pip install -r requirements-dev.txt && pytest -q`. To run the site, copy `pp2_00.db` into `site/`
and serve it over HTTP (`python -m http.server`). ES modules and the DB fetch don't work from `file://`.
Scrape locally with env vars: `NICKS="a,b" SEASON=1,18 python records.py`.

## Domain model

- **Season codes**: the site/config use `"0,0"`, the DB stores `"0_0"`. `0_0` = all time. `1_N` = the season
  starting **1 July 2008+N** and ending 30 June the next year (`1_18` = 2026-27). UI labels: "Season 2026-27".
- **Fish_ID**: `< 50` are fish species (nothing in 50-109), `>= 110` are competitions. The code splits at 100:
  fish = `Fish_ID < 100`, competition = `Fish_ID > 100` (`FISH_SQL`/`COMP_SQL`, `isFish`/`isComp` in common.js).
  The value 100 itself is never used; that is not a bug.
- **Tables**
  - `records(Season, Rank, Nick, Type, Lake, Date, Weight, Lake_ID, Fish_ID, Percentile, Score, Out_Of, Rarity)`.
    `Date` is an ISO string, `Weight` is in grams.
  - `totalrecords(Season, Lake_ID, Fish_ID, Players, Rarity)`.
  - Unique indexes `uq_records(Season, Nick, Lake_ID, Fish_ID)` and `uq_totals(Season, Lake_ID, Fish_ID)`;
    `PRAGMA user_version = 2`. `init_schema` upgrades older DBs in place.
- **Score**: `pct = Rank / Out_Of`; `Score = (sqrt(Rarity / pct) - 1) / (sqrt(2) - 1)`.
  - `Out_Of` = Players on that board.
  - **Rarity** = (max Players among ALL boards of the lake, **competitions included, intentionally**) / Players of
    this fish. Competitions (`Fish_ID > 100`) have Rarity 1.0; a board with 0 players has Rarity 0.0.
  - If `Rank > Out_Of` (totals and records are scraped minutes apart), `Out_Of` is raised to `Rank` and **stored**.
  - Scores are recomputed for ALL rows of the season on every records run.
- **Record holder** = per (Season, Lake_ID, Fish_ID), highest Score; ties go to the earlier date, then nick
  (`holdersSql` in common.js is the single source). Season is in the partition, so "All seasonal records" yields
  one holder per season/lake/type, not one overall.
- **Nick filter on "All team records"** (index) applies *after* the holder is chosen, i.e. "records held by that
  player", the same as "Team records held" on the profile page.

## Scraping (propilkki.fi)

- Responses are cp1252. The player's row is the one whose `<td>` has class `select`.
- Finnish headers: Sija (rank), Pelaaja (player), Kalalaji (fish type), Järvi (lake), Päiväys (date),
  Kalan paino / Kokonaispaino (weight / total weight, for competitions).
- Session token comes from `iframe#iframe1` `src` (`t=`); a hard-coded fallback exists and logs a warning.
- Totals count players as rows on the page plus the last page (max `row=` link). The owner verified this is correct.
- Lakes and their fish IDs live in `config.LAKE_FISHES`; each lake also scans the global competition IDs
  (`fishes_for(lake)`). Don't edit that data casually.

## Pipeline safety decisions

Principle: a bad scrape must never reach the published DB. On failure the DB is left untouched.

- Writes happen in a single transaction; `ScrapeError` (bad data) and `requests.RequestException` (network)
  both exit 1.
- **totals guards** (constants in totals.py): abort if everything is 0, more than 50% of counts are 0, or the new
  player total is below 50% of the stored one.
- **records guards**: required columns must exist; incomplete rows abort; abort if a configured player scrapes
  below 50% of their stored record count (stops silent partial overwrites).
- Old rows are deleted by configured nick **and** returned name, case-insensitively (`COLLATE NOCASE`).
- Duplicate rows in one scrape: warn, keep the better rank. Date warnings (unparseable, outside the season
  window) are warnings only.
- `VACUUM` after writing. The workflow checks `PRAGMA integrity_check` and a non-empty `records` before upload,
  and keeps a 30-day artifact backup (the release upload with `--clobber` replaces the only copy).

## Workflows

- **update-db.yml**: cron weekly (Mon 03:00 UTC) + `workflow_dispatch` (inputs `nicks`, `season`, `skip_totals`).
  Downloads the previous DB from the `db-latest` release, runs totals then records, uploads, then calls deploy.yml.
- **Only season `0_0` is auto-updated, intentionally.** A new season is added manually once, after it ends
  (e.g. run with season `1,18` after 30 June 2027, once per nick), and again manually when a player is added.
- **deploy.yml**: no scraping. Builds `_site/` from `site/` + the DB in the latest release and deploys to Pages.
  Triggers: manual, `workflow_call` (from update-db), and push to `main` touching `site/**`.
  The caller of a reusable workflow must grant `pages: write` and `id-token: write`. Pages source must be
  "GitHub Actions".
- **test.yml**: runs pytest on pushes touching Python/tests.
- GitHub disables scheduled workflows after 60 days without repo activity (public repos); releases don't count.

## Frontend decisions

- No build step. Plain ES modules (`<script type="module">`); sql.js 1.10.3 is loaded from cdnjs with an SRI hash
  (computed from the npm package; SRI covers only the JS, not the `.wasm`). When bumping the version, recompute
  the hash and update the `<script>` tags in all three HTML files plus `SQLJS_VERSION` in common.js.
- Client-side SQLite is intentional because the DB is tiny. Pre-aggregating to JSON was considered and postponed.
- `common.js` holds all shared helpers (DOM `el`, `q`, `start`, season helpers, URL state, `nameEl`/`scoreEl`,
  sortable `table`, `holdersSql`, nav). Don't duplicate them in page scripts.
- **Presentation lives in JS, not SQL**: queries return raw numbers; JS adds " g" and formats scores with
  `toFixed(2)`. Table cells use `cell(sortValue, display, cls)`; nulls always sort last; headers cycle
  asc / desc / off.
- **Shareable URLs** (defaults omitted): index `preset, nick, lake, type, season`; matrix `season, lake`;
  profile `nick, season`.
- Season dropdowns: all time first, then "All seasonal records" (value `seasons`, SQL `Season <> '0_0'`),
  then newest season first. **The matrix intentionally has no "All seasonal records" option.**
- Player names are real `<a>` links to `profile.html?nick=...&season=...` (season omitted for `0_0`).
- **Index page**: presets plus Nick/Lake/Type/Season filters; "Advanced: edit SQL" textarea. If SQL was
  hand-edited, changing a filter asks for confirmation. Ctrl/Cmd+Enter runs. The textarea grows to its content.
- **Page scrolls, not boxes**: tables and textareas never scroll vertically; tables scroll sideways only when too
  wide. Consequence: no sticky table headers.
- **Matrix**: one card per lake with a header row (Player, Type, Weight, Rank, Score) on shared column tracks.
  Cards are at least 512px wide; below ~32rem rows scroll sideways on phones. Words must never break mid-word
  (long names like "Harmaanieriä"). Competition rows sit under a "Competitions" divider.
- **Profile**: tabs Overview / All records / By lake / By species / Team records. One shared
  All/Fish/Competitions select sits in the tab row after "Team records" and shows only on the two record tabs.
  In "All seasonal records" mode the record tables gain a Season column. The "Team records held" stat card is a
  button that opens that tab.
- **Styling**: dark theme; every alpha/hex colour is a CSS token in `:root` (no hard-coded hex alphas elsewhere);
  one base `.btn` class plus `.tab`; `.name` is defined once; use `100dvh`. Name colours (`NAME_COLORS`, lowercase
  keys) and score tiers (`SCORE_TIERS`) live in common.js.
- **Accessibility**: everything is keyboard operable (links/buttons, no clickable spans), `aria-sort` on sortable
  headers, `aria-current` for nav and tabs, `aria-label` on selects, `role="status"` on the status line, visible
  `:focus-visible`, table roles on matrix cards. The status variable is `statusEl` (don't shadow `window.status`).
- Known gap: matrix row dates are only a `title` tooltip (not available on touch/keyboard).

## Testing notes

- `pytest -q` runs 49 offline tests (`FakeSession` / `board()` HTML builder in `tests/helpers.py`).
- Tests import `records` through `helpers.load("records")`, which finds the file by path (works with tests in
  `tests/` or in a flat layout), so a same-named folder can't shadow it.
- A CI failure once came from truncated/mis-formatted copies of `records.py` and `helpers.py`. If imports
  mysteriously miss names, check that the files are complete.
- Nothing here has been run against the live site by an AI agent; the scrapers are tested with fake responses only.

## Lake viewer (separate tool, not part of the site)

`lake_viewer.html` is a stand-alone page built by the game-data pipeline (`viewer_template.html` +
`build_viewer.py`), with live data from `read_fish.py --serve`. It is a personal tool for single-player/offline
play, not published with the site. The pipeline and its user guide are no longer kept up to date for other users;
change the template only. Where its choices differ from the site rules above, the site rules win, except for the
  table rules under "Side panels" below, which apply to the viewer only.

- **Removed on purpose** (don't bring back): the type-map layer (the game never uses it because of a coordinate
  bug), the "(fish area / record area)" text, the dot-radius scale input, the "Paste JSON (rarely needed)" box,
  the "Download recorded positions (CSV)" button, the hole-size selector and the hole-fit chance.
- **Species**: Made is off by default. Buttons in the order All, Made (only Made), None.
- **Fish groups table** columns: species, rec, n, mean g ±sd, top g ±sd (abbreviated), radius. Buttons Tick all,
  Tick biggest, Untick all. "Tick biggest" ticks, per species, every record with the largest top mean + 2 × top sd
  (ties all ticked).
- **Hover on the map**: `x, y | cell (a,b) | depth N cm`, then "visible groups here". A hotspot line appears only
  when the pointer is inside a hotspot's radius; species with the same value per stimulus are grouped
  ("0.100 per stimulus: A, B, C; ...").
- **Hover on a live fish**: rec #, species, radius, mean ±sd, and top mean ±sd only if it differs. No bait likes,
  shyness, hole-fit chance or "size drawn only at a bite" text.
- **Players**: you in red, other players/bots in blue.
- **Holes**: all drawn the same (hole size is not readable yet), as a high-contrast marker: dark halo, turquoise
  ring, red centre; a larger red centre means occupied. No small/big legend.
- **Live fish**: trails off by default, with "Clear trails" next to the trails box. Heading arrows on by default,
  with an arrowhead; length = distance the group covers in 60 s at its current speed. A group counts as stopped
  after 1.5 s without a position change (readings arrive once a second, so 1 s made it flicker).
- **Highlighted records**: the live table shows only rec, species, top g, top sd, radius. Highlighted groups show
  their mood in the label. Their area (rectangle/ellipse) is hidden unless "area of highlighted" is ticked.
- **Bite reach** dot mode: three rings, no gradient. Solid ring with a light shaded disc = 50 % (0.57 × record
  radius), dashed = 25 % (1.03 ×), dotted = 0 % cut-off (1.64 ×). These follow the game's range factor
  `0.5·2^(-4q) + 0.5 - 0.5q`; the record radius itself is not a boundary.
- **Side panels**: stretching is preferred over scrolling. Tables never scroll sideways: the side panel widens to fit
  the widest fish-group table. The fish-group and highlight (live) tables may scroll vertically; everything else
  grows instead. The bait-likes box has no inner scrollbar and hides baits whose range is -100..-100. "This game's lure ratings" and "This game's bait likes" are separate collapsible boxes.

## Open / deferred

- "Total fish score" / "Total competition score" presets sum across all seasonal records when "All seasonal
  records" is selected; a per-season breakdown (`GROUP BY Season, Nick`) was offered but not requested.
- Editing the index page's SQL editor functionality was explicitly postponed.
