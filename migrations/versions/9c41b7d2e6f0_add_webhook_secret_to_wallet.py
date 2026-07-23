"""Add a separate webhook signing secret to wallets.

Revision ID: 9c41b7d2e6f0
Revises: e4f8a9b2c1d8
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa


revision = "9c41b7d2e6f0"
down_revision = "e4f8a9b2c1d8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "wallet",
        sa.Column("webhook_secret", sa.String(length=255), nullable=True),
    )


def downgrade():
    op.drop_column("wallet", "webhook_secret")
