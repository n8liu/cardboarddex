"""Add provider history and catalog snapshots without changing Cards or Sets."""
from alembic import op
import sqlalchemy as sa

revision = "0007_market_data"
down_revision = "0006_site_analytics"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("market_history",
        sa.Column("card_id", sa.String(64), sa.ForeignKey("cards.id"), primary_key=True),
        sa.Column("printing", sa.String(128), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("market_price", sa.Numeric(12, 2)),
        sa.Column("avg_sales_price", sa.Numeric(12, 2)),
        sa.Column("sales_volume", sa.Integer()),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_market_history_day", "market_history", ["day"])
    op.create_table("catalog_snapshots",
        sa.Column("game", sa.String(64), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("catalog_snapshots")
    op.drop_index("ix_market_history_day", table_name="market_history")
    op.drop_table("market_history")
