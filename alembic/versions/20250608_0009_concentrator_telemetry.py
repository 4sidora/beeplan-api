"""Concentrator self-telemetry (signal, battery)."""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "concentrator_telemetry_samples",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "concentrator_id",
            sa.Integer(),
            sa.ForeignKey("concentrators.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_concentrator_telemetry_conc_ts",
        "concentrator_telemetry_samples",
        ["concentrator_id", "ts"],
    )


def downgrade() -> None:
    op.drop_index("ix_concentrator_telemetry_conc_ts", table_name="concentrator_telemetry_samples")
    op.drop_table("concentrator_telemetry_samples")
