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
    op.add_column('payout', sa.Column('task_id', sa.String(512), nullable=True))
    op.add_column('payout', sa.Column('external_id', sa.String(512), nullable=True))
    op.create_index(
        'uq_payout_task_id',
        'payout',
        ['task_id'],
        unique=True
    )
    op.create_index(
        'uq_payout_external_id',
        'payout',
        ['external_id'],
        unique=True
    )

def downgrade():
    op.drop_index('uq_payout_external_id', table_name='payout')
    op.drop_index('uq_payout_task_id', table_name='payout')
    op.drop_column('payout', 'external_id')
    op.drop_column('payout', 'task_id')
