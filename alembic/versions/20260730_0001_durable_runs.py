"""Add durable isolated simulation runs and snapshots.

Revision ID: 20260730_0001
Revises:
Create Date: 2026-07-30
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260730_0001"
down_revision: Optional[str] = None
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.create_table(
        "simulation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_path", sa.String(length=255), nullable=False),
        sa.Column("start_year", sa.Integer(), nullable=False),
        sa.Column("end_year", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("base_population_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=1000), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_simulation_runs_status"),
        "simulation_runs",
        ["status"],
        unique=False,
    )
    op.create_table(
        "persons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column(
            "religious_background",
            sa.Enum(
                "CATHOLIC",
                "PROTESTANT",
                "OTHER",
                "NONE",
                name="religiousbackground",
            ),
            nullable=False,
        ),
        sa.Column(
            "gender",
            sa.Enum("MALE", "FEMALE", "OTHER", name="gender"),
            nullable=False,
        ),
        sa.Column(
            "education_level",
            sa.Enum(
                "PRE_PRIMARY",
                "PRIMARY",
                "SECONDARY",
                "TERTIARY",
                "POSTGRADUATE",
                name="educationlevel",
            ),
            nullable=False,
        ),
        sa.Column(
            "location",
            sa.Enum(
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
                name="location",
            ),
            nullable=False,
        ),
        sa.Column(
            "origin",
            sa.Enum("NI", "ROI", "GB", "OTHER", name="origin"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_persons_run_id"), "persons", ["run_id"], unique=False)
    op.create_index("idx_age", "persons", ["age"])
    op.create_index("idx_religious_background", "persons", ["religious_background"])
    op.create_index("idx_location", "persons", ["location"])
    op.create_index("idx_origin", "persons", ["origin"])
    op.create_index("idx_age_location", "persons", ["age", "location"])
    op.create_index(
        "idx_religious_gender",
        "persons",
        ["religious_background", "gender"],
    )
    op.create_index("idx_run_location", "persons", ["run_id", "location"])
    op.create_index("idx_run_age", "persons", ["run_id", "age"])
    op.create_table(
        "simulation_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "year", name="uq_run_snapshot_year"),
    )
    op.create_index(
        op.f("ix_simulation_snapshots_run_id"),
        "simulation_snapshots",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_simulation_snapshots_run_id"),
        table_name="simulation_snapshots",
    )
    op.drop_table("simulation_snapshots")
    op.drop_index("idx_run_age", table_name="persons")
    op.drop_index("idx_run_location", table_name="persons")
    op.drop_index("idx_religious_gender", table_name="persons")
    op.drop_index("idx_age_location", table_name="persons")
    op.drop_index("idx_origin", table_name="persons")
    op.drop_index("idx_location", table_name="persons")
    op.drop_index("idx_religious_background", table_name="persons")
    op.drop_index("idx_age", table_name="persons")
    op.drop_index(op.f("ix_persons_run_id"), table_name="persons")
    op.drop_table("persons")
    op.drop_index(op.f("ix_simulation_runs_status"), table_name="simulation_runs")
    op.drop_table("simulation_runs")
