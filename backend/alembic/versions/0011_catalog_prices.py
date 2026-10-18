"""Add rebuildable catalog price candidates; never alter Cards or Sets."""
from alembic import op
import sqlalchemy as sa

revision = "0011_catalog_prices"
down_revision = "0010_ppt_query_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("catalog_price_candidates",
        sa.Column("card_id", sa.String(64), sa.ForeignKey("cards.id"), primary_key=True),
        sa.Column("provider", sa.String(32), primary_key=True),
        sa.Column("observation_id", sa.Integer(), primary_key=True, unique=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("condition", sa.String(64)), sa.Column("printing", sa.String(64)),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ppt_price_date", sa.Date()))
    op.create_index("uq_catalog_price_tcgapi", "catalog_price_candidates", ["card_id"], unique=True,
        postgresql_where=sa.text("provider = 'tcgapi'"), sqlite_where=sa.text("provider = 'tcgapi'"))
    op.create_index("ix_catalog_price_lookup", "catalog_price_candidates",
        ["card_id", "provider", "provider_updated_at", "observed_at", "observation_id"])
    op.create_table("catalog_price_projection_state",
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("after_card_id", sa.String(64)),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)))
    op.execute(sa.text("INSERT INTO catalog_price_projection_state(version, complete) VALUES (1, false)"))


def downgrade():
    op.drop_table("catalog_price_projection_state")
    op.drop_table("catalog_price_candidates")
