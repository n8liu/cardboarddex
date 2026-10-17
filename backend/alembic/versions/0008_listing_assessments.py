"""Add versioned listing identity assessments without changing catalog tables."""
from alembic import op
import sqlalchemy as sa
revision = "0008_listing_assessments"
down_revision = "0007_market_data"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("listing_assessments",
        sa.Column("fingerprint", sa.String(64), primary_key=True),
        sa.Column("card_id", sa.String(64), sa.ForeignKey("cards.id"), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("text_status", sa.String(24), nullable=False),
        sa.Column("image_status", sa.String(24), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("checked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_listing_assessments_card_id", "listing_assessments", ["card_id"])
    op.create_index("ix_listing_assessments_item_id", "listing_assessments", ["item_id"])
    op.create_index("ix_listing_assessments_pending", "listing_assessments", ["status", "checked_at"])


def downgrade():
    op.drop_table("listing_assessments")
