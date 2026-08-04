"""Evidence-calibrated border-poll scenario projections.

This is a polling scenario, not a prediction of constitutional identity from
religion. Published poll community cross-tabs are used as the closest
available proxy for the model's Census community-background field; age affects
turnout only.  Other unobserved factors and future opinion change remain outside
the model.
"""

import math
from typing import Any, Dict, Optional, Sequence
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.models import Person, ReligiousBackground

_NILT_SOURCE = {
    "id": "nilt_2024",
    "name": "Northern Ireland Life and Times Survey 2024",
    "publisher": "ARK",
    "fieldwork": "6 September to 19 November 2024",
    "sample_size": 1199,
    "url": "https://www.ark.ac.uk/nilt/2024/Political_Attitudes/REFUNIFY.html",
    "question": (
        "REFUNIFY: referendum tomorrow on unifying with the Republic of Ireland"
    ),
}

# Published percentages. Other religions are not separately tabulated by ARK,
# so the all-adult result is used transparently for that small Census group.
_NILT_RESPONSES = {
    ReligiousBackground.CATHOLIC: (0.68, 0.10, 0.17, 0.05),
    ReligiousBackground.PROTESTANT: (0.10, 0.74, 0.12, 0.04),
    ReligiousBackground.NONE: (0.35, 0.41, 0.16, 0.06),
    ReligiousBackground.OTHER: (0.36, 0.42, 0.16, 0.05),
}

# NILT would-not-vote percentage by age. The 1% overall ineligible response is
# excluded because the resident model cannot observe citizenship/registration.
_NILT_NON_VOTE_BY_AGE = (
    (18, 24, 0.10),
    (25, 34, 0.03),
    (35, 44, 0.04),
    (45, 54, 0.04),
    (55, 64, 0.05),
    (65, 200, 0.06),
)

_LUCIDTALK_SOURCE = {
    "id": "lucidtalk_winter_2025",
    "name": "LucidTalk / Belfast Telegraph NI Tracker Winter 2025",
    "publisher": "LucidTalk",
    "fieldwork": "14 to 17 February 2025",
    "sample_size": 1051,
    "base_responses": 3001,
    "margin_of_error": 0.023,
    "url": "https://www.lucidtalk.co.uk/news/lt-ni-tracker-poll-winter-2025/",
    "question": (
        "Border poll within the week: remain in the UK or join a united Ireland"
    ),
}

# Official Q4 weighted cross-breaks: unity, UK, unsure-but-would-vote,
# would-not-vote/spoil. Percentages are published rounded and normalised below.
_LUCIDTALK_RESPONSES = {
    ReligiousBackground.CATHOLIC: (0.86, 0.06, 0.06, 0.02),
    ReligiousBackground.PROTESTANT: (0.04, 0.88, 0.07, 0.01),
    ReligiousBackground.NONE: (0.40, 0.34, 0.26, 0.00),
    ReligiousBackground.OTHER: (0.53, 0.41, 0.06, 0.00),
}
_LUCIDTALK_NON_VOTE_BY_AGE = (
    (18, 34, 0.00),
    (35, 44, 0.01),
    (45, 54, 0.00),
    (55, 64, 0.00),
    (65, 200, 0.03),
)

CALIBRATIONS = {
    "lucidtalk_winter_2025": (
        _LUCIDTALK_SOURCE,
        _LUCIDTALK_RESPONSES,
        _LUCIDTALK_NON_VOTE_BY_AGE,
    ),
    "nilt_2024": (_NILT_SOURCE, _NILT_RESPONSES, _NILT_NON_VOTE_BY_AGE),
}


def _wilson_interval(
    share: float, sample_size: int, z: float = 1.96
) -> Dict[str, float]:
    """Return a rounded 95% Wilson interval for a survey proportion."""
    if sample_size <= 0:
        return {"low": 0.0, "estimate": round(share, 4), "high": 0.0}
    denominator = 1 + z * z / sample_size
    centre = (share + z * z / (2 * sample_size)) / denominator
    margin = (
        z
        * math.sqrt(share * (1 - share) / sample_size + z * z / (4 * sample_size**2))
        / denominator
    )
    return {
        "low": round(max(0.0, centre - margin), 4),
        "estimate": round(share, 4),
        "high": round(min(1.0, centre + margin), 4),
    }


class VotingPredictor:
    """Project stated border-poll responses for eligible-adult proxies."""

    def __init__(
        self,
        db_session: Session,
        run_id: Optional[UUID] = None,
        calibration: str = "lucidtalk_winter_2025",
        aggregate_rows: Optional[Sequence[Any]] = None,
        total_population: Optional[int] = None,
        custom_baseline: Optional[Sequence[float]] = None,
        custom_reference_rows: Optional[Sequence[Any]] = None,
    ):
        if calibration not in CALIBRATIONS:
            raise ValueError(f"unknown voting calibration: {calibration}")
        self.db = db_session
        self.run_id = run_id
        self.calibration = calibration
        self.aggregate_rows = aggregate_rows
        self.total_population = total_population
        self.custom_reference_rows = custom_reference_rows
        self.source, self.responses, self.non_vote_by_age = CALIBRATIONS[calibration]
        if custom_baseline is not None:
            self._apply_custom_baseline(custom_baseline)

    def _apply_custom_baseline(self, baseline: Sequence[float]) -> None:
        """Rake LucidTalk response odds to a user-supplied overall baseline."""
        if len(baseline) != 3 or any(value < 0 or value > 1 for value in baseline):
            raise ValueError("custom baseline must contain three shares from 0 to 1")
        if not math.isclose(sum(baseline), 1.0, abs_tol=1e-6):
            raise ValueError("custom baseline shares must sum to 1")
        rows = (
            self.custom_reference_rows
            if self.custom_reference_rows is not None
            else self._rows()
        )
        multipliers = [1.0, 1.0, 1.0]
        for _ in range(100):
            totals = [0.0, 0.0, 0.0]
            for row in rows:
                base = self.responses[row.religious_background][:3]
                adjusted = [base[index] * multipliers[index] for index in range(3)]
                denominator = sum(adjusted)
                turnout = self._turnout(row.age, row.religious_background)
                weight = row.count * turnout
                for index in range(3):
                    totals[index] += weight * adjusted[index] / denominator
            total = sum(totals)
            if total == 0:
                break
            shares = [value / total for value in totals]
            if max(abs(shares[index] - baseline[index]) for index in range(3)) < 1e-9:
                break
            for index in range(3):
                if shares[index] > 0:
                    multipliers[index] *= baseline[index] / shares[index]

        adjusted_responses = {}
        for background, response in self.responses.items():
            adjusted = [response[index] * multipliers[index] for index in range(3)]
            denominator = sum(adjusted)
            adjusted_responses[background] = (
                adjusted[0] / denominator,
                adjusted[1] / denominator,
                adjusted[2] / denominator,
                response[3],
            )
        self.responses = adjusted_responses
        self.calibration = "custom_lucidtalk"
        self.source = {
            **self.source,
            "id": "custom_lucidtalk",
            "name": "Custom baseline over LucidTalk Winter 2025",
            "custom_baseline": {
                "unite": baseline[0],
                "remain": baseline[1],
                "undecided": baseline[2],
            },
            "baseline_definition": "current_reference_population",
        }

    def _turnout(self, age: int, background: ReligiousBackground) -> float:
        age_non_vote = next(
            rate for low, high, rate in self.non_vote_by_age if low <= age <= high
        )
        background_non_vote = self.responses[background][3]
        # Average the two published marginal signals; joint microdata is not
        # inferred from separate cross-tabs.
        return 1.0 - ((age_non_vote + background_non_vote) / 2)

    def _rows(self, *filters):
        if self.aggregate_rows is not None:
            if not filters:
                return self.aggregate_rows
            location = filters[0].right.value
            return [row for row in self.aggregate_rows if row.location == location]
        query = self.db.query(
            Person.religious_background,
            Person.age,
            func.count(Person.id).label("count"),
        ).filter(Person.age >= 18, *filters)
        if self.run_id is None:
            query = query.filter(
                Person.run_id.is_(None), Person.baseline_profile == "current"
            )
        else:
            query = query.filter(Person.run_id == self.run_id)
        return query.group_by(Person.religious_background, Person.age).all()

    @staticmethod
    def aggregate_population(db: Session, run_id: Optional[UUID] = None):
        """Load the shared inputs required by every polling calibration."""
        query = db.query(
            Person.location,
            Person.religious_background,
            Person.age,
            func.count(Person.id).label("count"),
        ).filter(Person.age >= 18)
        if run_id is None:
            query = query.filter(
                Person.run_id.is_(None), Person.baseline_profile == "current"
            )
        else:
            query = query.filter(Person.run_id == run_id)
        return query.group_by(
            Person.location, Person.religious_background, Person.age
        ).all()

    def _predict(self, *filters) -> Dict[str, Any]:
        rows = self._rows(*filters)
        eligible = sum(row.count for row in rows)
        if eligible == 0:
            return self._empty()

        unite = remain = undecided = 0.0
        for row in rows:
            yes, no, uncertain, _ = self.responses[row.religious_background]
            response_total = yes + no + uncertain
            turnout = self._turnout(row.age, row.religious_background)
            likely_voters = row.count * turnout
            unite += likely_voters * yes / response_total
            remain += likely_voters * no / response_total
            undecided += likely_voters * uncertain / response_total

        projected_turnout = unite + remain + undecided
        unite_share = unite / projected_turnout
        remain_share = remain / projected_turnout
        undecided_share = undecided / projected_turnout
        decided = unite + remain
        proportional_unite = unite / decided if decided else 0.0
        return {
            "eligible_population": eligible,
            "projected_turnout": round(projected_turnout),
            "turnout_rate": round(projected_turnout / eligible, 4),
            "unite": round(unite),
            "remain": round(remain),
            "undecided": round(undecided),
            "unite_share": round(unite_share, 4),
            "remain_share": round(remain_share, 4),
            "undecided_share": round(undecided_share, 4),
            "decided_unite_share": round(proportional_unite, 4),
            "intervals": {
                "unite_share": _wilson_interval(
                    unite_share, self.source["sample_size"]
                ),
                "remain_share": _wilson_interval(
                    remain_share, self.source["sample_size"]
                ),
                "turnout_rate": _wilson_interval(
                    projected_turnout / eligible, self.source["sample_size"]
                ),
            },
            "scenarios": [
                {
                    "id": "undecided_to_remain",
                    "label": "All undecided vote remain",
                    "unite_share": round(unite / projected_turnout, 4),
                },
                {
                    "id": "proportional",
                    "label": "Undecided split like decided voters",
                    "unite_share": round(proportional_unite, 4),
                },
                {
                    "id": "undecided_to_unite",
                    "label": "All undecided vote unite",
                    "unite_share": round((unite + undecided) / projected_turnout, 4),
                },
            ],
        }

    @staticmethod
    def _empty() -> Dict[str, Any]:
        zero_interval = {"low": 0.0, "estimate": 0.0, "high": 0.0}
        return {
            "eligible_population": 0,
            "projected_turnout": 0,
            "turnout_rate": 0.0,
            "unite": 0,
            "remain": 0,
            "undecided": 0,
            "unite_share": 0.0,
            "remain_share": 0.0,
            "undecided_share": 0.0,
            "decided_unite_share": 0.0,
            "intervals": {
                "unite_share": zero_interval,
                "remain_share": zero_interval,
                "turnout_rate": zero_interval,
            },
            "scenarios": [],
        }

    def predict(self) -> Dict[str, Any]:
        result = self._predict()
        if self.total_population is not None:
            total_population = self.total_population
        elif self.aggregate_rows is None:
            total_query = self.db.query(func.count(Person.id))
            total_query = total_query.filter(
                Person.run_id.is_(None)
                if self.run_id is None
                else Person.run_id == self.run_id
            )
            if self.run_id is None:
                total_query = total_query.filter(Person.baseline_profile == "current")
            total_population = total_query.scalar() or 0
        else:
            total_population = sum(row.count for row in self.aggregate_rows)
        return {
            "total_population": total_population,
            **result,
            "source": self.source,
            "limitations": (
                "Adult resident eligibility proxy; community-background and age "
                "marginals are not causal predictors or a joint poll model."
                + (
                    " Custom values calibrate LucidTalk subgroup odds against the "
                    "current reference population, then hold those odds fixed as "
                    "simulated demographics change. They inherit the LucidTalk "
                    "sampling interval and are a user scenario, not a new poll."
                    if self.calibration == "custom_lucidtalk"
                    else ""
                )
            ),
        }

    def predict_by_location(self) -> Dict[str, Dict[str, Any]]:
        from ..core.models import Location

        return {loc.value: self._predict(Person.location == loc) for loc in Location}
