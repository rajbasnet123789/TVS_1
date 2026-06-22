"""multi_farm: add farms table and farm_id to existing tables

Revision ID: 001
Revises:
Create Date: 2026-06-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = "001_mcmt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create farms table
    op.create_table(
        "farms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("settings", sa.JSON, server_default="{}"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Insert Default Farm with hardcoded deterministic UUID
    op.execute("INSERT INTO farms (id, name, slug, is_active) VALUES ('00000000-0000-0000-0000-000000000001', 'Default Farm', 'default', true)")

    # Add farm_id to users (nullable — super_admin has no farm)
    op.add_column("users", sa.Column("farm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True))

    # Set all existing users to the Default Farm (except the default super_admin)
    op.execute("UPDATE users SET farm_id = (SELECT id FROM farms WHERE slug = 'default') WHERE email != 'admin@poultry.farm'")

    # Add farm_id to cameras
    op.add_column("cameras", sa.Column("farm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True))
    op.execute("UPDATE cameras SET farm_id = (SELECT id FROM farms WHERE slug = 'default')")
    op.alter_column("cameras", "farm_id", nullable=False)
    op.create_index("ix_cameras_farm_id", "cameras", ["farm_id"])

    # Add farm_id to chickens + unique constraint on (farm_id, chicken_id)
    op.add_column("chickens", sa.Column("farm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True))
    op.execute("UPDATE chickens SET farm_id = (SELECT id FROM farms WHERE slug = 'default')")
    op.alter_column("chickens", "farm_id", nullable=False)
    op.create_index("ix_chickens_farm_id", "chickens", ["farm_id"])

    # Gracefully and dynamically discover and drop the unique constraint on chicken_id
    try:
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        constraints = inspector.get_unique_constraints("chickens")
        constraint_name = "chickens_chicken_id_key"
        for const in constraints:
            if const["column_names"] == ["chicken_id"]:
                constraint_name = const["name"]
                break
        op.drop_constraint(constraint_name, "chickens", type_="unique")
    except Exception as e:
        err_msg = str(e).lower()
        if "does not exist" in err_msg or "not found" in err_msg or "undefined_object" in err_msg:
            print(f"Warning: Could not drop unique constraint on chickens.chicken_id: {e}")
        else:
            raise

    op.create_unique_constraint("uq_farm_chicken", "chickens", ["farm_id", "chicken_id"])

    # Add farm_id to alerts
    op.add_column("alerts", sa.Column("farm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True))
    op.execute("UPDATE alerts SET farm_id = (SELECT id FROM farms WHERE slug = 'default')")
    op.alter_column("alerts", "farm_id", nullable=False)
    op.create_index("ix_alerts_farm_id", "alerts", ["farm_id"])

    # Add farm_id to alert_rules
    op.add_column("alert_rules", sa.Column("farm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True))
    op.execute("UPDATE alert_rules SET farm_id = (SELECT id FROM farms WHERE slug = 'default')")
    op.alter_column("alert_rules", "farm_id", nullable=False)
    op.create_index("ix_alert_rules_farm_id", "alert_rules", ["farm_id"])


def downgrade() -> None:
    op.drop_index("ix_alert_rules_farm_id", table_name="alert_rules")
    op.drop_index("ix_alerts_farm_id", table_name="alerts")
    op.drop_index("ix_chickens_farm_id", table_name="chickens")
    op.drop_index("ix_cameras_farm_id", table_name="cameras")

    op.drop_constraint("uq_farm_chicken", "chickens", type_="unique")
    op.create_unique_constraint("chickens_chicken_id_key", "chickens", ["chicken_id"])

    op.drop_column("alert_rules", "farm_id")
    op.drop_column("alerts", "farm_id")
    op.drop_column("chickens", "farm_id")
    op.drop_column("cameras", "farm_id")
    op.drop_column("users", "farm_id")
    op.drop_table("farms")
