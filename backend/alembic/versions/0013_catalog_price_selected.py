"""Mark each card's selected catalog price so price sorts use an index; never alter Cards or Sets."""
from alembic import op
import sqlalchemy as sa

revision = "0013_catalog_price_selected"
down_revision = "0012_market_history_transitions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("catalog_price_candidates",
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    # Same order as candidate_join: primary PPT first, then newest. Releases stop
    # the worker before migrating, so no candidate writes race this backfill.
    op.execute(sa.text("""
        UPDATE catalog_price_candidates SET selected = true WHERE observation_id IN (
            SELECT observation_id FROM (
                SELECT observation_id, row_number() OVER (PARTITION BY card_id ORDER BY
                    CASE WHEN provider = 'pokemonpricetracker' THEN 0 ELSE 1 END,
                    provider_updated_at DESC NULLS LAST, observed_at DESC, observation_id DESC) AS position
                FROM catalog_price_candidates) ranked
            WHERE position = 1)"""))
    op.create_index("ix_catalog_price_selected", "catalog_price_candidates", ["price"],
        postgresql_where=sa.text("selected"), sqlite_where=sa.text("selected"))


def downgrade():
    op.drop_index("ix_catalog_price_selected", "catalog_price_candidates")
    op.drop_column("catalog_price_candidates", "selected")
