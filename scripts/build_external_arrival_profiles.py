"""Build Census-based external arrival profiles for the community model."""

import argparse
import csv
import io
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_RELIGION_MAP = {
    "Catholic": "catholic",
    "Protestant and Other Christian": "protestant",
    "Other Religions": "other",
    "No Religion": "none",
    "Religion Not Stated": "none",
}

OUTPUT_PATH = ROOT / "data" / "ni_external_arrivals_lgd_2021_by_religion.csv"
LGD_PATH = ROOT / "data" / "ni_census_2021_lgd_population.csv"


def _religion_rows(archive_path, member):
    with zipfile.ZipFile(archive_path) as archive:
        source = io.TextIOWrapper(archive.open(member), encoding="utf-8-sig")
        yield from csv.DictReader(source)


def extract_profiles(uk_archive, roi_archive):
    """Return GB, ROI and rest-of-world arrivals by destination and religion."""
    with LGD_PATH.open(encoding="utf-8", newline="") as source:
        locations = {row["code"]: row["location"] for row in csv.DictReader(source)}

    counts = defaultdict(int)
    outside_uk = defaultdict(int)
    for row in _religion_rows(uk_archive, "ODMG20NI-UK-LGD.csv"):
        destination = row["Area of residence code"]
        source = row["Migrant one year ago area code"]
        if destination not in locations or source in locations:
            continue
        background = MIGRATION_RELIGION_MAP[row["RELIGION_BELONG_TO_DVO_AGG5_label"]]
        count = int(row["Count"])
        if source == "999999999":
            outside_uk[destination, background] += count
        elif source.startswith(("E", "S", "W")):
            counts["gb", destination, background] += count

    roi_counts = defaultdict(int)
    for row in _religion_rows(roi_archive, "ODMG20NI-ROI-LGD.csv"):
        destination = row["Area of residence code"]
        if destination not in locations:
            continue
        background = MIGRATION_RELIGION_MAP[row["RELIGION_BELONG_TO_DVO_AGG5_label"]]
        roi_counts[destination, background] += int(row["Count"])

    for key, outside_count in outside_uk.items():
        destination, background = key
        roi_count = roi_counts[key]
        counts["roi", destination, background] += roi_count
        counts["other", destination, background] += outside_count - roi_count

    total = sum(counts.values())
    return [
        {
            "origin": origin,
            "destination_code": destination,
            "destination": locations[destination],
            "religious_background": background,
            "count": count,
            "share": round(count / total, 9),
        }
        for (origin, destination, background), count in sorted(counts.items())
        if count > 0
    ]


def write_profiles(rows, output_path=OUTPUT_PATH):
    fields = [
        "origin",
        "destination_code",
        "destination",
        "religious_background",
        "count",
        "share",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("uk_religion_zip", type=Path)
    parser.add_argument("roi_religion_zip", type=Path)
    args = parser.parse_args()
    write_profiles(extract_profiles(args.uk_religion_zip, args.roi_religion_zip))


if __name__ == "__main__":
    main()
