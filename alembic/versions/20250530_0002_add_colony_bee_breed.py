"""add colony bee_breed

Revision ID: 0002
Revises: 0001
Create Date: 2025-05-30

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("colonies", sa.Column("bee_breed", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("colonies", "bee_breed")
