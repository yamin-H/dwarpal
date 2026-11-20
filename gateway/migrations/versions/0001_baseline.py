"""baseline: tenants, api_keys, usage (skips tables that already exist)"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "tenants" not in existing:
        op.create_table(
            "tenants",
            sa.Column("id", sa.String(length=40), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("allowed_models", sa.JSON(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if "api_keys" not in existing:
        op.create_table(
            "api_keys",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("tenant_id", sa.String(length=40), nullable=False),
            sa.Column("key_hash", sa.String(length=64), nullable=False),
            sa.Column("prefix", sa.String(length=16), nullable=False),
            sa.Column("revoked", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_api_keys_tenant_id"), "api_keys", ["tenant_id"], unique=False)
        op.create_index(op.f("ix_api_keys_key_hash"), "api_keys", ["key_hash"], unique=True)
    if "usage" not in existing:
        op.create_table(
            "usage",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.String(length=40), nullable=False),
            sa.Column("model", sa.String(length=100), nullable=False),
            sa.Column("provider", sa.String(length=100), nullable=False),
            sa.Column("stream", sa.Boolean(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("prompt_tokens", sa.Integer(), nullable=False),
            sa.Column("completion_tokens", sa.Integer(), nullable=False),
            sa.Column("latency_ms", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_usage_tenant_id"), "usage", ["tenant_id"], unique=False)
        op.create_index(op.f("ix_usage_created_at"), "usage", ["created_at"], unique=False)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")