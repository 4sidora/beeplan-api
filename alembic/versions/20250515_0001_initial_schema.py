"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-05-15

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("oauth_provider", sa.String(64), nullable=True),
        sa.Column("oauth_subject", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "apiaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "concentrators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("apiary_id", sa.Integer(), sa.ForeignKey("apiaries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "ingest_token",
            sa.String(36),
            nullable=False,
            unique=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "colonies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("apiary_id", sa.Integer(), sa.ForeignKey("apiaries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "edge_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("concentrator_id", sa.Integer(), sa.ForeignKey("concentrators.id", ondelete="CASCADE"), nullable=False),
        sa.Column("public_id", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("current_colony_id", sa.Integer(), sa.ForeignKey("colonies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "edge_device_colony_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("edge_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("colony_id", sa.Integer(), sa.ForeignKey("colonies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attached_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("detached_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_assignment_device_detached",
        "edge_device_colony_assignments",
        ["device_id", "detached_at"],
    )

    op.create_table(
        "telemetry_samples",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("colony_id", sa.Integer(), sa.ForeignKey("colonies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_device_id", sa.Integer(), sa.ForeignKey("edge_devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
    )
    op.create_index("ix_telemetry_colony_ts", "telemetry_samples", ["colony_id", "ts"])
    op.create_index("ix_telemetry_metric_ts", "telemetry_samples", ["metric", "ts"])


def downgrade() -> None:
    op.drop_index("ix_telemetry_metric_ts", table_name="telemetry_samples")
    op.drop_index("ix_telemetry_colony_ts", table_name="telemetry_samples")
    op.drop_table("telemetry_samples")
    op.drop_index("ix_assignment_device_detached", table_name="edge_device_colony_assignments")
    op.drop_table("edge_device_colony_assignments")
    op.drop_table("edge_devices")
    op.drop_table("colonies")
    op.drop_table("concentrators")
    op.drop_table("apiaries")
    op.drop_table("users")
