"""Change transactions.row from BLOB to MEDIUMBLOB

Revision ID: 68494a63c4e9
Revises: e4f8a9b2c1d8
Create Date: 2025-12-11 08:08:33.640502

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '68494a63c4e9'
down_revision = 'e4f8a9b2c1d8'
branch_labels = None
depends_on = None


def upgrade():
    # Change column type to MEDIUMBLOB
    op.alter_column(
        "transactions",
        "row",
        type_=MEDIUMBLOB(),
        existing_nullable=True,  # adjust if not nullable
        mysql_existing_type=BLOB(),  # helps Alembic generate correct DDL
    )


def downgrade():
    # Revert column type back to BLOB
    op.alter_column(
        "transactions",
        "row",
        type_=BLOB(),
        existing_nullable=True,  # adjust if not nullable
        mysql_existing_type=MEDIUMBLOB(),
    )
