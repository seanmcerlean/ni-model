"""Replace hybrid counties and constituencies with current LGDs.

Revision ID: 20260731_0002
Revises: 20260730_0001
Create Date: 2026-07-31
"""

from typing import Optional, Sequence, Union

from alembic import op

revision: str = "20260731_0002"
down_revision: Optional[str] = "20260730_0001"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

NEW_VALUES = (
    "ANTRIM_AND_NEWTOWNABBEY",
    "ARMAGH_BANBRIDGE_CRAIGAVON",
    "BELFAST",
    "CAUSEWAY_COAST_GLENS",
    "DERRY_STRABANE",
    "FERMANAGH_OMAGH",
    "LISBURN_CASTLEREAGH",
    "MID_EAST_ANTRIM",
    "MID_ULSTER",
    "NEWRY_MOURNE_DOWN",
    "ARDS_NORTH_DOWN",
)

OLD_VALUES = (
    "ANTRIM",
    "ARMAGH",
    "DOWN",
    "FERMANAGH",
    "DERRY",
    "TYRONE",
    "BELFAST_NORTH",
    "BELFAST_SOUTH",
    "BELFAST_EAST",
    "BELFAST_WEST",
)


def _replace_enum(values, expression):
    op.execute(
        "ALTER TABLE persons ALTER COLUMN location TYPE text USING location::text"
    )
    op.execute("DROP TYPE location")
    quoted = ", ".join(f"'{value}'" for value in values)
    op.execute(f"CREATE TYPE location AS ENUM ({quoted})")
    op.execute(
        "ALTER TABLE persons ALTER COLUMN location TYPE location "
        f"USING ({expression})::location"
    )


def upgrade() -> None:
    expression = """CASE location
        WHEN 'ANTRIM' THEN 'ANTRIM_AND_NEWTOWNABBEY'
        WHEN 'ARMAGH' THEN 'ARMAGH_BANBRIDGE_CRAIGAVON'
        WHEN 'DOWN' THEN 'NEWRY_MOURNE_DOWN'
        WHEN 'FERMANAGH' THEN 'FERMANAGH_OMAGH'
        WHEN 'DERRY' THEN 'DERRY_STRABANE'
        WHEN 'TYRONE' THEN 'MID_ULSTER'
        WHEN 'BELFAST_NORTH' THEN 'BELFAST'
        WHEN 'BELFAST_SOUTH' THEN 'BELFAST'
        WHEN 'BELFAST_EAST' THEN 'BELFAST'
        WHEN 'BELFAST_WEST' THEN 'BELFAST'
    END"""
    _replace_enum(NEW_VALUES, expression)


def downgrade() -> None:
    expression = """CASE location
        WHEN 'ANTRIM_AND_NEWTOWNABBEY' THEN 'ANTRIM'
        WHEN 'ARMAGH_BANBRIDGE_CRAIGAVON' THEN 'ARMAGH'
        WHEN 'BELFAST' THEN 'BELFAST_NORTH'
        WHEN 'CAUSEWAY_COAST_GLENS' THEN 'DERRY'
        WHEN 'DERRY_STRABANE' THEN 'DERRY'
        WHEN 'FERMANAGH_OMAGH' THEN 'FERMANAGH'
        WHEN 'LISBURN_CASTLEREAGH' THEN 'DOWN'
        WHEN 'MID_EAST_ANTRIM' THEN 'ANTRIM'
        WHEN 'MID_ULSTER' THEN 'TYRONE'
        WHEN 'NEWRY_MOURNE_DOWN' THEN 'DOWN'
        WHEN 'ARDS_NORTH_DOWN' THEN 'DOWN'
    END"""
    _replace_enum(OLD_VALUES, expression)
