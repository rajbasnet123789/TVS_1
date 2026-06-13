"""Add camera position fields and MCMT support

Revision ID: 001_mcmt
Revises: 
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa


revision = "001_mcmt"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cameras", sa.Column("pos_x", sa.Integer(), server_default="0"))
    op.add_column("cameras", sa.Column("pos_y", sa.Integer(), server_default="0"))
    op.add_column("cameras", sa.Column("pos_z", sa.Integer(), server_default="0"))
    op.add_column("chickens", sa.Column("global_id", sa.Integer(), nullable=True, unique=True))


def downgrade() -> None:
    op.drop_column("chickens", "global_id")
    op.drop_column("cameras", "pos_z")
    op.drop_column("cameras", "pos_y")
    op.drop_column("cameras", "pos_x")
