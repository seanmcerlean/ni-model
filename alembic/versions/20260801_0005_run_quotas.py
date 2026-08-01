"""Add anonymous owner keys for public run quotas.

Revision ID: 20260801_0005
Revises: 20260731_0004
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260801_0005"
down_revision: Optional[str] = "20260731_0004"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column("simulation_runs", sa.Column("owner_key", sa.String(length=64)))
    op.create_index(
        op.f("ix_simulation_runs_owner_key"),
        "simulation_runs",
        ["owner_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_simulation_runs_owner_key"), table_name="simulation_runs")
    op.drop_column("simulation_runs", "owner_key")
