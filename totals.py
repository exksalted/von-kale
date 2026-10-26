import re
import sys
import time

import requests

from config import LAKES, SEASON, SEASON_PARAM, fishes_for, lake_filter
from db import connect, vacuum
from scraper import ScrapeError, count_rows, fetch, get_token

# Sanity limits for a scrape. A broken token or an error page that still answers HTTP 200
# looks like "0 players everywhere"; these stop that from replacing good data.
MAX_ZERO_SHARE = 0.5       # more than this share of (lake, fish) counts being 0 -> abort
MIN_PREVIOUS_RATIO = 0.5   # new player total below this share of the stored one -> abort


def get_total_players(session, token, lake, fish, list_val):
    params = {
        "f": "1", "t": token, "list": list_val, "lake": str(lake), "fish": str(fish),
        "nick": "", "row": "0", "game_info": "0", "fish_info": "0", "lang": "fi",
    }
    soup = fetch(session, params)  # raises on network failure
    rows_on_page = count_rows(soup)
    if rows_on_page == 0:
        return 0

    max_offset = 0
    for link in soup.find_all("a", href=True):
        m = re.search(r"[?&]row=(\d+)", link["href"])
        if m:
            max_offset = max(max_offset, int(m.group(1)))

    if max_offset == 0:
        return rows_on_page

    last = fetch(session, {**params, "row": str(max_offset)})  # raises, no more guessing
    return max_offset + count_rows(last)


def validate_totals(records, previous_players):
    """Raises ScrapeError if the scraped counts look broken. previous_players = stored sum (0 if none)."""
    total = sum(r["Players"] for r in records)
    if not records or total == 0:
        raise ScrapeError("Every player count is 0. The token or the page layout is probably broken.")
    zeros = sum(1 for r in records if r["Players"] == 0)
    if zeros / len(records) > MAX_ZERO_SHARE:
        raise ScrapeError(f"{zeros} of {len(records)} counts are 0 (limit {MAX_ZERO_SHARE:.0%}).")
    if previous_players and total < MIN_PREVIOUS_RATIO * previous_players:
        raise ScrapeError(f"Player total fell from {previous_players} to {total} "
                          f"(limit: {MIN_PREVIOUS_RATIO:.0%} of the stored value).")


def previous_total(con, season, lakes=None):
    return con.execute("SELECT COALESCE(SUM(Players), 0) FROM totalrecords WHERE Season = ?"
                       + lake_filter(lakes), (season,)).fetchone()[0]


def save_to_sqlite(records, season, con, lakes=None):
    with con:  # one transaction: commits on success, rolls back on error
        con.execute("DELETE FROM totalrecords WHERE Season = ?" + lake_filter(lakes), (season,))
        con.executemany(
            "INSERT INTO totalrecords (Season, Lake_ID, Fish_ID, Players) VALUES (?,?,?,?)",
            [(season, r["Lake_ID"], r["Fish_ID"], r["Players"]) for r in records],
        )
        con.execute("""
            UPDATE totalrecords SET Rarity = CASE
              WHEN Fish_ID > 100 THEN 1.0
              WHEN Players = 0 THEN 0.0
              ELSE (SELECT CAST(MAX(tr.Players) AS REAL) FROM totalrecords tr
                    WHERE tr.Season = totalrecords.Season
                      AND tr.Lake_ID = totalrecords.Lake_ID) / Players
            END
            WHERE Season = ?""", (season,))


def main():
    records, failures = [], []

    with requests.Session() as session:
        token = get_token(session)
        for lake in LAKES:
            print(f"Scanning Lake {lake}...")
            for fish in fishes_for(lake):
                try:
                    n = get_total_players(session, token, lake, fish, SEASON_PARAM)
                except requests.RequestException as e:
                    failures.append((lake, fish, str(e)))
                    print(f"  -> Fish {fish}: FAILED ({e})")
                    continue
                print(f"  -> Fish {fish}: {n} players")
                records.append({"Lake_ID": lake, "Fish_ID": fish, "Players": n})
                time.sleep(0.1)

    if failures:
        print(f"{len(failures)} requests failed. DB left untouched.")
        sys.exit(1)

    con = connect()
    try:
        validate_totals(records, previous_total(con, SEASON))
        save_to_sqlite(records, SEASON, con)
        vacuum(con)
    finally:
        con.close()
    print(f"Saved {len(records)} rows for season '{SEASON}'.")


if __name__ == "__main__":
    try:
        main()
    except ScrapeError as e:
        print(f"FAILED: {e} DB left untouched.")
        sys.exit(1)
