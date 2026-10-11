"""add organization scope to audit logs

Revision ID: 004_audit_org_scope
Revises: 003_merge_heads
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004_audit_org_scope"
down_revision: str | None = "003_merge_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("organization_id", sa.String(36), nullable=True),
    )
    op.create_index(
        "ix_audit_logs_organization_id",
        "audit_logs",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_organization_id", table_name="audit_logs")
    op.drop_column("audit_logs", "organization_id")
