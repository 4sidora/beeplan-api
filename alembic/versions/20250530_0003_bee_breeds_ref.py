"""bee breeds reference table

Revision ID: 0003
Revises: 0002
Create Date: 2025-05-30

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

BREEDS = [
    "Карникола",
    "Бакфаст",
    "Среднерусская",
    "Карпатская",
    "Местная",
    "Бурзянская",
    "Кавказская",
    "Итальянская",
]


def upgrade() -> None:
    op.create_table(
        "bee_breeds",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
    )
    breeds = sa.table("bee_breeds", sa.column("name", sa.String))
    op.bulk_insert(breeds, [{"name": n} for n in BREEDS])


def downgrade() -> None:
    op.drop_table("bee_breeds")
