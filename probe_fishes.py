"""Find fish IDs missing from config.LAKE_FISHES.

For every lake, queries the all-time (0,0) leaderboard with an empty nick for each fish ID
in the probe range that is NOT already listed for that lake. A non-empty leaderboard means
the fish exists there. Read-only: no DB access. Any failed request aborts the run.

Usage: python probe_fishes.py [--min 1] [--max 32] [--out missing_fishes.py]
"""
import argparse
import sys
import time

import requests

from config import LAKE_FISHES
from scraper import ScrapeError, fetch, get_token, table_parts

SEASON_ALL_TIME = "0,0"


def probe(session, token, lake, fish):
    """Returns (found, species name or None). Raises on network failure."""
    soup = fetch(session, {
        "f": "1", "t": token, "list": SEASON_ALL_TIME, "lake": str(lake), "fish": str(fish),
        "nick": "", "row": "0", "game_info": "0", "fish_info": "0", "lang": "fi",
    })
    headers, trs = table_parts(soup)
    if not headers or not trs:
        return False, None

    name = None
    if "Kalalaji" in headers:
        cells = trs[0].find_all("td")
        idx = headers.index("Kalalaji")
        if idx < len(cells):
            name = cells[idx].get_text(strip=True) or None
    return True, name


def sanity_check(session, token):
    """A known lake/fish pair must return rows, otherwise the token/layout is broken."""
    lake = next(iter(LAKE_FISHES))
    fish = LAKE_FISHES[lake][0]
    found, _ = probe(session, token, lake, fish)
    if not found:
        raise ScrapeError(f"Control query (lake {lake}, fish {fish}) returned no rows. "
                          f"The token or page layout is probably broken.")


def write_output(path, missing, names):
    lines = ["# Fish IDs found on the all-time leaderboard but absent from LAKE_FISHES.",
             "MISSING_FISHES = {"]
    for lake, ids in missing.items():
        label = ", ".join(f"{i}={names.get(i, '?')}" for i in ids)
        lines.append(f"    {lake}: {ids},  # {label}")
    lines.append("}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--min", type=int, default=1, dest="lo")
    ap.add_argument("--max", type=int, default=32, dest="hi")
    ap.add_argument("--out", default="missing_fishes.py")
    args = ap.parse_args()

    missing, names = {}, {}
    suspicious = []

    with requests.Session() as session:
        token = get_token(session)
        sanity_check(session, token)

        for lake, known in LAKE_FISHES.items():
            candidates = [f for f in range(args.lo, args.hi + 1) if f not in known]
            hits = []
            for fish in candidates:
                found, name = probe(session, token, lake, fish)
                if found:
                    hits.append(fish)
                    if name:
                        names.setdefault(fish, name)
                time.sleep(0.1)

            label = ", ".join(f"{i} ({names.get(i, '?')})" for i in hits) or "none"
            print(f"Lake {lake}: missing {label}")
            if hits:
                missing[lake] = hits
            if candidates and len(hits) == len(candidates):
                suspicious.append(lake)

    total = sum(len(v) for v in missing.values())
    print(f"\n{total} missing fish IDs across {len(missing)} lakes.\n")
    print("MISSING_FISHES = {")
    for lake, ids in missing.items():
        print(f"    {lake}: {ids},")
    print("}")

    write_output(args.out, missing, names)
    print(f"\nWrote {args.out}")

    if suspicious:
        print(f"::warning::Every probed ID was a hit on lakes {suspicious}. "
              f"The site may return a default board for invalid fish; verify manually.")


if __name__ == "__main__":
    try:
        main()
    except (requests.RequestException, ScrapeError) as e:
        print(f"FAILED: {e}")
        sys.exit(1)
