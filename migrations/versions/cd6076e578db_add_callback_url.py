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
    op.add_column('payout', sa.Column('task_id', sa.String(512)))
    op.add_column('payout', sa.Column('callback_url', sa.String(512), nullable=True))
    op.add_column('payout', sa.Column('external_id', sa.String(512), nullable=True))
    op.add_column('payout', sa.Column('success', sa.String(512), nullable=True))
    op.add_column('payout', sa.Column('error', sa.String(512), nullable=True))
    op.create_index('ix_payout_task_id', 'payout', ['task_id'])
    op.create_index('ix_payout_status', 'payout', ['status'])
    op.create_index('ix_payout_created_at', 'payout', ['created_at'])
    op.create_index('ix_payout_task_status_created', 'payout', ['task_id', 'status', 'created_at'])


def downgrade():
    op.drop_index('ix_payout_task_status_created', table_name='payout')
    op.drop_index('ix_payout_created_at', table_name='payout')
    op.drop_index('ix_payout_status', table_name='payout')
    op.drop_index('ix_payout_task_id', table_name='payout')
    op.drop_column('payout', 'external_id')
    op.drop_column('payout', 'task_id')
    op.drop_column('payout', 'callback_url')
    op.drop_column('payout', 'success')
    op.drop_column('payout', 'error')
