"""Preserve graph history across provider cutover; no catalog changes."""
from alembic import op
import sqlalchemy as sa
revision = "0012_market_history_transitions"
down_revision = "0011_catalog_prices"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("market_history_transitions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("card_id", sa.String(64), sa.ForeignKey("cards.id"), nullable=False),
        sa.Column("product_id", sa.String(160), sa.ForeignKey("ppt_products.id"), nullable=False),
        sa.Column("dimensions", sa.JSON(), nullable=False),
        sa.Column("cutover_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_market_history_transitions_card_id", "market_history_transitions", ["card_id"])


def downgrade():
    # Empty development databases can be rolled back; recorded cutovers cannot.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM market_history_transitions")):
        raise RuntimeError("Roll back application code, not preserved history transitions")
    op.drop_table("market_history_transitions")
