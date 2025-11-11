"""Add xpub to wallet
Revision ID: d3f96a84b3bf
Revises: cd6076e578ca
Create Date: 2025-05-30 12:03:08.807677
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3f96a84b3bf'
down_revision = 'cd6076e578ca'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('wallet', sa.Column('xpub', sa.String(), nullable=True))


def downgrade():
    op.drop_column('wallet', 'xpub')