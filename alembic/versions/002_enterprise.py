"""add enterprise tables

Revision ID: 002_enterprise
Revises: 001_initial
Create Date: 2026-09-15

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '002_enterprise'
down_revision: str | None = '001_initial'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Audit logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), index=True),
        sa.Column('action', sa.String(100)),
        sa.Column('resource_type', sa.String(50)),
        sa.Column('resource_id', sa.String(36), nullable=True),
        sa.Column('details', sa.Text, nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True)),
    )

    # Webhook subscriptions
    op.create_table(
        'webhook_subscriptions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), index=True),
        sa.Column('url', sa.String(500)),
        sa.Column('events', sa.Text),
        sa.Column('secret', sa.String(64)),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
    )

    # Webhook deliveries
    op.create_table(
        'webhook_deliveries',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('subscription_id', sa.String(36), sa.ForeignKey('webhook_subscriptions.id'), index=True),
        sa.Column('event', sa.String(100)),
        sa.Column('payload', sa.Text),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('status_code', sa.Integer, nullable=True),
        sa.Column('response_body', sa.Text, nullable=True),
        sa.Column('attempts', sa.Integer, default=0),
        sa.Column('max_attempts', sa.Integer, default=3),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Organizations
    op.create_table(
        'organizations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(200)),
        sa.Column('slug', sa.String(100), unique=True, index=True),
        sa.Column('owner_id', sa.String(36), index=True),
        sa.Column('plan', sa.String(20), default='free'),
        sa.Column('created_at', sa.DateTime(timezone=True)),
    )

    # Teams
    op.create_table(
        'teams',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id'), index=True),
        sa.Column('name', sa.String(100)),
        sa.Column('created_at', sa.DateTime(timezone=True)),
    )

    # Team members
    op.create_table(
        'team_members',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('team_id', sa.String(36), sa.ForeignKey('teams.id'), index=True),
        sa.Column('user_id', sa.String(36), index=True),
        sa.Column('role', sa.String(20), default='viewer'),
        sa.Column('created_at', sa.DateTime(timezone=True)),
    )

    # Team API keys
    op.create_table(
        'team_api_keys',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('team_id', sa.String(36), sa.ForeignKey('teams.id'), index=True),
        sa.Column('organization_id', sa.String(36), index=True),
        sa.Column('api_key_hash', sa.String(64), unique=True, index=True),
        sa.Column('api_key_prefix', sa.String(20)),
        sa.Column('permissions', sa.Text, default='[]'),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table('team_api_keys')
    op.drop_table('team_members')
    op.drop_table('teams')
    op.drop_table('organizations')
    op.drop_table('webhook_deliveries')
    op.drop_table('webhook_subscriptions')
    op.drop_table('audit_logs')
