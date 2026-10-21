import re
import sqlite3
import sys
import time

import requests
from bs4 import BeautifulSoup

from config import (NICKS, list_value, lake_specific_fishes,
                    global_special_fishes, special_fish_names)

DB_PATH = "pp2_00.db"
BASE_URL = "https://www.propilkki.fi/propilkki2/P2_records/P2_records.php"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}
FALLBACK_TOKEN = "1792154187"


def fetch(session, params=None):
    """GET with retries. Raises after 3 failed attempts."""
    for attempt in range(3):
        try:
            r = session.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
            r.raise_for_status()
            r.encoding = "cp1252"
            return BeautifulSoup(r.text, "html.parser")
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def get_token(session):
    try:
        soup = fetch(session)
        iframe = soup.find("iframe", id="iframe1")
        if iframe and iframe.get("src"):
            m = re.search(r"[?&]t=(\d+)", iframe["src"])
            if m:
                return m.group(1)
    except requests.RequestException:
        pass
    return FALLBACK_TOKEN


def count_rows(soup):
    table = soup.find("table", {"id": "myTable"})
    if not table:
        return 0
    tbody = table.find("tbody")
    return len(tbody.find_all("tr")) if tbody else len(table.find_all("tr")[1:])


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


def save_to_sqlite(records, season, db_path=DB_PATH):
    con = sqlite3.connect(db_path)
    try:
        with con:  # one transaction: commits on success, rolls back on error
            con.execute("""CREATE TABLE IF NOT EXISTS totalrecords
                (Season TEXT, Lake_ID INTEGER, Fish_ID INTEGER, Players INTEGER, Rarity REAL)""")
            con.execute("""CREATE INDEX IF NOT EXISTS idx_tr
                ON totalrecords(Season, Lake_ID, Fish_ID)""")
            con.execute("DELETE FROM totalrecords WHERE Season = ?", (season,))
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
    finally:
        con.close()


def main():
    season = list_value.replace(",", "_")
    records, failures = [], []

    with requests.Session() as session:
        token = get_token(session)
        for lake, fishes in lake_specific_fishes.items():
            combined = list(dict.fromkeys(fishes + global_special_fishes))
            print(f"Scanning Lake {lake}...")
            for fish in combined:
                try:
                    n = get_total_players(session, token, lake, fish, list_value)
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

    save_to_sqlite(records, season)
    print(f"Saved {len(records)} rows for season '{season}'.")


if __name__ == "__main__":
    main()
