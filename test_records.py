import pytest
import sqlite3

import records
import scraper
from db import connect
from scraper import ScrapeError
from helpers import FakeSession, board, ConnectionFailure


def row(rank, nick, lake=1, fish=1, kind="Hauki", name="Lake", date="2024-01-02", weight=900):
    return (rank, nick, kind, name, date, weight, lake, fish)


def db_with_totals(players=10):
    con = connect(":memory:")
    con.executemany("INSERT INTO totalrecords (Season, Lake_ID, Fish_ID, Players, Rarity) VALUES (?,?,?,?,?)",
                    [("0_0", 1, 1, players, 1.0), ("0_0", 1, 3, players, 1.0), ("0_0", 2, 1, players, 1.0)])
    return con


def stored(con):
    return con.execute("SELECT Nick, Lake_ID, Fish_ID, Rank FROM records ORDER BY Nick, Lake_ID, Fish_ID").fetchall()


# ---- schema

def test_schema_is_idempotent_and_versioned():
    con = connect(":memory:")
    from db import init_schema, SCHEMA_VERSION
    init_schema(con)
    assert con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_unique_key_rejects_duplicates():
    con = db_with_totals()
    ins = "INSERT INTO records (Season, Rank, Nick, Lake_ID, Fish_ID) VALUES ('0_0', 1, 'a', 1, 1)"
    con.execute(ins)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(ins)


def test_old_db_without_unique_key_is_upgraded(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE records (Season TEXT, Rank INTEGER, Nick TEXT, Type TEXT, Lake TEXT, Date TEXT, "
                "Weight INTEGER, Lake_ID INTEGER, Fish_ID INTEGER, Percentile REAL, Score REAL, Out_Of INTEGER, Rarity REAL)")
    old.execute("CREATE INDEX idx_rec ON records(Season, Nick)")
    old.execute("INSERT INTO records (Season, Rank, Nick, Lake_ID, Fish_ID) VALUES ('0_0', 1, 'a', 1, 1)")
    old.commit(); old.close()
    con = connect(path)
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "uq_records" in names and "idx_rec" not in names
    assert con.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 1


# ---- save

def test_save_writes_scores():
    con = db_with_totals(10)
    assert records.save("0_0", [row(2, "Pumpkin")], ["Pumpkin"], con) == 1
    assert con.execute("SELECT Out_Of, Score FROM records").fetchone()[0] == 10
    assert con.execute("SELECT Score FROM records").fetchone()[0] > 0


def test_save_replaces_case_insensitively():
    con = db_with_totals()
    records.save("0_0", [row(3, "pumpkin")], ["pumpkin"], con)
    records.save("0_0", [row(1, "Pumpkin")], ["pumpkin"], con)
    assert stored(con) == [("Pumpkin", 1, 1, 1)]


def test_save_leaves_other_players_and_seasons_alone():
    con = db_with_totals()
    con.execute("INSERT INTO totalrecords (Season, Lake_ID, Fish_ID, Players, Rarity) VALUES ('1_18', 1, 1, 5, 1.0)")
    records.save("0_0", [row(1, "Exksa")], ["Exksa"], con)
    records.save("1_18", [row(1, "Exksa")], ["Exksa"], con)
    records.save("0_0", [row(2, "Pumpkin")], ["Pumpkin"], con)
    assert con.execute("SELECT COUNT(*) FROM records WHERE Season='1_18'").fetchone()[0] == 1
    assert {r[0] for r in stored(con)} == {"Exksa", "Pumpkin"}


def test_duplicate_rows_keep_better_rank(capsys):
    con = db_with_totals()
    records.save("0_0", [row(4, "a"), row(2, "a")], ["a"], con)
    assert stored(con) == [("a", 1, 1, 2)]
    assert "Duplicate" in capsys.readouterr().out


def test_collapse_guard_aborts_and_keeps_old_rows():
    con = db_with_totals()
    old = [row(i, "Exksa", fish=f) for i, f in enumerate([1, 3], start=1)] + [row(1, "Exksa", lake=2)]
    records.save("0_0", old, ["Exksa"], con)
    before = stored(con)
    with pytest.raises(ScrapeError):
        records.save("0_0", [row(1, "Pumpkin")], ["Exksa", "Pumpkin"], con)   # Exksa vanished
    assert stored(con) == before


def test_new_player_with_nothing_stored_is_fine():
    con = db_with_totals()
    assert records.save("0_0", [], ["Newbie"], con) == 0


def test_failed_refresh_rolls_back():
    con = connect(":memory:")   # no totals -> refresh_scores raises inside the transaction
    with pytest.raises(ScrapeError):
        records.save("0_0", [row(1, "a")], ["a"], con)
    assert con.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 0


def test_date_warnings(capsys):
    con = db_with_totals()
    con.execute("INSERT INTO totalrecords (Season, Lake_ID, Fish_ID, Players, Rarity) VALUES ('1_18', 1, 1, 5, 1.0)")
    records.save("1_18", [row(1, "a", date="2020-01-01"), row(1, "b", date="not a date")], ["a", "b"], con)
    out = capsys.readouterr().out
    assert "outside season 1_18" in out and "unparseable" in out


# ---- scraping

def test_scrape_leaderboard_returns_highlighted_rows_only():
    html = board([["1", "other", "Hauki", "Lake", "01.02.2024", "5 g"],
                  ["*2", "Me", "Hauki", "Lake", "01.02.2024", "850 g"]])
    out = records.scrape_leaderboard(FakeSession(lambda p: html), "tok", "Me", 1, 1)
    assert [r["Pelaaja"] for r in out] == ["Me"]


def test_scrape_leaderboard_rejects_changed_layout():
    html = board([["*2", "Me", "Hauki"]], headers=("Sija", "Pelaaja", "Kalalaji"))
    with pytest.raises(ScrapeError):
        records.scrape_leaderboard(FakeSession(lambda p: html), "tok", "Me", 1, 1)


def test_to_row_rejects_incomplete_rows():
    with pytest.raises(ScrapeError):
        records.to_row({"Sija": "1", "Pelaaja": "", "Kalalaji": "Hauki", "Järvi": "L"}, 1, 1)
    with pytest.raises(ScrapeError):
        records.to_row({"Sija": "1", "Pelaaja": "a", "Järvi": "L"}, 1, 1)   # no fish type


def test_to_row_parses_fields():
    r = records.to_row({"Sija": "3.", "Pelaaja": "a", "Kalalaji": "Hauki", "Järvi": "L",
                        "Päiväys": "05.03.2024", "Kalan paino": "1 200 g"}, 4, 1)
    assert r == (3, "a", "Hauki", "L", "2024-03-05", 1200, 4, 1)


# ---- token

def test_token_from_site():
    html = '<iframe id="iframe1" src="x.php?t=555&y=1"></iframe>'
    assert scraper.get_token(FakeSession(lambda p: html)) == "555"


def test_token_fallback_warns(monkeypatch, capsys):
    monkeypatch.setattr(scraper.time, "sleep", lambda s: None)
    s = FakeSession(lambda p: ConnectionFailure("down"))
    assert scraper.get_token(s) == scraper.FALLBACK_TOKEN
    assert "fallback token" in capsys.readouterr().out
