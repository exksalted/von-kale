import pytest

import totals
from db import connect
from scraper import ScrapeError
from helpers import FakeSession, board


def rec(lake, fish, players):
    return {"Lake_ID": lake, "Fish_ID": fish, "Players": players}


# ---- rarity / saving

def rarity(con):
    return {(l, f): r for l, f, r in con.execute("SELECT Lake_ID, Fish_ID, Rarity FROM totalrecords")}


def test_rarity_relative_to_busiest_board_of_the_lake():
    con = connect(":memory:")
    totals.save_to_sqlite([rec(1, 1, 10), rec(1, 3, 5), rec(1, 15, 0), rec(1, 110, 3)], "0_0", con)
    assert rarity(con) == {(1, 1): 1.0, (1, 3): 2.0, (1, 15): 0.0, (1, 110): 1.0}


def test_rarity_max_includes_competitions():
    # intended: the busiest board on the lake counts, competitions included
    con = connect(":memory:")
    totals.save_to_sqlite([rec(1, 1, 10), rec(1, 110, 20)], "0_0", con)
    assert rarity(con)[(1, 1)] == 2.0


def test_save_replaces_only_that_season():
    con = connect(":memory:")
    totals.save_to_sqlite([rec(1, 1, 10)], "0_0", con)
    totals.save_to_sqlite([rec(1, 1, 4)], "1_18", con)
    totals.save_to_sqlite([rec(1, 1, 12)], "0_0", con)
    assert con.execute("SELECT Season, Players FROM totalrecords ORDER BY Season").fetchall() == [("0_0", 12), ("1_18", 4)]
    assert totals.previous_total(con, "0_0") == 12


# ---- validation guards

def test_validate_accepts_normal_data():
    totals.validate_totals([rec(1, 1, 10), rec(1, 2, 0), rec(1, 3, 7)], previous_players=15)


@pytest.mark.parametrize("data, prev", [
    ([], 0),
    ([rec(1, 1, 0), rec(1, 2, 0)], 0),                                  # everything zero
    ([rec(1, 1, 5), rec(1, 2, 0), rec(1, 3, 0)], 0),                    # mostly zeros
    ([rec(1, 1, 4), rec(1, 2, 4)], 100),                                # collapsed vs stored
])
def test_validate_rejects_broken_data(data, prev):
    with pytest.raises(ScrapeError):
        totals.validate_totals(data, prev)


# ---- get_total_players

def test_total_players_single_page():
    s = FakeSession(lambda p: board([["1", "a", "x", "y", "z", "1"]] * 7))
    assert totals.get_total_players(s, "tok", 1, 1, "0,0") == 7


def test_total_players_paginated_uses_last_page():
    def handler(p):
        if p["row"] == "0":
            return board([["1"]] * 50, headers=("h",), links=(50, 100))
        assert p["row"] == "100"
        return board([["1"]] * 7, headers=("h",))
    assert totals.get_total_players(FakeSession(handler), "tok", 1, 1, "0,0") == 107


def test_total_players_no_table_is_zero():
    assert totals.get_total_players(FakeSession(lambda p: "<html></html>"), "tok", 1, 1, "0,0") == 0
