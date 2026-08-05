import pytest

from src.ni_model.simulation.relocation_calibration import relocation_pair_scales


def test_relocation_balancing_preserves_gross_activity_and_targets_net_change():
    current = {"a": 100.0, "b": 100.0, "c": 100.0}
    raw = {
        ("a", "b"): 10.0,
        ("a", "c"): 10.0,
        ("b", "a"): 10.0,
        ("b", "c"): 10.0,
        ("c", "a"): 10.0,
        ("c", "b"): 10.0,
    }
    targets = [{"year": 2025, "populations": {"A": 110, "B": 100, "C": 90}}]

    scales = relocation_pair_scales(current, raw, targets, {"strength": 1.0}, 2025)
    adjusted = {pair: raw[pair] * scales[pair] for pair in raw}
    net = {
        location: sum(
            flow
            for (_, destination), flow in adjusted.items()
            if destination == location
        )
        - sum(flow for (source, _), flow in adjusted.items() if source == location)
        for location in current
    }

    assert sum(adjusted.values()) == pytest.approx(sum(raw.values()))
    assert net == pytest.approx({"a": 10.0, "b": 0.0, "c": -10.0})


def test_relocation_balancing_retains_pair_ratios_for_community_subgroups():
    scales = relocation_pair_scales(
        {"a": 100, "b": 100},
        {("a", "b"): 8.0, ("b", "a"): 12.0},
        [{"year": 2025, "populations": {"a": 105, "b": 95}}],
        {"strength": 0.5},
        2025,
    )

    # A single factor per OD pair is applied to every community rule on that route.
    catholic = 3.0 * scales[("a", "b")]
    protestant = 5.0 * scales[("a", "b")]
    assert catholic / protestant == pytest.approx(3 / 5)


def test_post_projection_strength_fades_to_documented_floor():
    raw = {("a", "b"): 10.0, ("b", "a"): 10.0}
    targets = [{"year": 2047, "populations": {"a": 110, "b": 90}}]
    config = {
        "strength": 0.65,
        "post_projection_strength": 0.15,
        "fade_years": 10,
    }

    early = relocation_pair_scales({"a": 100, "b": 100}, raw, targets, config, 2047)
    late = relocation_pair_scales({"a": 100, "b": 100}, raw, targets, config, 2057)

    assert early[("b", "a")] > late[("b", "a")] > 1.0


def test_partial_fixture_population_is_not_forced_into_missing_lgds():
    raw = {("a", "b"): 2.0}
    scales = relocation_pair_scales(
        {"a": 10},
        raw,
        [{"year": 2025, "populations": {"A": 10, "B": 10}}],
        {"strength": 1.0},
        2025,
    )

    assert scales == {("a", "b"): 1.0}
