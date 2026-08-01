"""Add model-selected baseline profiles and sample expansion metadata.

Revision ID: 20260801_0007
Revises: 20260801_0006
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260801_0007"
down_revision: Optional[str] = "20260801_0006"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column(
        "persons",
        sa.Column(
            "baseline_profile",
            sa.String(length=32),
            nullable=False,
            server_default="current",
        ),
    )
    op.create_index(
        op.f("ix_persons_baseline_profile"),
        "persons",
        ["baseline_profile"],
        unique=False,
    )
    op.add_column(
        "simulation_runs",
        sa.Column(
            "represented_population_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "simulation_runs",
        sa.Column(
            "population_scale",
            sa.Float(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "simulation_runs",
        sa.Column(
            "baseline_profile",
            sa.String(length=32),
            nullable=False,
            server_default="current",
        ),
    )
    op.execute(
        "UPDATE simulation_runs SET represented_population_count = base_population_count"
    )


def downgrade() -> None:
    op.drop_column("simulation_runs", "baseline_profile")
    op.drop_column("simulation_runs", "population_scale")
    op.drop_column("simulation_runs", "represented_population_count")
    op.drop_index(op.f("ix_persons_baseline_profile"), table_name="persons")
    op.drop_column("persons", "baseline_profile")
