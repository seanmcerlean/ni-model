"""Add estimated probable-community lineage.

Revision ID: 20260804_0008
Revises: 20260801_0007
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260804_0008"
down_revision: Optional[str] = "20260801_0007"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


_CATHOLIC_THRESHOLDS = {
    "antrim_and_newtownabbey": 36764,
    "armagh_banbridge_craigavon": 44092,
    "belfast": 49624,
    "causeway_coast_glens": 41338,
    "derry_strabane": 62795,
    "fermanagh_omagh": 56648,
    "lisburn_castlereagh": 33866,
    "mid_east_antrim": 27853,
    "mid_ulster": 56999,
    "newry_mourne_down": 63505,
    "ards_north_down": 23586,
}


def upgrade() -> None:
    background_type = sa.Enum(name="religiousbackground", create_type=False)
    op.add_column(
        "persons", sa.Column("probable_community", background_type, nullable=True)
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        threshold = (
            "CASE location::text "
            + " ".join(
                f"WHEN '{location.upper()}' THEN {value}"
                for location, value in _CATHOLIC_THRESHOLDS.items()
            )
            + " ELSE 40952 END"
        )
        bucket = "mod(abs(hashtextextended(id::text, 0)), 100000)"
        op.execute(
            "UPDATE persons SET probable_community = CASE "
            "WHEN religious_background::text <> 'NONE' THEN religious_background "
            f"WHEN {bucket} < 3040 THEN 'OTHER'::religiousbackground "
            f"WHEN {bucket} < ({threshold}) "
            "THEN 'CATHOLIC'::religiousbackground "
            "ELSE 'PROTESTANT'::religiousbackground END"
        )
    else:
        # SQLite development databases store enums as text. A stable person
        # number gives a reproducible approximation to each LGD probability.
        cases = " ".join(
            f"WHEN '{location.upper()}' THEN {value}"
            for location, value in _CATHOLIC_THRESHOLDS.items()
        )
        op.execute(
            "UPDATE persons SET probable_community = CASE "
            "WHEN religious_background <> 'NONE' THEN religious_background "
            "WHEN abs(coalesce(person_number, rowid)) % 100000 < 3040 "
            "THEN 'OTHER' "
            "WHEN abs(coalesce(person_number, rowid)) % 100000 < "
            f"(CASE location {cases} ELSE 40952 END) "
            "THEN 'CATHOLIC' ELSE 'PROTESTANT' END"
        )
    with op.batch_alter_table("persons") as batch:
        batch.alter_column("probable_community", nullable=False)
        batch.create_check_constraint(
            "ck_person_probable_community_not_none",
            "probable_community <> 'NONE'",
        )
        batch.create_index("idx_probable_community", ["probable_community"])


def downgrade() -> None:
    with op.batch_alter_table("persons") as batch:
        batch.drop_constraint("ck_person_probable_community_not_none", type_="check")
        batch.drop_index("idx_probable_community")
        batch.drop_column("probable_community")
