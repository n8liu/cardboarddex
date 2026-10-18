"""Online indexes for current provider pricing and Live Comps.

Adopts the identically named legacy index created during the production incident.
No catalog schema changes. SQLite test databases need no PostgreSQL tuning indexes.
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_ppt_query_indexes"
down_revision = "0009_pokemon_price_tracker"
branch_labels = None
depends_on = None

INDEXES = {
    "ix_price_observations_tcgapi_latest": "(card_id, provider_updated_at DESC NULLS LAST, observed_at DESC, id DESC) INCLUDE (price) WHERE provider = 'tcgapi' AND grading_company IS NULL",
    "ix_price_observations_ppt_primary": "(card_id, fingerprint) WHERE provider = 'pokemonpricetracker' AND grading_company IS NULL AND CAST(payload->>'primary' AS boolean) IS TRUE",
    "ix_price_observations_provider_feed": "(provider, COALESCE(observed_at, provider_updated_at) DESC, id DESC) INCLUDE (card_id, grading_company)",
}


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        for name, definition in INDEXES.items():
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON price_observations {definition}")
            valid = op.get_bind().execute(sa.text(
                "SELECT indisvalid AND indisready FROM pg_index WHERE indexrelid = to_regclass(:name)"
            ), {"name": name}).scalar()
            if not valid:
                raise RuntimeError(f"Index {name} is invalid; inspect the interrupted build before retrying")


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        # Preserve the legacy incident fix, which may predate this migration.
        for name in INDEXES:
            if name != "ix_price_observations_tcgapi_latest":
                op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
