import random
from typing import List

from ..core.models import (
    EducationLevel,
    Gender,
    Location,
    Origin,
    Person,
    ReligiousBackground,
)

# NI 2021 census approximate shares
_RELIGION_WEIGHTS = [
    (ReligiousBackground.CATHOLIC, 0.454),
    (ReligiousBackground.PROTESTANT, 0.398),
    (ReligiousBackground.OTHER, 0.082),
    (ReligiousBackground.NONE, 0.066),
]

_GENDER_WEIGHTS = [
    (Gender.MALE, 0.494),
    (Gender.FEMALE, 0.504),
    (Gender.OTHER, 0.002),
]

# Population-weighted location shares (Belfast areas split ~30% of total)
_LOCATION_WEIGHTS = [
    (Location.BELFAST_NORTH, 0.085),
    (Location.BELFAST_SOUTH, 0.080),
    (Location.BELFAST_EAST, 0.075),
    (Location.BELFAST_WEST, 0.070),
    (Location.ANTRIM, 0.130),
    (Location.DOWN, 0.125),
    (Location.DERRY, 0.115),
    (Location.ARMAGH, 0.095),
    (Location.TYRONE, 0.090),
    (Location.FERMANAGH, 0.055),
]

_ORIGIN_WEIGHTS = [
    (Origin.NI, 0.920),
    (Origin.ROI, 0.040),
    (Origin.GB, 0.030),
    (Origin.OTHER, 0.010),
]

# Age band (min, max, weight) — NI pyramid: broad base, tapering top
_AGE_BANDS = [
    (0, 4, 0.060),
    (5, 14, 0.115),
    (15, 24, 0.120),
    (25, 34, 0.135),
    (35, 44, 0.130),
    (45, 54, 0.130),
    (55, 64, 0.110),
    (65, 74, 0.090),
    (75, 84, 0.055),
    (85, 100, 0.025),
    (101, 110, 0.030),
]

# Education level by age band index (0-based, matching _AGE_BANDS)
_PRE = EducationLevel.PRE_PRIMARY
_PRI = EducationLevel.PRIMARY
_SEC = EducationLevel.SECONDARY
_TER = EducationLevel.TERTIARY
_PGR = EducationLevel.POSTGRADUATE

_EDUCATION_BY_AGE: List[List[tuple]] = [
    [(_PRE, 1.0)],                                              # 0-4
    [(_PRE, 0.5), (_PRI, 0.5)],                                 # 5-14
    [(_PRI, 0.1), (_SEC, 0.9)],                                 # 15-24
    [(_SEC, 0.5), (_TER, 0.5)],                                 # 25-34
    [(_SEC, 0.4), (_TER, 0.45), (_PGR, 0.15)],                  # 35-44
    [(_SEC, 0.45), (_TER, 0.40), (_PGR, 0.15)],                 # 45-54
    [(_PRI, 0.1), (_SEC, 0.55), (_TER, 0.30), (_PGR, 0.05)],   # 55-64
    [(_PRI, 0.2), (_SEC, 0.55), (_TER, 0.25)],                  # 65-74
    [(_PRI, 0.3), (_SEC, 0.55), (_TER, 0.15)],                  # 75-84
    [(_PRI, 0.4), (_SEC, 0.50), (_TER, 0.10)],                  # 85-100
    [(_PRI, 0.5), (_SEC, 0.40), (_TER, 0.10)],                  # 101+
]


def _weighted_choice(choices):
    items, weights = zip(*choices)
    return random.choices(items, weights=weights, k=1)[0]


def _sample_age() -> tuple[int, int]:
    """Return (age, band_index) sampled from NI age pyramid"""
    band_items = [(i, w) for i, (_, _, w) in enumerate(_AGE_BANDS)]
    band_idx = _weighted_choice([(i, w) for i, w in band_items])
    min_age, max_age, _ = _AGE_BANDS[band_idx]
    return random.randint(min_age, max_age), band_idx


def generate_population(size: int, seed: int = None) -> List[Person]:
    """Generate a list of Person objects with realistic NI demographic distributions.

    Args:
        size: Number of persons to generate
        seed: Optional random seed for reproducibility

    Returns:
        List of unsaved Person instances
    """
    if seed is not None:
        random.seed(seed)

    persons = []
    for _ in range(size):
        age, band_idx = _sample_age()
        persons.append(
            Person(
                age=age,
                religious_background=_weighted_choice(_RELIGION_WEIGHTS),
                gender=_weighted_choice(_GENDER_WEIGHTS),
                location=_weighted_choice(_LOCATION_WEIGHTS),
                origin=_weighted_choice(_ORIGIN_WEIGHTS),
                education_level=_weighted_choice(_EDUCATION_BY_AGE[band_idx]),
            )
        )
    return persons
