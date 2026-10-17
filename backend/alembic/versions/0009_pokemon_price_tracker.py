"""Add isolated Pokémon Price Tracker mapping, snapshots and monthly history.

Revision ID: 0009_pokemon_price_tracker
Revises: 0008_listing_assessments
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_pokemon_price_tracker"
down_revision = "0008_listing_assessments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("ppt_products",
        sa.Column("id", sa.String(160), primary_key=True),
        sa.Column("provider_id", sa.String(128), nullable=False),
        sa.Column("card_id", sa.String(64), sa.ForeignKey("cards.id")),
        sa.Column("segment", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("match_method", sa.String(64)),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.Column("quotes", sa.JSON(), nullable=False),
        sa.Column("primary_price", sa.Numeric(12, 2)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("retry_at", sa.DateTime(timezone=True)),
        sa.Column("failures", sa.Integer(), nullable=False))
    op.create_index("ix_ppt_products_card_id", "ppt_products", ["card_id"])
    op.create_index("ix_ppt_products_due", "ppt_products", ["status", "segment", "last_success_at"])
    op.create_table("ppt_current_quotes",
        sa.Column("fingerprint", sa.String(64), primary_key=True),
        sa.Column("product_id", sa.String(160), sa.ForeignKey("ppt_products.id"), nullable=False),
        sa.Column("price_date", sa.Date(), nullable=False))
    op.create_index("ix_ppt_current_quotes_product_id", "ppt_current_quotes", ["product_id"])
    op.create_table("ppt_history",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("product_id", sa.String(160), sa.ForeignKey("ppt_products.id"), nullable=False),
        sa.Column("card_id", sa.String(64), sa.ForeignKey("cards.id"), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("dimensions", sa.JSON(), nullable=False),
        sa.Column("points", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_ppt_history_card_month", "ppt_history", ["card_id", "month"])
    op.create_table("ppt_checkpoints", sa.Column("key", sa.String(160), primary_key=True),
                    sa.Column("payload", sa.JSON(), nullable=False))


def downgrade():
    op.drop_table("ppt_current_quotes")
    op.drop_table("ppt_history")
    op.drop_table("ppt_products")
    op.drop_table("ppt_checkpoints")
