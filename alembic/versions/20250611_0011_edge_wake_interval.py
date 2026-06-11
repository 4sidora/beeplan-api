"""Edge device: persisted wake_interval_sec from last firmware build."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("edge_devices", "wake_interval_sec"):
        op.add_column(
            "edge_devices",
            sa.Column("wake_interval_sec", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("edge_devices", "wake_interval_sec"):
        op.drop_column("edge_devices", "wake_interval_sec")
