"""ESP-NOW v2: wifi_channel, telemetry_slot_sec, ingest dedup."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in {col["name"] for col in inspect(bind).get_columns(table)}


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return table in inspect(bind).get_table_names()


def upgrade() -> None:
    if not _has_column("concentrators", "wifi_channel"):
        op.add_column("concentrators", sa.Column("wifi_channel", sa.SmallInteger(), nullable=True))
    if not _has_column("concentrators", "spool_pending_count"):
        op.add_column(
            "concentrators",
            sa.Column("spool_pending_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_column("edge_devices", "telemetry_slot_sec"):
        op.add_column(
            "edge_devices",
            sa.Column("telemetry_slot_sec", sa.Integer(), nullable=True),
        )
    if not _has_table("telemetry_ingest_log"):
        op.create_table(
            "telemetry_ingest_log",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("device_id", sa.Integer(), nullable=False),
            sa.Column("report_id", sa.String(length=128), nullable=False),
            sa.Column(
                "ingested_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["device_id"], ["edge_devices.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("device_id", "report_id", name="uq_telemetry_ingest_device_report"),
        )

    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   concentrator_id,
                   (ROW_NUMBER() OVER (PARTITION BY concentrator_id ORDER BY id) - 1) AS idx
            FROM edge_devices
            WHERE deleted_at IS NULL
        )
        UPDATE edge_devices e
        SET telemetry_slot_sec = (ranked.idx % 100) * 36
        FROM ranked
        WHERE e.id = ranked.id AND e.telemetry_slot_sec IS NULL
        """
    )


def downgrade() -> None:
    if _has_table("telemetry_ingest_log"):
        op.drop_table("telemetry_ingest_log")
    if _has_column("edge_devices", "telemetry_slot_sec"):
        op.drop_column("edge_devices", "telemetry_slot_sec")
    if _has_column("concentrators", "spool_pending_count"):
        op.drop_column("concentrators", "spool_pending_count")
    if _has_column("concentrators", "wifi_channel"):
        op.drop_column("concentrators", "wifi_channel")
