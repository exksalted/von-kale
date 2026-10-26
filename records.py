import math
import re
import sys
import time
from collections import Counter

import requests

from config import LAKES, NICKS, SEASON, SEASON_PARAM, SPECIAL_FISH_NAMES, fishes_for, lake_filter
from db import connect, vacuum
from scraper import ScrapeError, fetch, get_token, table_parts, warn

REQUIRED_HEADERS = {"Sija", "Pelaaja", "Järvi", "Päiväys"}
WEIGHT_HEADERS = ("Kalan paino", "Kokonaispaino")
MIN_KEEP_RATIO = 0.5   # a player scraping below this share of their stored records -> abort


def check_headers(headers):
    missing = REQUIRED_HEADERS - set(headers)
    if missing or not any(h in headers for h in WEIGHT_HEADERS):
        raise ScrapeError(f"Leaderboard columns changed (found {headers}); "
                          f"missing: {sorted(missing) or list(WEIGHT_HEADERS)}.")


def scrape_leaderboard(session, token, nick, lake, fish):
    """Highlighted rows for this nick. [] if none. Raises on network failure or a changed layout."""
    soup = fetch(session, {
        "f": "1", "t": token, "list": SEASON_PARAM, "lake": str(lake), "fish": str(fish),
        "nick": nick, "row": "0", "game_info": "0", "fish_info": "0", "lang": "fi",
    })
    headers, trs = table_parts(soup)
    if not headers:
        return []

    out = []
    for tr in trs:
        cells = tr.find_all("td")
        if not cells or not any("select" in c.get("class", []) for c in cells):
            continue  # not the searched player's row
        out.append(dict(zip(headers, (c.get_text(strip=True) for c in cells))))
    if out:
        check_headers(headers)
    return out


def parse_rank(s):
    digits = re.sub(r"\D", "", s or "")
    return int(digits) if digits else None


def parse_weight(s):
    s = re.sub(r"[\s\u00a0]", "", s or "")
    s = re.sub(r"g$", "", s).replace(",", ".")
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f.is_integer() else f


def iso_date(s):
    m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", s or "")
    return f"{m[3]}-{m[2]}-{m[1]}" if m else s


def to_row(rec, lake, fish):
    """(rank, nick, type, lake name, date, weight, lake id, fish id); ScrapeError if incomplete."""
    nick = (rec.get("Pelaaja") or "").strip()
    kind = SPECIAL_FISH_NAMES.get(fish) or rec.get("Kalalaji")
    if not (nick and kind and rec.get("Järvi")):
        raise ScrapeError(f"Incomplete row for lake {lake}, fish {fish}: {rec}")
    return (
        parse_rank(rec.get("Sija")),
        nick,
        kind,
        rec["Järvi"],
        iso_date(rec.get("Päiväys")),
        parse_weight(rec.get("Kalan paino", rec.get("Kokonaispaino"))),
        lake,
        fish,
    )


def scrape_nick(session, token, nick):
    rows = []
    for lake in LAKES:
        if not scrape_leaderboard(session, token, nick, lake, 0):
            continue  # player not on this lake
        print(f"{nick}: lake {lake}")
        for fish in fishes_for(lake):
            for rec in scrape_leaderboard(session, token, nick, lake, fish):
                rows.append(to_row(rec, lake, fish))
            time.sleep(0.1)
    return rows


def score(rank, out_of, rarity):
    """(percentile, score). Needs rank >= 1 and out_of >= rank."""
    pct = rank / out_of
    return pct, (math.sqrt(rarity / pct) - 1) / (math.sqrt(2) - 1)


def refresh_scores(con, season):
    """Recompute Out_Of/Rarity/Percentile/Score for ALL rows of the season. Returns how many Out_Of were raised."""
    totals = {(l, f): (p, r) for l, f, p, r in con.execute(
        "SELECT Lake_ID, Fish_ID, Players, Rarity FROM totalrecords WHERE Season = ?", (season,))}
    if not totals:
        raise ScrapeError(f"No totalrecords for season {season}. Run totals.py first.")

    updates, raised = [], 0
    for rowid, rank, lake, fish in con.execute(
            "SELECT rowid, Rank, Lake_ID, Fish_ID FROM records WHERE Season = ?", (season,)).fetchall():
        out_of, rarity = totals.get((lake, fish), (None, None))
        pct = sc = None
        if rank and out_of and rarity is not None:
            if rank > out_of:  # totals and records are scraped minutes apart; the board grew in between
                out_of = rank
                raised += 1
            pct, sc = score(rank, out_of, rarity)
        updates.append((out_of, rarity, pct, sc, rowid))
    con.executemany(
        "UPDATE records SET Out_Of=?, Rarity=?, Percentile=?, Score=? WHERE rowid=?", updates)
    return raised


def dedupe(rows):
    """One row per (nick, lake, fish); on a clash keep the better rank and warn."""
    best = {}
    for r in rows:
        key = (r[1], r[6], r[7])
        old = best.get(key)
        if old is None:
            best[key] = r
            continue
        warn(f"Duplicate record for {key}; keeping the better rank.")
        if (r[0] is None, r[0] or 0) < (old[0] is None, old[0] or 0):
            best[key] = r
    return list(best.values())


def check_not_collapsed(con, season, nicks, rows, lakes=None):
    """Refuse to overwrite when a configured player suddenly has far fewer records than stored."""
    found = Counter(r[1].casefold() for r in rows)
    for nick in nicks:
        old = con.execute("SELECT COUNT(*) FROM records WHERE Season = ? AND Nick = ? COLLATE NOCASE"
                          + lake_filter(lakes), (season, nick)).fetchone()[0]
        new = found.get(nick.casefold(), 0)
        if old and new < MIN_KEEP_RATIO * old:
            raise ScrapeError(f"{nick}: scraped {new} records but {old} are stored for season {season}.")


def season_window(season):
    """(first, last) ISO dates of a season code like '1_18' (1 Jul 2026 - 30 Jun 2027); None for all time."""
    m = re.fullmatch(r"1_(\d+)", season)
    if not m:
        return None
    y = 2008 + int(m[1])
    return f"{y}-07-01", f"{y + 1}-06-30"


def check_dates(con, season):
    bad = con.execute("SELECT COUNT(*) FROM records WHERE Season = ? AND date(Date) IS NULL",
                      (season,)).fetchone()[0]
    if bad:
        warn(f"{bad} rows have unparseable dates.")
    window = season_window(season)
    if window:
        outside = con.execute(
            "SELECT COUNT(*) FROM records WHERE Season = ? AND date(Date) IS NOT NULL AND Date NOT BETWEEN ? AND ?",
            (season, *window)).fetchone()[0]
        if outside:
            warn(f"{outside} rows are dated outside season {season} ({window[0]} to {window[1]}).")


def save(season, rows, nicks, con, lakes=None):
    """Replaces the stored records of the given players (on the scanned lakes) for the season.
    Returns the number saved."""
    rows = dedupe(rows)
    check_not_collapsed(con, season, nicks, rows, lakes)
    if not rows:
        print("No records found; nothing written.")
        return 0

    # Match case-insensitively on both the configured nicks and the names the site returned,
    # so a 'ademan' vs 'Ademan' mismatch can't leave duplicates behind.
    names = {n.casefold() for n in nicks} | {r[1].casefold() for r in rows}
    with con:  # single transaction
        con.executemany("DELETE FROM records WHERE Season = ? AND Nick = ? COLLATE NOCASE"
                        + lake_filter(lakes), [(season, n) for n in names])
        con.executemany(
            """INSERT INTO records (Season, Rank, Nick, Type, Lake, Date, Weight, Lake_ID, Fish_ID)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            [(season, *r) for r in rows])
        raised = refresh_scores(con, season)
    if raised:
        print(f"Raised Out_Of to Rank on {raised} records (leaderboards grew during the run).")
    check_dates(con, season)
    return len(rows)


def main():
    rows = []
    with requests.Session() as session:
        token = get_token(session)
        for nick in NICKS:
            rows += scrape_nick(session, token, nick)

    con = connect()
    try:
        n = save(SEASON, rows, NICKS, con)
        if n:
            vacuum(con)
            print(f"Saved {n} records for season '{SEASON}'.")
    finally:
        con.close()


if __name__ == "__main__":
    try:
        main()
    except (requests.RequestException, ScrapeError) as e:
        print(f"FAILED: {e} DB left untouched.")
        sys.exit(1)
