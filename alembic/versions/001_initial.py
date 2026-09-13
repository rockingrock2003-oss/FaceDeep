"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-09-12

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '001_initial'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('username', sa.String(100), unique=True, index=True),
        sa.Column('email', sa.String(255), unique=True, index=True),
        sa.Column('hashed_password', sa.String(255)),
        sa.Column('api_key_hash', sa.String(64), unique=True, index=True),
        sa.Column('api_key_prefix', sa.String(20)),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('is_verified', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        # Tracking
        sa.Column('entry_in_chroma_db', sa.Integer, default=0),
        sa.Column('add_count', sa.Integer, default=0),
        sa.Column('delete_count', sa.Integer, default=0),
        sa.Column('update_count', sa.Integer, default=0),
        sa.Column('number_of_api_use_for_service', sa.Integer, default=0),
        # Billing
        sa.Column('plan', sa.String(20), default='free'),
        sa.Column('stripe_customer_id', sa.String(255), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(255), nullable=True),
        sa.Column('plan_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('daily_requests_used', sa.Integer, default=0),
        sa.Column('daily_requests_reset_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_revenue_generated', sa.Float, default=0.0),
    )

    # Email verifications table
    op.create_table(
        'email_verifications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), index=True),
        sa.Column('token', sa.String(64), unique=True, index=True),
        sa.Column('is_used', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
    )

    # Import jobs table
    op.create_table(
        'import_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), index=True),
        sa.Column('person_id', sa.String(255)),
        sa.Column('label', sa.String(255)),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('total', sa.Integer, default=0),
        sa.Column('processed', sa.Integer, default=0),
        sa.Column('success', sa.Integer, default=0),
        sa.Column('failed', sa.Integer, default=0),
        sa.Column('errors', sa.String(5000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('import_jobs')
    op.drop_table('email_verifications')
    op.drop_table('users')
