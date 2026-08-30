"""scope asset external IDs to workspaces

Revision ID: 077
Revises: 076
Create Date: 2026-08-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "077"
down_revision: Union[str, None] = "076"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ux_assets_user_source_external", table_name="assets")
    op.create_index(
        "ux_assets_workspace_source_external",
        "assets",
        ["workspace_id", "source", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_assets_workspace_source_external", table_name="assets")
    op.create_index(
        "ux_assets_user_source_external",
        "assets",
        ["user_id", "source", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
