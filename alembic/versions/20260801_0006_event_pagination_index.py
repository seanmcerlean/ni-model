"""Cover annual event pagination with the run/year index.

Revision ID: 20260801_0006
Revises: 20260801_0005
"""

from typing import Optional, Sequence, Union

from alembic import op

revision: str = "20260801_0006"
down_revision: Optional[str] = "20260801_0005"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.drop_index("idx_event_run_year", table_name="simulation_person_events")
    op.create_index(
        "idx_event_run_year_id",
        "simulation_person_events",
        ["run_id", "year", "id"],
    )


def downgrade() -> None:
    op.drop_index("idx_event_run_year_id", table_name="simulation_person_events")
    op.create_index(
        "idx_event_run_year",
        "simulation_person_events",
        ["run_id", "year"],
    )
