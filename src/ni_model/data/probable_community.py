"""Best-estimate community lineage for residents reporting no background.

The 2021 Census does not identify a community background for people who report
neither a current religion nor a religion brought up in.  These probabilities
are an ecological estimate, not an observed personal characteristic.  They are
calibrated to the NISRA national-identity by community-background table
(DT-0002): 37.91% Catholic, 59.05% Protestant and 3.04% Other among the 177,361
people in the Census ``None`` category. LGD variation uses the local
Catholic/Protestant odds with 0.65 shrinkage toward the NI-wide estimate.

Source: NISRA Census 2021 flexible table builder, DT-0002.
Methodology: docs/probable-community.md.
"""

from ..core.models import Location, ReligiousBackground

NONE_PROBABLE_CATHOLIC_BY_LOCATION = {
    Location.ANTRIM_AND_NEWTOWNABBEY: 0.34781,
    Location.ARMAGH_BANBRIDGE_CRAIGAVON: 0.42339,
    Location.BELFAST: 0.48045,
    Location.CAUSEWAY_COAST_GLENS: 0.39499,
    Location.DERRY_STRABANE: 0.61629,
    Location.FERMANAGH_OMAGH: 0.55289,
    Location.LISBURN_CASTLEREAGH: 0.31793,
    Location.MID_EAST_ANTRIM: 0.25591,
    Location.MID_ULSTER: 0.55651,
    Location.NEWRY_MOURNE_DOWN: 0.62361,
    Location.ARDS_NORTH_DOWN: 0.21190,
}
NONE_PROBABLE_OTHER = 0.0303978


def infer_probable_community(background, location, rng):
    """Return an initial probable lineage, preserving observed non-None values."""
    if background != ReligiousBackground.NONE:
        return background
    if rng.random() < NONE_PROBABLE_OTHER:
        return ReligiousBackground.OTHER
    probability = NONE_PROBABLE_CATHOLIC_BY_LOCATION[location]
    return (
        ReligiousBackground.CATHOLIC
        if rng.random() < probability
        else ReligiousBackground.PROTESTANT
    )
