"""Evidence-calibrated border-poll scenario projections.

This is a polling scenario, not a prediction of constitutional identity from
religion.  NILT's published religion cross-tabs are used as the closest
available proxy for the model's Census community-background field; age affects
turnout only.  Other unobserved factors and future opinion change remain outside
the model.
"""

import math
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.models import Person, ReligiousBackground

SOURCE = {
    "name": "Northern Ireland Life and Times Survey 2024",
    "publisher": "ARK",
    "fieldwork": "6 September to 19 November 2024",
    "sample_size": 1199,
    "url": "https://www.ark.ac.uk/nilt/2024/Political_Attitudes/REFUNIFY.html",
    "question": "REFUNIFY: referendum tomorrow on unifying with the Republic of Ireland",
}

# Published percentages. Other religions are not separately tabulated by ARK,
# so the all-adult result is used transparently for that small Census group.
_RESPONSES = {
    ReligiousBackground.CATHOLIC: (0.68, 0.10, 0.17, 0.05),
    ReligiousBackground.PROTESTANT: (0.10, 0.74, 0.12, 0.04),
    ReligiousBackground.NONE: (0.35, 0.41, 0.16, 0.06),
    ReligiousBackground.OTHER: (0.36, 0.42, 0.16, 0.05),
}

# NILT would-not-vote percentage by age. The 1% overall ineligible response is
# excluded because the resident model cannot observe citizenship/registration.
_NON_VOTE_BY_AGE = (
    (18, 24, 0.10),
    (25, 34, 0.03),
    (35, 44, 0.04),
    (45, 54, 0.04),
    (55, 64, 0.05),
    (65, 200, 0.06),
)


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

    def __init__(self, db_session: Session, run_id: Optional[UUID] = None):
        self.db = db_session
        self.run_id = run_id

    @staticmethod
    def _turnout(age: int, background: ReligiousBackground) -> float:
        age_non_vote = next(
            rate for low, high, rate in _NON_VOTE_BY_AGE if low <= age <= high
        )
        background_non_vote = _RESPONSES[background][3]
        # Average the two published marginal signals; joint microdata is not
        # inferred from separate cross-tabs.
        return 1.0 - ((age_non_vote + background_non_vote) / 2)

    def _rows(self, *filters):
        query = self.db.query(
            Person.religious_background,
            Person.age,
            func.count(Person.id).label("count"),
        ).filter(Person.age >= 18, *filters)
        if self.run_id is None:
            query = query.filter(Person.run_id.is_(None))
        else:
            query = query.filter(Person.run_id == self.run_id)
        return query.group_by(Person.religious_background, Person.age).all()

    def _predict(self, *filters) -> Dict[str, Any]:
        rows = self._rows(*filters)
        eligible = sum(row.count for row in rows)
        if eligible == 0:
            return self._empty()

        unite = remain = undecided = 0.0
        for row in rows:
            yes, no, uncertain, _ = _RESPONSES[row.religious_background]
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
                "unite_share": _wilson_interval(unite_share, SOURCE["sample_size"]),
                "remain_share": _wilson_interval(remain_share, SOURCE["sample_size"]),
                "turnout_rate": _wilson_interval(
                    projected_turnout / eligible, SOURCE["sample_size"]
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
        total_query = self.db.query(func.count(Person.id))
        total_query = total_query.filter(
            Person.run_id.is_(None)
            if self.run_id is None
            else Person.run_id == self.run_id
        )
        return {
            "total_population": total_query.scalar() or 0,
            **result,
            "source": SOURCE,
            "limitations": "Adult resident eligibility proxy; community-background and age marginals are not causal predictors or a joint poll model.",
        }

    def predict_by_location(self) -> Dict[str, Dict[str, Any]]:
        from ..core.models import Location

        return {loc.value: self._predict(Person.location == loc) for loc in Location}
