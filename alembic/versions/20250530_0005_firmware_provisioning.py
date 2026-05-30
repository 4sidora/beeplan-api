"""Add concentrator gateway fields and firmware_builds table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("concentrators", sa.Column("gateway_mac", sa.String(17), nullable=True))
    op.add_column("concentrators", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("concentrators", sa.Column("firmware_version", sa.String(32), nullable=True))

    op.add_column("edge_devices", sa.Column("hardware_mac", sa.String(17), nullable=True))

    op.create_table(
        "firmware_builds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_type", sa.String(16), nullable=False),
        sa.Column("board", sa.String(32), nullable=False),
        sa.Column("concentrator_id", sa.Integer(), sa.ForeignKey("concentrators.id", ondelete="CASCADE"), nullable=False),
        sa.Column("edge_device_id", sa.Integer(), sa.ForeignKey("edge_devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_firmware_builds_user_id", "firmware_builds", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_firmware_builds_user_id", table_name="firmware_builds")
    op.drop_table("firmware_builds")
    op.drop_column("edge_devices", "hardware_mac")
    op.drop_column("concentrators", "firmware_version")
    op.drop_column("concentrators", "last_seen_at")
    op.drop_column("concentrators", "gateway_mac")
