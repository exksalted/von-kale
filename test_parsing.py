import pytest

import records


@pytest.mark.parametrize("raw, expected", [("1.", 1), ("12", 12), (" 3 ", 3), ("", None), (None, None), ("-", None)])
def test_parse_rank(raw, expected):
    assert records.parse_rank(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("850 g", 850), ("1\u00a0234 g", 1234), ("12,5 g", 12.5), ("700", 700), ("", None), (None, None), ("n/a", None),
])
def test_parse_weight(raw, expected):
    assert records.parse_weight(raw) == expected


def test_iso_date():
    assert records.iso_date("05.03.2024") == "2024-03-05"
    assert records.iso_date("2024-03-05") == "2024-03-05"   # unknown formats pass through
    assert records.iso_date(None) is None


def test_season_window():
    assert records.season_window("1_18") == ("2026-07-01", "2027-06-30")
    assert records.season_window("0_0") is None
