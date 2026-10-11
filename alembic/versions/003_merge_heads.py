"""merge oauth and enterprise migration heads

Revision ID: 003_merge_heads
Revises: 002_oauth, 002_enterprise
Create Date: 2026-10-11
"""

from collections.abc import Sequence

revision: str = "003_merge_heads"
down_revision: tuple[str, str] = ("002_oauth", "002_enterprise")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
