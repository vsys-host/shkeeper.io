"""Add callback_url

Revision ID: cd6076e578db
Revises: 0319bf7b9426
Create Date: 2024-07-31 10:39:30.170808

"""
from alembic import op
import sqlalchemy as sa

revision = 'cd6076e578db'
down_revision = 'cd6076e578ca'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('payout', sa.Column('callback_url', sa.String(512), nullable=True))
    op.add_column('wallet', sa.Column('callback_url', sa.String(512), nullable=True))

def downgrade():
    op.drop_column('payout', 'callback_url')
    op.drop_column('wallet', 'callback_url')
