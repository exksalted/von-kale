import math
import re
import sys
import time
from collections import Counter

import requests

from config import LAKE_FISHES, NICKS, SEASON, SEASON_PARAM, SPECIAL_FISH_NAMES, fishes_for
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
