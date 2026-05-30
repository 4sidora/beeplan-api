"""colony extended fields

Revision ID: 0004
Revises: 0003
Create Date: 2025-05-30

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("colonies", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("colonies", sa.Column("colony_type", sa.String(32), nullable=True))
    op.add_column("colonies", sa.Column("hive_type", sa.String(64), nullable=True))
    op.add_column("colonies", sa.Column("body_count", sa.Integer(), nullable=True))
    op.add_column("colonies", sa.Column("frames_per_body", sa.Integer(), nullable=True))
    op.add_column("colonies", sa.Column("hive_volume_m3", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("colonies", "hive_volume_m3")
    op.drop_column("colonies", "frames_per_body")
    op.drop_column("colonies", "body_count")
    op.drop_column("colonies", "hive_type")
    op.drop_column("colonies", "colony_type")
    op.drop_column("colonies", "description")
