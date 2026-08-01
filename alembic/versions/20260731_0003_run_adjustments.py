"""Persist per-run scenario adjustments.

Revision ID: 20260731_0003
Revises: 20260731_0002
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260731_0003"
down_revision: Optional[str] = "20260731_0002"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column(
        "simulation_runs",
        sa.Column("adjustments", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("simulation_runs", "adjustments")
