"""Multi-store support

Revision ID: f1a2b3c4d5e6
Revises: e4f8a9b2c1d8
Create Date: 2026-07-20

"""
from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "e4f8a9b2c1d8"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(name):
    return name in _inspector().get_table_names()


def _column_exists(table, column):
    if not _table_exists(table):
        return False
    return column in {c["name"] for c in _inspector().get_columns(table)}


def _fk_names(table):
    return {fk.get("name") for fk in _inspector().get_foreign_keys(table)}


def upgrade():
    if not _table_exists("store"):
        op.create_table(
            "store",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("api_key", sa.String(), nullable=False),
            sa.Column("platform_fee_percent", sa.Numeric(), nullable=True),
            sa.Column(
                "status",
                sa.Enum("ACTIVE", "SUSPENDED", "DELETED", name="storestatus"),
                nullable=True,
                server_default="ACTIVE",
            ),
            sa.Column("is_default", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("api_key"),
        )

    if not _table_exists("store_wallet"):
        op.create_table(
            "store_wallet",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("store_id", sa.Integer(), nullable=False),
            sa.Column("crypto", sa.String(), nullable=False),
            sa.Column("fda_address", sa.String(), nullable=True),
            sa.Column("fee_percent_override", sa.Numeric(), nullable=True),
            sa.Column("fee_collection_address", sa.String(), nullable=True),
            sa.Column("cold_wallet_address", sa.String(), nullable=True),
            sa.Column("pdest", sa.String(), nullable=True),
            sa.Column("pfee", sa.String(), nullable=True),
            sa.Column("payout", sa.Boolean(), nullable=True, server_default="0"),
            sa.Column(
                "ppolicy",
                sa.Enum("MANUAL", "SCHEDULED", "LIMIT", name="payoutpolicy"),
                nullable=True,
                server_default="MANUAL",
            ),
            sa.Column("pcond", sa.String(), nullable=True),
            sa.Column("last_payout_attempt", sa.DateTime(), nullable=True),
            sa.Column(
                "prespolicy",
                sa.Enum("DISABLE", "AMOUNT", "PERCENT", name="payoutreservepolicy"),
                nullable=True,
                server_default="DISABLE",
            ),
            sa.Column("presamount", sa.String(), nullable=True),
            sa.Column(
                "status",
                sa.Enum("PENDING", "READY", "FAILED", name="storewalletstatus"),
                nullable=True,
                server_default="PENDING",
            ),
            sa.Column("last_error", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("store_id", "crypto"),
        )

    if _table_exists("user"):
        with op.batch_alter_table("user", schema=None) as batch_op:
            if not _column_exists("user", "store_id"):
                batch_op.add_column(sa.Column("store_id", sa.Integer(), nullable=True))
            if not _column_exists("user", "role"):
                batch_op.add_column(
                    sa.Column(
                        "role",
                        sa.Enum("ADMIN", "STORE_OWNER", name="userrole"),
                        nullable=True,
                    )
                )
            if "fk_user_store_id" not in _fk_names("user"):
                batch_op.create_foreign_key(
                    "fk_user_store_id", "store", ["store_id"], ["id"]
                )
        if _column_exists("user", "role"):
            # Keep exactly one admin among existing users.
            op.execute(
                sa.text(
                    """
                    UPDATE "user"
                    SET role = :admin_role
                    WHERE id = (
                        SELECT id
                        FROM "user"
                        ORDER BY id
                        LIMIT 1
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM "user" WHERE role = :admin_role
                    )
                    """
                ).bindparams(admin_role="ADMIN")
            )
            op.execute(
                sa.text(
                    """
                    UPDATE "user"
                    SET role = :owner_role
                    WHERE role = :admin_role
                    AND id <> (
                        SELECT id
                        FROM "user"
                        WHERE role = :admin_role
                        ORDER BY id
                        LIMIT 1
                    )
                    """
                ).bindparams(admin_role="ADMIN", owner_role="STORE_OWNER")
            )
            op.execute(
                sa.text(
                    """
                    UPDATE "user"
                    SET role = :owner_role
                    WHERE role IS NULL
                    """
                ).bindparams(owner_role="STORE_OWNER")
            )

    if _table_exists("invoice"):
        with op.batch_alter_table("invoice", schema=None) as batch_op:
            if not _column_exists("invoice", "store_id"):
                batch_op.add_column(sa.Column("store_id", sa.Integer(), nullable=True))
            if "fk_invoice_store_id" not in _fk_names("invoice"):
                batch_op.create_foreign_key(
                    "fk_invoice_store_id", "store", ["store_id"], ["id"]
                )

    if _table_exists("payout"):
        with op.batch_alter_table("payout", schema=None) as batch_op:
            if not _column_exists("payout", "store_id"):
                batch_op.add_column(sa.Column("store_id", sa.Integer(), nullable=True))
            if "fk_payout_store_id" not in _fk_names("payout"):
                batch_op.create_foreign_key(
                    "fk_payout_store_id", "store", ["store_id"], ["id"]
                )


def downgrade():
    if _table_exists("payout") and _column_exists("payout", "store_id"):
        with op.batch_alter_table("payout", schema=None) as batch_op:
            if "fk_payout_store_id" in _fk_names("payout"):
                batch_op.drop_constraint("fk_payout_store_id", type_="foreignkey")
            batch_op.drop_column("store_id")
    if _table_exists("invoice") and _column_exists("invoice", "store_id"):
        with op.batch_alter_table("invoice", schema=None) as batch_op:
            if "fk_invoice_store_id" in _fk_names("invoice"):
                batch_op.drop_constraint("fk_invoice_store_id", type_="foreignkey")
            batch_op.drop_column("store_id")
    if _table_exists("user") and _column_exists("user", "store_id"):
        with op.batch_alter_table("user", schema=None) as batch_op:
            if "fk_user_store_id" in _fk_names("user"):
                batch_op.drop_constraint("fk_user_store_id", type_="foreignkey")
            if _column_exists("user", "role"):
                batch_op.drop_column("role")
            batch_op.drop_column("store_id")
    if _table_exists("store_wallet"):
        op.drop_table("store_wallet")
    if _table_exists("store"):
        op.drop_table("store")
