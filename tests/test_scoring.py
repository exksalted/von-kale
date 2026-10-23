import math

import pytest

from db import connect
from helpers import load

records = load("records")


def test_score_values():
    assert records.score(1, 1, 1.0) == (1.0, 0.0)
    pct, sc = records.score(1, 2, 1.0)
    assert pct == 0.5 and sc == pytest.approx(1.0)
    assert records.score(1, 4, 1.0)[1] == pytest.approx(1 / (math.sqrt(2) - 1))


def test_rarer_fish_score_higher():
    assert records.score(1, 10, 4.0)[1] > records.score(1, 10, 1.0)[1]


def _db_with(totals, recs):
    con = connect(":memory:")
    con.executemany("INSERT INTO totalrecords (Season, Lake_ID, Fish_ID, Players, Rarity) VALUES (?,?,?,?,?)", totals)
    con.executemany("INSERT INTO records (Season, Rank, Nick, Lake_ID, Fish_ID) VALUES (?,?,?,?,?)", recs)
    return con


def test_refresh_scores_fills_columns():
    con = _db_with([("0_0", 1, 1, 10, 1.0)], [("0_0", 2, "a", 1, 1)])
    assert records.refresh_scores(con, "0_0") == 0
    out_of, pct, sc = con.execute("SELECT Out_Of, Percentile, Score FROM records").fetchone()
    assert out_of == 10 and pct == pytest.approx(0.2)
    assert sc == pytest.approx((math.sqrt(5) - 1) / (math.sqrt(2) - 1))


def test_rank_above_out_of_is_clamped():
    con = _db_with([("0_0", 1, 1, 3, 1.0)], [("0_0", 5, "a", 1, 1)])
    assert records.refresh_scores(con, "0_0") == 1
    out_of, pct, sc = con.execute("SELECT Out_Of, Percentile, Score FROM records").fetchone()
    assert (out_of, pct, sc) == (5, 1.0, 0.0)


def test_unknown_lake_fish_gets_no_score():
    con = _db_with([("0_0", 1, 1, 3, 1.0)], [("0_0", 1, "a", 2, 9)])
    records.refresh_scores(con, "0_0")
    assert con.execute("SELECT Out_Of, Score FROM records").fetchone() == (None, None)


def test_refresh_requires_totals():
    con = _db_with([], [("0_0", 1, "a", 1, 1)])
    with pytest.raises(records.ScrapeError):
        records.refresh_scores(con, "0_0")
  
