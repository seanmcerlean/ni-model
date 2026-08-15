"""Add compact person identifiers, temporal events, and checkpoints.

Revision ID: 20260731_0004
Revises: 20260731_0003
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260731_0004"
down_revision: Optional[str] = "20260731_0003"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column("persons", sa.Column("person_number", sa.BigInteger()))
    op.add_column("persons", sa.Column("birth_year", sa.Integer()))
    op.create_index(
        op.f("ix_persons_person_number"),
        "persons",
        ["person_number"],
        unique=True,
    )
    op.create_index(
        op.f("ix_persons_birth_year"), "persons", ["birth_year"], unique=False
    )

    # Existing databases may contain current, historical, and cloned run rows.
    # Assign compact stable identifiers without guessing their reference year.
    op.execute(
        """WITH numbered AS (
               SELECT id, row_number() OVER (ORDER BY id) AS person_number
               FROM persons
           )
           UPDATE persons
           SET person_number = numbered.person_number
           FROM numbered
           WHERE persons.id = numbered.id"""
    )
    op.alter_column("persons", "person_number", nullable=False)
    op.execute("CREATE SEQUENCE persons_person_number_seq")
    op.execute(
        "SELECT setval('persons_person_number_seq', "
        "COALESCE((SELECT max(person_number) FROM persons), 0) + 1, false)"
    )
    op.alter_column(
        "persons",
        "person_number",
        server_default=sa.text("nextval('persons_person_number_seq')"),
    )

    op.create_table(
        "simulation_person_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_event_run_year", "simulation_person_events", ["run_id", "year"]
    )
    op.create_index(
        "idx_event_run_person_year",
        "simulation_person_events",
        ["run_id", "person_id", "year"],
    )

    op.create_table(
        "simulation_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("storage_uri", sa.String(length=1000), nullable=False),
        sa.Column("population_count", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "year", name="uq_run_checkpoint_year"),
    )
    op.create_index(
        "idx_checkpoint_run_year",
        "simulation_checkpoints",
        ["run_id", "year"],
    )


def downgrade() -> None:
    op.drop_index("idx_checkpoint_run_year", table_name="simulation_checkpoints")
    op.drop_table("simulation_checkpoints")
    op.drop_index("idx_event_run_person_year", table_name="simulation_person_events")
    op.drop_index("idx_event_run_year", table_name="simulation_person_events")
    op.drop_table("simulation_person_events")
    op.alter_column("persons", "person_number", server_default=None)
    op.execute("DROP SEQUENCE persons_person_number_seq")
    op.drop_index(op.f("ix_persons_birth_year"), table_name="persons")
    op.drop_index(op.f("ix_persons_person_number"), table_name="persons")
    op.drop_column("persons", "birth_year")
    op.drop_column("persons", "person_number")
