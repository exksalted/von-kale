"""Record holder (rank 1) of every lake/fish combo for one season, saved to the bestrecords table.

Uses the same env vars as the other scripts: SEASON (e.g. "0,0") and optionally LAKES.
Replaces the stored rows for that season (and lake subset) in one transaction; any failed
request or sanity-check failure leaves the DB untouched.
"""
import sys
import time

import requests

from config import LAKES, SEASON, SEASON_PARAM, fishes_for, lake_filter
from db import connect, vacuum
from records import check_headers, to_row
from scraper import ScrapeError, fetch, get_token, table_parts

MIN_KEEP_RATIO = 0.5   # fewer combos than this share of the stored ones -> abort
MAX_LISTED_CHANGES = 50

SCHEMA = """
CREATE TABLE IF NOT EXISTS bestrecords (
    Season  TEXT    NOT NULL,
    Lake_ID INTEGER NOT NULL,
    Fish_ID INTEGER NOT NULL,
    Lake    TEXT,
    Type    TEXT,
    Nick    TEXT,
    Weight  REAL,
    Date    TEXT,
    PRIMARY KEY (Season, Lake_ID, Fish_ID)
)"""


def scrape_best(session, token, lake, fish):
    """(Lake_ID, Fish_ID, Lake, Type, Nick, Weight, Date) of the top-ranked row, or None if the
    board is empty. Raises on network failure or a changed layout."""
    soup = fetch(session, {
        "f": "1", "t": token, "list": SEASON_PARAM, "lake": str(lake), "fish": str(fish),
        "nick": "", "row": "0", "game_info": "0", "fish_info": "0", "lang": "fi",
    })
    headers, trs = table_parts(soup)
    if not headers or not trs:
        return None
    cells = trs[0].find_all("td")
    if len(cells) != len(headers):
        return None  # placeholder row such as "no results"
    check_headers(headers)

    rec = dict(zip(headers, (c.get_text(strip=True) for c in cells)))
    rank, nick, kind, lake_name, date, weight, lake_id, fish_id = to_row(rec, lake, fish)
    if rank is not None and rank != 1:
        raise ScrapeError(f"Top row of lake {lake}, fish {fish} has rank {rank}, expected 1.")
    return lake_id, fish_id, lake_name, kind, nick, weight, date


def scrape_all(session, token):
    rows = []
    for lake in LAKES:
        found = 0
        for fish in fishes_for(lake):
            best = scrape_best(session, token, lake, fish)
            if best:
                rows.append(best)
                found += 1
            time.sleep(0.1)
        print(f"Lake {lake}: {found} records")
    return rows


def stored(con, season):
    return {(l, f): (nick, w, d) for l, f, nick, w, d in con.execute(
        "SELECT Lake_ID, Fish_ID, Nick, Weight, Date FROM bestrecords WHERE Season = ?"
        + lake_filter(), (season,))}


def check_not_collapsed(old, rows):
    if old and len(rows) < MIN_KEEP_RATIO * len(old):
        raise ScrapeError(f"Found {len(rows)} records but {len(old)} are stored.")


def report_changes(old, rows):
    changes = []
    for lake, fish, lake_name, kind, nick, weight, date in rows:
        prev = old.get((lake, fish))
        if prev is None:
            if old:
                changes.append(f"NEW      {lake_name} / {kind}: {nick} {weight} ({date})")
        elif prev != (nick, weight, date):
            changes.append(f"CHANGED  {lake_name} / {kind}: {prev[0]} {prev[1]} -> {nick} {weight} ({date})")
    for line in changes[:MAX_LISTED_CHANGES]:
        print(line)
    if len(changes) > MAX_LISTED_CHANGES:
        print(f"... and {len(changes) - MAX_LISTED_CHANGES} more")
    print(f"{len(changes)} new or changed records.")


def save(season, rows, con):
    con.execute(SCHEMA)
    old = stored(con, season)
    check_not_collapsed(old, rows)
    if not rows:
        print("No records found; nothing written.")
        return 0
    report_changes(old, rows)
    with con:  # one transaction
        con.execute("DELETE FROM bestrecords WHERE Season = ?" + lake_filter(), (season,))
        con.executemany(
            "INSERT INTO bestrecords (Season, Lake_ID, Fish_ID, Lake, Type, Nick, Weight, Date) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [(season, *r) for r in rows])
    return len(rows)


def main():
    with requests.Session() as session:
        token = get_token(session)
        rows = scrape_all(session, token)

    con = connect()
    try:
        n = save(SEASON, rows, con)
        if n:
            vacuum(con)
            print(f"Saved {n} best records for season '{SEASON}'.")
    finally:
        con.close()


if __name__ == "__main__":
    try:
        main()
    except (requests.RequestException, ScrapeError) as e:
        print(f"FAILED: {e} DB left untouched.")
        sys.exit(1)
