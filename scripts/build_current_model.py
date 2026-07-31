"""Build the normalized NISRA projection data and current model YAML.

Usage:
    python scripts/build_current_model.py /path/to/NPP24_ppp_coc.xlsx

The workbook is the official NISRA 2024-based principal projection summary.
Observed 2022-2024 components come from the normalized mid-year estimates
already checked into ``data/``.
"""

import argparse
import csv
import io
import zipfile
from pathlib import Path

import openpyxl
import yaml

ROOT = Path(__file__).resolve().parents[1]
OBSERVED_PATH = ROOT / "data" / "ni_population_components_2002_2024.csv"
PROJECTION_PATH = ROOT / "data" / "ni_population_projection_2024_2074.csv"
LGD_POPULATION_PATH = ROOT / "data" / "ni_census_2021_lgd_population.csv"
INTERNAL_MIGRATION_PATH = ROOT / "data" / "ni_internal_migration_lgd_2021.csv"
MODEL_PATH = ROOT / "models" / "ni_current.yaml"


def _integer(value):
    return int(round(float(value)))


def _year(value):
    return int(str(value)[:4])


def extract_projection(workbook_path):
    workbook = openpyxl.load_workbook(workbook_path, data_only=True, read_only=True)
    sheet = workbook["PERSONS"]
    year_cells = next(
        sheet.iter_rows(min_row=7, max_row=7, min_col=2, max_col=52, values_only=True)
    )
    years = [_year(value) for value in year_cells]
    rows = {
        row[0]: row[1:]
        for row in sheet.iter_rows(
            min_row=8, max_row=20, min_col=1, max_col=52, values_only=True
        )
    }

    projection = []
    for index, year in enumerate(years):
        if year == 2024:
            continue
        row = {
            "year": year,
            "population_start": _integer(rows["Population at start"][index]),
            "births": _integer(rows["Births"][index]),
            "deaths": _integer(rows["Deaths"][index]),
            "immigration": _integer(rows["International migration inflows"][index])
            + _integer(rows["Cross border migration inflows [note 3]"][index]),
            "emigration": _integer(rows["International migration outflows"][index])
            + _integer(rows["Cross border migration outflows [note 3]"][index]),
            "net_migration": _integer(rows["Net migration"][index]),
            "population_end": _integer(rows["Population at end"][index]),
        }
        row["reconciliation_adjustment"] = row["population_end"] - (
            row["population_start"]
            + row["births"]
            - row["deaths"]
            + row["net_migration"]
        )
        projection.append(row)
    return projection


def read_observed():
    with OBSERVED_PATH.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    return [
        {
            "year": int(row["period"][-4:]),
            "population_start": int(row["population_start"]),
            "births": int(row["births"]),
            "deaths": int(row["deaths"]),
            "immigration": "",
            "emigration": "",
            "net_migration": int(row["net_migration"]),
            "reconciliation_adjustment": int(row["other_changes"]),
            "population_end": int(row["population_end"]),
        }
        for row in rows
        if int(row["period"][-4:]) >= 2022
    ]


def write_projection(rows):
    fields = [
        "year",
        "population_start",
        "births",
        "deaths",
        "immigration",
        "emigration",
        "net_migration",
        "reconciliation_adjustment",
        "population_end",
    ]
    with PROJECTION_PATH.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def extract_internal_migration(archive_path):
    with LGD_POPULATION_PATH.open(encoding="utf-8", newline="") as source:
        populations = {row["code"]: row for row in csv.DictReader(source)}
    with zipfile.ZipFile(archive_path) as archive:
        binary_source = archive.open("ODMG01NI-UK-LGD.csv")
        source = io.TextIOWrapper(binary_source, encoding="utf-8-sig")
        rows = csv.DictReader(source)
        flows = [
            {
                "source_code": row["Migrant one year ago area code"],
                "source": populations[row["Migrant one year ago area code"]][
                    "location"
                ],
                "destination_code": row["Area of residence code"],
                "destination": populations[row["Area of residence code"]]["location"],
                "count": int(row["Count"]),
                "source_population": int(
                    populations[row["Migrant one year ago area code"]]["count"]
                ),
            }
            for row in rows
            if row["Migrant one year ago area code"] in populations
            and row["Area of residence code"] in populations
            and row["Migrant one year ago area code"] != row["Area of residence code"]
        ]
    return sorted(flows, key=lambda row: (row["source_code"], row["destination_code"]))


def write_internal_migration(rows):
    fields = [
        "source_code",
        "source",
        "destination_code",
        "destination",
        "count",
        "source_population",
        "rate_per_1000",
    ]
    with INTERNAL_MIGRATION_PATH.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {**row, "rate_per_1000": _rate(row["count"], row["source_population"])}
            )


def _rate(count, population):
    return round(count * 1000 / population, 6)


def build_model(rows, internal_flows):
    births = []
    deaths = []
    migration = []
    for row in rows:
        year = row["year"]
        population = row["population_start"]
        after_births = population + row["births"]
        before_migration = after_births - row["deaths"]
        source = "observed" if year <= 2024 else "principal_projection"
        births.append(
            {
                "rate": _rate(row["births"], population),
                "year_min": year,
                "year_max": year,
                "filters": {},
                "evidence": source,
            }
        )
        deaths.append(
            {
                # Deaths run after births in the simulation engine.
                "rate": _rate(row["deaths"], after_births),
                "year_min": year,
                "year_max": year,
                "filters": {},
                "evidence": source,
            }
        )
        if row["immigration"] == "":
            migration.append(
                {
                    "rate": _rate(row["net_migration"], before_migration),
                    "year_min": year,
                    "year_max": year,
                    "filters": {},
                    "evidence": "observed_net_only",
                }
            )
        else:
            migration.extend(
                [
                    {
                        "rate": _rate(row["immigration"], before_migration),
                        "year_min": year,
                        "year_max": year,
                        "filters": {},
                        "evidence": source,
                        "flow": "in",
                    },
                    {
                        # Outflows run after inflows, so use the then-current
                        # population as the denominator.
                        "rate": -_rate(
                            row["emigration"], before_migration + row["immigration"]
                        ),
                        "year_min": year,
                        "year_max": year,
                        "filters": {},
                        "evidence": source,
                        "flow": "out",
                    },
                ]
            )

    return {
        "name": "NI Current – NISRA 2024 principal projection",
        "description": (
            "Observed NISRA components for 2022–2024 followed by the official "
            "2024-based principal projection for 2025–2074. The population "
            "baseline uses Census 2021 marginals; internal relocation follows "
            "the Census 2021 LGD origin–destination pattern. This is a projection "
            "scenario, not a forecast."
        ),
        "baseline_year": 2021,
        "data_through": 2024,
        "projection_version": "NISRA/ONS 2024-based principal projection",
        "default_start_year": 2024,
        "default_end_year": 2035,
        "rate_jitter": 0,
        "random_seed": 42,
        "birth_rates": births,
        "death_rates": deaths,
        "migration_rates": migration,
        "internal_migration_rates": [
            {
                "rate": _rate(flow["count"], flow["source_population"]),
                "year_min": 2022,
                "destination": flow["destination"].upper(),
                "filters": {"location": flow["source"].upper()},
                "evidence": "census_2021_origin_destination",
            }
            for flow in internal_flows
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("origin_destination_zip", type=Path)
    args = parser.parse_args()
    rows = read_observed() + extract_projection(args.workbook)
    internal_flows = extract_internal_migration(args.origin_destination_zip)
    write_projection(rows)
    write_internal_migration(internal_flows)
    with MODEL_PATH.open("w", encoding="utf-8") as target:
        yaml.safe_dump(
            build_model(rows, internal_flows),
            target,
            sort_keys=False,
            allow_unicode=True,
            width=88,
        )


if __name__ == "__main__":
    main()
