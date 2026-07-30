import csv
from pathlib import Path

DATA_PATH = Path("data/ni_population_components_2002_2024.csv")


def _rows():
    with DATA_PATH.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def test_population_components_cover_published_period():
    rows = _rows()

    assert len(rows) == 23
    assert rows[0]["period"] == "mid-2001 to mid-2002"
    assert rows[-1]["period"] == "mid-2023 to mid-2024"


def test_population_component_reconciliation():
    for row in _rows():
        births = int(row["births"])
        deaths = int(row["deaths"])
        natural_change = int(row["natural_change"])
        migration = int(row["net_migration"])
        other_changes = int(row["other_changes"])
        start = int(row["population_start"])
        end = int(row["population_end"])

        assert natural_change == births - deaths
        assert end == start + natural_change + migration + other_changes
        assert int(row["population_change"]) == end - start


def test_latest_official_components():
    latest = _rows()[-1]

    assert int(latest["births"]) == 19_785
    assert int(latest["deaths"]) == 17_855
    assert int(latest["net_migration"]) == 5_769
