"""Small sampling helpers shared by simulation engines."""

import math


def stochastic_round(expected: float, random_value: float) -> int:
    """Round an expected event count without systematically losing fractions."""
    whole = math.floor(expected)
    return whole + int(random_value < expected - whole)
