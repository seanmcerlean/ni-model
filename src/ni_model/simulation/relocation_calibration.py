"""Balance observed LGD relocation flows toward official population trajectories."""

from collections import defaultdict


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
    if not earlier:
        return None, False
    return by_year[max(earlier)], True


def relocation_pair_scales(current_counts, raw_flows, targets, calibration, year):
    """Return OD-pair factors that retain gross movement and approach LGD shares.

    Iterative proportional fitting preserves the observed OD structure. Only row
    and column totals are adjusted, so community-relative rates within each OD
    pair remain unchanged.
    """
    target, after_horizon = _target_for_year(targets, year)
    if not target or not raw_flows:
        return {pair: 1.0 for pair in raw_flows}
    if set(target) - set(current_counts) or any(
        current_counts.get(location, 0) <= 0 for location in target
    ):
        # Tiny fixtures and deliberately partial populations cannot be raked to
        # an all-LGD target without inventing unsupported routes or residents.
        return {pair: 1.0 for pair in raw_flows}

    strength = float(calibration.get("strength", 0.65))
    if after_horizon:
        last_year = max(item["year"] for item in targets)
        fade_years = max(int(calibration.get("fade_years", 15)), 1)
        post_strength = float(calibration.get("post_projection_strength", 0.15))
        progress = min(max(year - last_year, 0) / fade_years, 1.0)
        strength += (post_strength - strength) * progress
    if strength <= 0:
        return {pair: 1.0 for pair in raw_flows}

    locations = sorted(current_counts)
    total = sum(current_counts.values())
    target_total = sum(target.get(location, 0) for location in locations)
    if not total or not target_total:
        return {pair: 1.0 for pair in raw_flows}

    raw_out = defaultdict(float)
    raw_in = defaultdict(float)
    for (source, destination), flow in raw_flows.items():
        raw_out[source] += flow
        raw_in[destination] += flow

    target_net = {}
    for location in locations:
        desired = total * target.get(location, 0) / target_total
        raw_net = raw_in[location] - raw_out[location]
        official_net = desired - current_counts[location]
        target_net[location] = raw_net + strength * (official_net - raw_net)

    # Retain each area's observed movement activity while altering its net balance.
    target_out = {}
    target_in = {}
    for location in locations:
        activity = (raw_out[location] + raw_in[location]) / 2
        activity = max(activity, abs(target_net[location]) / 2 + 1e-9)
        target_out[location] = activity - target_net[location] / 2
        target_in[location] = activity + target_net[location] / 2

    out_total = sum(target_out.values())
    in_total = sum(target_in.values())
    if in_total:
        target_in = {
            location: value * out_total / in_total
            for location, value in target_in.items()
        }

    matrix = {pair: max(float(flow), 1e-12) for pair, flow in raw_flows.items()}
    for _ in range(100):
        rows = defaultdict(float)
        for (source, _), value in matrix.items():
            rows[source] += value
        for pair in matrix:
            source = pair[0]
            if rows[source]:
                matrix[pair] *= target_out[source] / rows[source]

        columns = defaultdict(float)
        for (_, destination), value in matrix.items():
            columns[destination] += value
        for pair in matrix:
            destination = pair[1]
            if columns[destination]:
                matrix[pair] *= target_in[destination] / columns[destination]

    return {
        pair: matrix[pair] / raw_flow if raw_flow > 0 else 1.0
        for pair, raw_flow in raw_flows.items()
    }
