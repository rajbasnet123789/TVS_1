"""add deletion_requests table

Revision ID: 005
Revises: 004
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deletion_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_by", sa.String(255), nullable=True),
    )
    op.create_index("ix_deletion_requests_status", "deletion_requests", ["status"])
    op.create_index("ix_deletion_requests_user_id", "deletion_requests", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_deletion_requests_user_id", table_name="deletion_requests")
    op.drop_index("ix_deletion_requests_status", table_name="deletion_requests")
    op.drop_table("deletion_requests")
