"""Cover dashboard aggregates without reading large observation payloads."""
from alembic import op

revision = "0005_price_obs_analytics_cover"
down_revision = "0004_price_obs_search_index"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        if op.get_bind().dialect.name == "postgresql":
            # The API's short query deadline must not interrupt an online build.
            op.execute("SET statement_timeout = '5min'")
        op.create_index(
            "ix_price_observations_analytics_cover", "price_observations", ["card_id"],
            postgresql_include=[
                "id", "price", "provider", "grading_company", "observed_at", "provider_updated_at",
            ],
            postgresql_concurrently=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_price_observations_analytics_cover", table_name="price_observations",
            postgresql_concurrently=True,
        )
