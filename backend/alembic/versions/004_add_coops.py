"""add coops table and coop_id + snapshot_url to cameras

Revision ID: 004
Revises: 003
Create Date: 2026-06-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coops",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("farm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_coops_farm_id", "coops", ["farm_id"])
    op.create_unique_constraint("uq_coops_farm_id_name", "coops", ["farm_id", "name"])

    op.add_column("cameras", sa.Column("coop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("coops.id"), nullable=True))
    op.add_column("cameras", sa.Column("snapshot_url", sa.String(500), nullable=True))
    op.create_index("ix_cameras_coop_id", "cameras", ["coop_id"])

    op.execute("""
        INSERT INTO coops (id, farm_id, name, sort_order)
        SELECT gen_random_uuid(), farm_id, location, 0
        FROM cameras
        WHERE location IS NOT NULL AND location != ''
        GROUP BY farm_id, location
    """)

    op.execute("""
        UPDATE cameras
        SET coop_id = sub.id
        FROM (
            SELECT c.id AS camera_id, co.id
            FROM cameras c
            JOIN coops co ON co.farm_id = c.farm_id AND co.name = c.location
        ) AS sub
        WHERE cameras.id = sub.camera_id
    """)


def downgrade() -> None:
    op.drop_constraint("uq_coops_farm_id_name", "coops", type_="unique")
    op.drop_index("ix_cameras_coop_id", table_name="cameras")
    op.drop_column("cameras", "snapshot_url")
    op.drop_column("cameras", "coop_id")
    op.drop_index("ix_coops_farm_id", table_name="coops")
    op.drop_table("coops")
