"""Edge device last_seen_at and unbound device telemetry."""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "edge_devices",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "edge_device_telemetry_samples",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("edge_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_edge_device_telemetry_device_ts",
        "edge_device_telemetry_samples",
        ["device_id", "ts"],
    )


def downgrade() -> None:
    op.drop_index("ix_edge_device_telemetry_device_ts", table_name="edge_device_telemetry_samples")
    op.drop_table("edge_device_telemetry_samples")
    op.drop_column("edge_devices", "last_seen_at")
