"""Rename edge_devices.label to name; add firmware_version."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _edge_device_columns() -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns("edge_devices")}


def upgrade() -> None:
    cols = _edge_device_columns()
    if "label" in cols and "name" not in cols:
        op.alter_column("edge_devices", "label", new_column_name="name")
    cols = _edge_device_columns()
    if "firmware_version" not in cols:
        op.add_column(
            "edge_devices",
            sa.Column("firmware_version", sa.String(32), nullable=True),
        )


def downgrade() -> None:
    cols = _edge_device_columns()
    if "firmware_version" in cols:
        op.drop_column("edge_devices", "firmware_version")
    cols = _edge_device_columns()
    if "name" in cols and "label" not in cols:
        op.alter_column("edge_devices", "name", new_column_name="label")
