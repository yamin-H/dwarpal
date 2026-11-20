"""tenant controls, key expiry, cost tracking (adds only columns that are missing)"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _add(table: str, column: sa.Column) -> None:
    present = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    if column.name not in present:
        op.add_column(table, column)


def upgrade() -> None:
    _add("tenants", sa.Column("cache_enabled", sa.Boolean(), nullable=False,
                              server_default=sa.true()))
    _add("tenants", sa.Column("allow_fallback", sa.Boolean(), nullable=False,
                              server_default=sa.true()))
    _add("tenants", sa.Column("semantic_threshold", sa.Float(), nullable=True))
    _add("tenants", sa.Column("monthly_token_budget", sa.BigInteger(), nullable=True))
    _add("tenants", sa.Column("monthly_cost_budget_micros", sa.BigInteger(), nullable=True))
    _add("api_keys", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    _add("usage", sa.Column("cost_micros", sa.BigInteger(), nullable=False,
                            server_default=sa.text("0")))
    _add("usage", sa.Column("served_model", sa.String(length=100), nullable=True))


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")