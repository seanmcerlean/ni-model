from typing import Any, Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.models import Origin, Person, ReligiousBackground

# Default propensity rates: probability of voting Unite (Irish unity)
# Remaining share split evenly between Remain (union) and Undecided
_DEFAULT_RATES: Dict[str, Any] = {
    "by_religion": {
        ReligiousBackground.CATHOLIC: 0.75,
        ReligiousBackground.PROTESTANT: 0.08,
        ReligiousBackground.OTHER: 0.35,
        ReligiousBackground.NONE: 0.30,
    },
    "by_origin": {
        Origin.ROI: 0.90,
        Origin.NI: 0.40,
        Origin.GB: 0.10,
        Origin.OTHER: 0.35,
    },
    # Age modifiers applied additively to religion-based rate
    "age_modifiers": {
        (0, 34): +0.05,
        (35, 54): 0.00,
        (55, 200): -0.05,
    },
    # Weight given to religion vs origin signal (must sum to 1.0)
    "religion_weight": 0.70,
    "origin_weight": 0.30,
}


class VotingPredictor:
    """Predicts vote shares (Unite / Remain / Undecided) from current population."""

    def __init__(self, db_session: Session, rates: Dict[str, Any] = None):
        self.db = db_session
        self.rates = rates or _DEFAULT_RATES

    def _age_modifier(self, age: int) -> float:
        for (min_age, max_age), mod in self.rates["age_modifiers"].items():
            if min_age <= age <= max_age:
                return mod
        return 0.0

    def _unite_propensity(
        self, religion: ReligiousBackground, origin: Origin, age: int
    ) -> float:
        r_rate = self.rates["by_religion"].get(religion, 0.30)
        o_rate = self.rates["by_origin"].get(origin, 0.30)
        blended = (
            r_rate * self.rates["religion_weight"]
            + o_rate * self.rates["origin_weight"]
        )
        return max(0.0, min(1.0, blended + self._age_modifier(age)))

    def predict(self) -> Dict[str, Any]:
        """Return predicted vote shares and counts for the current population."""
        rows = (
            self.db.query(
                Person.religious_background,
                Person.origin,
                Person.age,
                func.count(Person.id).label("count"),
            )
            .group_by(Person.religious_background, Person.origin, Person.age)
            .all()
        )

        total = sum(r.count for r in rows)
        if total == 0:
            return {
                "total_population": 0,
                "unite": 0,
                "remain": 0,
                "undecided": 0,
                "unite_share": 0.0,
                "remain_share": 0.0,
                "undecided_share": 0.0,
            }

        unite_votes = 0.0
        for row in rows:
            p = self._unite_propensity(row.religious_background, row.origin, row.age)
            unite_votes += p * row.count

        remain_votes = sum(
            (1.0 - self._unite_propensity(r.religious_background, r.origin, r.age))
            * 0.6
            * r.count
            for r in rows
        )
        undecided_votes = total - unite_votes - remain_votes

        return {
            "total_population": total,
            "unite": round(unite_votes),
            "remain": round(remain_votes),
            "undecided": round(undecided_votes),
            "unite_share": round(unite_votes / total, 4),
            "remain_share": round(remain_votes / total, 4),
            "undecided_share": round(undecided_votes / total, 4),
        }

    def predict_by_location(self) -> Dict[str, Dict[str, Any]]:
        """Return vote predictions broken down by location."""
        from ..core.models import Location

        return {
            loc.value: self._predict_for_filter(Person.location == loc)
            for loc in Location
        }

    def _predict_for_filter(self, *filters) -> Dict[str, Any]:
        rows = (
            self.db.query(
                Person.religious_background,
                Person.origin,
                Person.age,
                func.count(Person.id).label("count"),
            )
            .filter(*filters)
            .group_by(Person.religious_background, Person.origin, Person.age)
            .all()
        )

        total = sum(r.count for r in rows)
        if total == 0:
            return {
                "total": 0,
                "unite_share": 0.0,
                "remain_share": 0.0,
                "undecided_share": 0.0,
            }

        unite = sum(
            self._unite_propensity(r.religious_background, r.origin, r.age) * r.count
            for r in rows
        )
        remain = sum(
            (1.0 - self._unite_propensity(r.religious_background, r.origin, r.age))
            * 0.6
            * r.count
            for r in rows
        )
        return {
            "total": total,
            "unite_share": round(unite / total, 4),
            "remain_share": round(remain / total, 4),
            "undecided_share": round((total - unite - remain) / total, 4),
        }
