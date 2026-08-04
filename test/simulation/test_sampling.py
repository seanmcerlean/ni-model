"""Tests for shared stochastic sampling helpers."""

from src.ni_model.simulation.sampling import stochastic_round


def test_stochastic_round_preserves_fractional_expected_counts():
    assert stochastic_round(2.25, 0.24) == 3
    assert stochastic_round(2.25, 0.25) == 2


def test_stochastic_round_keeps_integral_counts_exact():
    assert stochastic_round(5.0, 0.0) == 5
    assert stochastic_round(5.0, 0.99) == 5
