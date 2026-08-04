import csv
import random
from collections.abc import Iterator
from pathlib import Path
from typing import List, Optional

from ..core.models import (
    EducationLevel,
    Gender,
    Location,
    Origin,
    Person,
    ReligiousBackground,
)

# NI Census 2021 "religion or religion brought up in" (community-background
# proxy), table MS-B23. Topic tables are independently disclosure-controlled,
# so this table totals 1,903,172 rather than the headline population 1,903,175.
_RELIGION_WEIGHTS = [
    (ReligiousBackground.CATHOLIC, 869_753 / 1_903_172),
    (ReligiousBackground.PROTESTANT, 827_545 / 1_903_172),
    (ReligiousBackground.OTHER, 28_514 / 1_903_172),
    (ReligiousBackground.NONE, 177_360 / 1_903_172),
]

# Census 2021 usual residents: 935,973 male and 967,202 female. The database
# retains OTHER for scenarios, but Census 2021 published this table by sex.
_GENDER_WEIGHTS = [
    (Gender.MALE, 935_973 / 1_903_175),
    (Gender.FEMALE, 967_202 / 1_903_175),
]

_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def _load_location_weights():
    """Load exact Census 2021 LGD marginals from the checked-in source table."""
    path = _DATA_DIR / "ni_census_2021_lgd_population.csv"
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    total = sum(int(row["count"]) for row in rows)
    return [(Location(row["location"]), int(row["count"]) / total) for row in rows]


_LOCATION_WEIGHTS = _load_location_weights()


def _load_location_background_weights():
    """Load Census 2021 community-background weights conditional on LGD."""
    path = _DATA_DIR / "ni_census_2021_lgd_community_background.csv"
    weights = {}
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            counts = [
                (ReligiousBackground.CATHOLIC, int(row["catholic"])),
                (ReligiousBackground.PROTESTANT, int(row["protestant"])),
                (ReligiousBackground.OTHER, int(row["other"])),
                (ReligiousBackground.NONE, int(row["none"])),
            ]
            total = sum(count for _, count in counts)
            weights[Location(row["location"])] = [
                (background, count / total) for background, count in counts
            ]
    return weights


_BACKGROUND_WEIGHTS_BY_LOCATION = _load_location_background_weights()


def _regional_background_weights(target_weights=None):
    """Return LGD conditionals, optionally calibrated to NI-wide targets.

    Iterative proportional fitting preserves the Census 2021 LGD pattern while
    matching a supplied historical NI-wide community-background distribution.
    """
    if target_weights is None:
        return _BACKGROUND_WEIGHTS_BY_LOCATION

    backgrounds = list(ReligiousBackground)
    targets = dict(target_weights)
    matrix = {
        location: {
            background: location_share
            * dict(_BACKGROUND_WEIGHTS_BY_LOCATION[location])[background]
            for background in backgrounds
        }
        for location, location_share in _LOCATION_WEIGHTS
    }
    location_targets = dict(_LOCATION_WEIGHTS)

    for _ in range(50):
        for background in backgrounds:
            current = sum(row[background] for row in matrix.values())
            factor = targets[background] / current
            for row in matrix.values():
                row[background] *= factor
        for location, row in matrix.items():
            factor = location_targets[location] / sum(row.values())
            for background in backgrounds:
                row[background] *= factor

    return {
        location: [
            (background, row[background] / location_targets[location])
            for background in backgrounds
        ]
        for location, row in matrix.items()
    }


# Census 2021 country of birth, MS-A16. `GB` combines England, Scotland and
# Wales; `OTHER` combines all remaining published categories.
_ORIGIN_WEIGHTS = [
    (Origin.NI, 1_646_276 / 1_903_173),
    (Origin.ROI, 40_357 / 1_903_173),
    (Origin.GB, 92_257 / 1_903_173),
    (Origin.OTHER, 124_283 / 1_903_173),
]

# Census 2021 five-year age bands, MS-A02. MS-A02 combines everybody aged 90+;
# that band is split using an explicit approximate centenarian share (0.015%)
# consistent with NISRA's published 2024 count of 294.
_AGE_TOTAL = 1_903_174
_CENTENARIAN_WEIGHT = 0.00015
_AGE_BANDS = [
    (0, 4, 113_820 / _AGE_TOTAL),
    (5, 9, 124_475 / _AGE_TOTAL),
    (10, 14, 126_918 / _AGE_TOTAL),
    (15, 19, 113_203 / _AGE_TOTAL),
    (20, 24, 111_386 / _AGE_TOTAL),
    (25, 29, 116_409 / _AGE_TOTAL),
    (30, 34, 126_050 / _AGE_TOTAL),
    (35, 39, 127_313 / _AGE_TOTAL),
    (40, 44, 122_163 / _AGE_TOTAL),
    (45, 49, 121_670 / _AGE_TOTAL),
    (50, 54, 130_967 / _AGE_TOTAL),
    (55, 59, 129_276 / _AGE_TOTAL),
    (60, 64, 113_049 / _AGE_TOTAL),
    (65, 69, 93_464 / _AGE_TOTAL),
    (70, 74, 83_467 / _AGE_TOTAL),
    (75, 79, 66_377 / _AGE_TOTAL),
    (80, 84, 43_776 / _AGE_TOTAL),
    (85, 89, 25_879 / _AGE_TOTAL),
    (90, 99, (13_512 / _AGE_TOTAL) - _CENTENARIAN_WEIGHT),
    (100, 110, _CENTENARIAN_WEIGHT),
]


def calibrated_age_bands(targets):
    """Scale the detailed Census shape to supplied broad-age marginals."""
    calibrated = []
    for target_min, target_max, target_weight in targets:
        members = [band for band in _AGE_BANDS if target_min <= band[0] <= target_max]
        current_weight = sum(weight for _, _, weight in members)
        calibrated.extend(
            (minimum, maximum, weight * target_weight / current_weight)
            for minimum, maximum, weight in members
        )
    return calibrated


# Census 2021 MS-B31. Detailed five-year age shapes come from MS-A02 and are
# calibrated to the published age-by-community broad bands. This retains both
# the national age pyramid and the materially older Protestant-background
# population instead of sampling age and community independently.
_BACKGROUND_AGE_COUNTS = {
    ReligiousBackground.CATHOLIC: (869_749, (177_818, 286_070, 282_161, 123_700)),
    ReligiousBackground.PROTESTANT: (
        827_541,
        (118_693, 223_474, 292_060, 193_314),
    ),
    ReligiousBackground.OTHER: (28_516, (6_054, 11_889, 8_226, 2_347)),
    ReligiousBackground.NONE: (177_361, (62_647, 72_930, 34_677, 7_107)),
}
_BACKGROUND_AGE_BANDS = {
    background: calibrated_age_bands(
        [
            (0, 14, counts[0] / total),
            (15, 39, counts[1] / total),
            (40, 64, counts[2] / total),
            (65, 110, counts[3] / total),
        ]
    )
    for background, (total, counts) in _BACKGROUND_AGE_COUNTS.items()
}


# Education weights are scenario assumptions selected by broad age, not
# observed joint Census distributions.
_PRE = EducationLevel.PRE_PRIMARY
_PRI = EducationLevel.PRIMARY
_SEC = EducationLevel.SECONDARY
_TER = EducationLevel.TERTIARY
_PGR = EducationLevel.POSTGRADUATE

_EDUCATION_BY_BROAD_AGE: List[tuple[int, int, List[tuple]]] = [
    (0, 4, [(_PRE, 1.0)]),
    (5, 14, [(_PRE, 0.5), (_PRI, 0.5)]),
    (15, 24, [(_PRI, 0.1), (_SEC, 0.9)]),
    (25, 34, [(_SEC, 0.5), (_TER, 0.5)]),
    (35, 44, [(_SEC, 0.4), (_TER, 0.45), (_PGR, 0.15)]),
    (45, 54, [(_SEC, 0.45), (_TER, 0.40), (_PGR, 0.15)]),
    (55, 64, [(_PRI, 0.1), (_SEC, 0.55), (_TER, 0.30), (_PGR, 0.05)]),
    (65, 74, [(_PRI, 0.2), (_SEC, 0.55), (_TER, 0.25)]),
    (75, 84, [(_PRI, 0.3), (_SEC, 0.55), (_TER, 0.15)]),
    (85, 99, [(_PRI, 0.4), (_SEC, 0.50), (_TER, 0.10)]),
    (100, 110, [(_PRI, 0.5), (_SEC, 0.40), (_TER, 0.10)]),
]


def _weighted_choice(choices, rng: random.Random):
    items, weights = zip(*choices)
    return rng.choices(items, weights=weights, k=1)[0]


def _sample_age(rng: random.Random, age_bands=_AGE_BANDS) -> int:
    """Return an age sampled from a configured NI age distribution."""
    band_items = [(i, w) for i, (_, _, w) in enumerate(age_bands)]
    band_idx = _weighted_choice([(i, w) for i, w in band_items], rng)
    min_age, max_age, _ = age_bands[band_idx]
    return rng.randint(min_age, max_age)


def _education_weights(age: int) -> List[tuple]:
    return next(
        weights
        for min_age, max_age, weights in _EDUCATION_BY_BROAD_AGE
        if min_age <= age <= max_age
    )


def iter_population(
    size: int,
    seed: Optional[int] = None,
    religion_weights=None,
    reference_year: int = 2021,
    age_bands=None,
    origin_weights=None,
) -> Iterator[Person]:
    """Yield residents without retaining a full-scale population in memory."""
    if size < 0:
        raise ValueError("size must be non-negative")

    rng = random.Random(seed)
    # Keep the established demographic stream unchanged; adding this inferred
    # field must not silently alter ages, locations, origins, or backgrounds.
    probable_rng = random.Random(None if seed is None else seed ^ 0x50B4B1E)
    from .probable_community import infer_probable_community

    use_background_age_bands = religion_weights is None and age_bands is None
    age_bands = _AGE_BANDS if age_bands is None else age_bands
    origin_weights = _ORIGIN_WEIGHTS if origin_weights is None else origin_weights
    regional_background_weights = _regional_background_weights(religion_weights)
    for _ in range(size):
        location = _weighted_choice(_LOCATION_WEIGHTS, rng)
        background_weights = regional_background_weights[location]
        background = _weighted_choice(background_weights, rng)
        selected_age_bands = (
            _BACKGROUND_AGE_BANDS[background] if use_background_age_bands else age_bands
        )
        age = _sample_age(rng, selected_age_bands)
        yield Person(
            age=age,
            birth_year=reference_year - age,
            religious_background=background,
            probable_community=infer_probable_community(
                background, location, probable_rng
            ),
            gender=_weighted_choice(_GENDER_WEIGHTS, rng),
            location=location,
            origin=_weighted_choice(origin_weights, rng),
            education_level=_weighted_choice(_education_weights(age), rng),
        )


def generate_population(
    size: int, seed: int = None, reference_year: int = 2021
) -> List[Person]:
    """Generate a list of Person objects with realistic NI demographic distributions.

    Args:
        size: Number of persons to generate
        seed: Optional random seed for reproducibility

    Returns:
        List of unsaved Person instances
    """
    return list(iter_population(size, seed=seed, reference_year=reference_year))
