"""Everything that talks to propilkki.fi, shared by totals.py and records.py."""
import os
import re
import time

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.propilkki.fi/propilkki2/P2_records/P2_records.php"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}
FALLBACK_TOKEN = "1792154187"


class ScrapeError(Exception):
    """The site answered, but not with what we expect (or the data looks wrong). Never retried."""


def warn(msg):
    """Shows up as an annotation in the GitHub Actions run summary."""
    print(f"::warning::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"WARNING: {msg}")


def fetch(session, params=None):
    """GET with retries. Raises requests.RequestException after 3 failed attempts."""
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
    warn("Could not read the session token from the site; using the fallback token.")
    return FALLBACK_TOKEN


def table_parts(soup):
    """(headers, body rows) of the leaderboard table; ([], []) if the page has none."""
    table = soup.find("table", {"id": "myTable"})
    if not table:
        return [], []
    thead, tbody = table.find("thead"), table.find("tbody")
    headers = [th.get_text(strip=True) for th in thead.find_all("th")] if thead else []
    trs = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]
    return headers, trs


def count_rows(soup):
    return len(table_parts(soup)[1])
    
