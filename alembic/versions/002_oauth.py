"""add oauth and avatar columns

Revision ID: 002_oauth
Revises: 001_initial
Create Date: 2026-09-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_oauth"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("oauth_provider", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("oauth_id", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.String(500), nullable=True))
    op.create_index("ix_users_oauth_id", "users", ["oauth_id"])


def downgrade() -> None:
    op.drop_index("ix_users_oauth_id", table_name="users")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "oauth_id")
    op.drop_column("users", "oauth_provider")
