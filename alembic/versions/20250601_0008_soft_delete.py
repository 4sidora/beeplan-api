"""Soft delete for concentrators and edge devices."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def _unique_constraint_name(table: str, column: str) -> str | None:
    bind = op.get_bind()
    for uc in inspect(bind).get_unique_constraints(table):
        if uc.get("column_names") == [column]:
            return uc["name"]
    return None


def upgrade() -> None:
    op.add_column(
        "concentrators",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "edge_devices",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    conc_uc = _unique_constraint_name("concentrators", "ingest_token")
    if conc_uc:
        op.drop_constraint(conc_uc, "concentrators", type_="unique")
    op.create_index(
        "uq_concentrators_ingest_token_active",
        "concentrators",
        ["ingest_token"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    edge_uc = _unique_constraint_name("edge_devices", "public_id")
    if edge_uc:
        op.drop_constraint(edge_uc, "edge_devices", type_="unique")
    op.create_index(
        "uq_edge_devices_public_id_active",
        "edge_devices",
        ["public_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_edge_devices_public_id_active", table_name="edge_devices")
    op.create_unique_constraint("edge_devices_public_id_key", "edge_devices", ["public_id"])

    op.drop_index("uq_concentrators_ingest_token_active", table_name="concentrators")
    op.create_unique_constraint("concentrators_ingest_token_key", "concentrators", ["ingest_token"])

    op.drop_column("edge_devices", "deleted_at")
    op.drop_column("concentrators", "deleted_at")
