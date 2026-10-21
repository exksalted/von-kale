import math
import re
import sqlite3
import sys
import time

import requests

from config import (NICKS, list_value, lake_specific_fishes,
                    global_special_fishes, special_fish_names)
from totals import DB_PATH, fetch, get_token  # fetch() raises RequestException after 3 tries


def scrape_leaderboard(session, token, nick, lake, fish):
    """Highlighted rows for this nick. [] if none. Raises on network failure."""
    soup = fetch(session, {
        "f": "1", "t": token, "list": list_value, "lake": str(lake), "fish": str(fish),
        "nick": nick, "row": "0", "game_info": "0", "fish_info": "0", "lang": "fi",
    })
    table = soup.find("table", {"id": "myTable"})
    thead = table.find("thead") if table else None
    if not thead:
        return []
    headers = [th.get_text(strip=True) for th in thead.find_all("th")]
    tbody = table.find("tbody")
    trs = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

    out = []
    for tr in trs:
        cells = tr.find_all("td")
        if not cells or not any("select" in c.get("class", []) for c in cells):
            continue  # not the searched player's row
        out.append(dict(zip(headers, (c.get_text(strip=True) for c in cells))))
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


def scrape_nick(session, token, nick):
    rows = []
    for lake in range(1, 47):
        if not scrape_leaderboard(session, token, nick, lake, 0):
            continue  # player not on this lake
        print(f"{nick}: lake {lake}")
        fishes = list(dict.fromkeys(lake_specific_fishes.get(lake, []) + global_special_fishes))
        for fish in fishes:
            for rec in scrape_leaderboard(session, token, nick, lake, fish):
                rows.append((
                    parse_rank(rec.get("Sija")),
                    rec.get("Pelaaja"),
                    special_fish_names.get(fish, rec.get("Kalalaji")),
                    rec.get("Järvi"),
                    iso_date(rec.get("Päiväys")),
                    parse_weight(rec.get("Kalan paino", rec.get("Kokonaispaino"))),
                    lake,
                    fish,
                ))
            time.sleep(0.1)
    return rows


def refresh_scores(con, season):
    """Recompute Out_Of/Rarity/Percentile/Score for ALL rows of the season."""
    totals = {(l, f): (p, r) for l, f, p, r in con.execute(
        "SELECT Lake_ID, Fish_ID, Players, Rarity FROM totalrecords WHERE Season = ?", (season,))}
    if not totals:
        raise SystemExit(f"No totalrecords for season {season}. Run totals.py first.")

    updates = []
    for rowid, rank, lake, fish in con.execute(
            "SELECT rowid, Rank, Lake_ID, Fish_ID FROM records WHERE Season = ?", (season,)).fetchall():
        out_of, rarity = totals.get((lake, fish), (None, None))
        pct = score = None
        if rank and out_of and rarity is not None:
            pct = rank / out_of
            score = (math.sqrt(rarity / pct) - 1) / (math.sqrt(2) - 1)
        updates.append((out_of, rarity, pct, score, rowid))
    con.executemany(
        "UPDATE records SET Out_Of=?, Rarity=?, Percentile=?, Score=? WHERE rowid=?", updates)


def save(season, rows, db_path=DB_PATH):
    con = sqlite3.connect(db_path)
    try:
        with con:  # single transaction
            con.execute("""CREATE TABLE IF NOT EXISTS records (
                Season TEXT, Rank INTEGER, Nick TEXT, Type TEXT, Lake TEXT, Date TEXT,
                Weight INTEGER, Lake_ID INTEGER, Fish_ID INTEGER,
                Percentile REAL, Score REAL, Out_Of INTEGER, Rarity REAL)""")
            con.execute("CREATE INDEX IF NOT EXISTS idx_rec ON records(Season, Nick)")
            nicks = {r[1] for r in rows}
            con.executemany("DELETE FROM records WHERE Season = ? AND Nick = ?",
                            [(season, n) for n in nicks])
            con.executemany(
                """INSERT INTO records (Season, Rank, Nick, Type, Lake, Date, Weight, Lake_ID, Fish_ID)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                [(season, *r) for r in rows])
            refresh_scores(con, season)
        bad = con.execute("SELECT COUNT(*) FROM records WHERE Season = ? AND date(Date) IS NULL",
                          (season,)).fetchone()[0]
        if bad:
            print(f"WARNING: {bad} rows have unparseable dates.")
    finally:
        con.close()


def main():
    season = list_value.replace(",", "_")
    rows = []
    with requests.Session() as session:
        token = get_token(session)
        for nick in NICKS:
            try:
                rows += scrape_nick(session, token, nick)
            except requests.RequestException as e:
                print(f"FAILED for {nick}: {e}. DB left untouched.")
                sys.exit(1)
    if not rows:
        print("No records found; nothing written.")
        return
    save(season, rows)
    print(f"Saved {len(rows)} records for season '{season}'.")


if __name__ == "__main__":
    main()
