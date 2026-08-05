"""Balance observed LGD relocation flows toward official population trajectories."""

from collections import defaultdict

Pair = tuple[str, str]
Flows = dict[Pair, float]
Counts = dict[str, float]


def _unity_scales(flows: Flows) -> Flows:
    return dict.fromkeys(flows, 1.0)


def _target_for_year(targets, year):
    by_year = {
        target["year"]: {
            str(location).lower(): population
            for location, population in target["populations"].items()
        }
        for target in targets
    }
    if year in by_year:
        return by_year[year], False
    earlier = [target_year for target_year in by_year if target_year < year]
    return (by_year[max(earlier)], True) if earlier else (None, False)


def _calibration_strength(calibration, targets, year, after_horizon):
    strength = float(calibration.get("strength", 0.65))
    if not after_horizon:
        return strength

    last_year = max(item["year"] for item in targets)
    fade_years = max(int(calibration.get("fade_years", 15)), 1)
    post_strength = float(calibration.get("post_projection_strength", 0.15))
    progress = min(max(year - last_year, 0) / fade_years, 1.0)
    return strength + (post_strength - strength) * progress


def _location_flows(raw_flows: Flows) -> tuple[Counts, Counts]:
    outgoing = defaultdict(float)
    incoming = defaultdict(float)
    for (source, destination), flow in raw_flows.items():
        outgoing[source] += flow
        incoming[destination] += flow
    return outgoing, incoming


def _target_net_flows(
    current: Counts,
    target: Counts,
    outgoing: Counts,
    incoming: Counts,
    strength: float,
) -> Counts:
    total = sum(current.values())
    target_total = sum(target[location] for location in current)
    return {
        location: (incoming[location] - outgoing[location])
        + strength
        * (
            total * target[location] / target_total
            - current[location]
            - (incoming[location] - outgoing[location])
        )
        for location in current
    }


def _target_margins(
    locations, outgoing: Counts, incoming: Counts, target_net: Counts
) -> tuple[Counts, Counts]:
    target_out = {}
    target_in = {}
    for location in locations:
        activity = (outgoing[location] + incoming[location]) / 2
        activity = max(activity, abs(target_net[location]) / 2 + 1e-9)
        target_out[location] = activity - target_net[location] / 2
        target_in[location] = activity + target_net[location] / 2

    scale = sum(target_out.values()) / sum(target_in.values())
    return target_out, {
        location: value * scale for location, value in target_in.items()
    }


def _margins(matrix: Flows, index: int) -> Counts:
    totals = defaultdict(float)
    for pair, value in matrix.items():
        totals[pair[index]] += value
    return totals


def _scale_margin(matrix: Flows, targets: Counts, index: int) -> None:
    current = _margins(matrix, index)
    for pair in matrix:
        location = pair[index]
        if current[location]:
            matrix[pair] *= targets[location] / current[location]


def _balance_matrix(raw_flows: Flows, target_out: Counts, target_in: Counts) -> Flows:
    matrix = {pair: max(float(flow), 1e-12) for pair, flow in raw_flows.items()}
    for _ in range(100):
        _scale_margin(matrix, target_out, 0)
        _scale_margin(matrix, target_in, 1)
    return matrix


def relocation_pair_scales(current_counts, raw_flows, targets, calibration, year):
    """Return OD-pair factors that retain gross movement and approach LGD shares.

    Iterative proportional fitting preserves the observed OD structure. Only row
    and column totals are adjusted, so community-relative rates within each OD
    pair remain unchanged.
    """
    target, after_horizon = _target_for_year(targets, year)
    if not target or not raw_flows:
        return _unity_scales(raw_flows)
    if set(target) - set(current_counts) or any(
        current_counts.get(location, 0) <= 0 for location in target
    ):
        return _unity_scales(raw_flows)

    strength = _calibration_strength(calibration, targets, year, after_horizon)
    if strength <= 0:
        return _unity_scales(raw_flows)

    outgoing, incoming = _location_flows(raw_flows)
    target_net = _target_net_flows(current_counts, target, outgoing, incoming, strength)
    target_out, target_in = _target_margins(
        sorted(current_counts), outgoing, incoming, target_net
    )
    balanced = _balance_matrix(raw_flows, target_out, target_in)
    return {
        pair: balanced[pair] / flow if flow > 0 else 1.0
        for pair, flow in raw_flows.items()
    }
