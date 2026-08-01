"""add camera roi field

Revision ID: 002
Revises: 001
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cameras", sa.Column("roi", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("cameras", "roi")
