"""Add isolated site telemetry and admin sessions; no catalog changes."""
from alembic import op
import sqlalchemy as sa

revision = "0006_site_analytics"
down_revision = "0005_price_obs_analytics_cover"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("analytics_visitors",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False))
    op.create_table("analytics_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("visitor_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("path", sa.String(128), nullable=False),
        sa.Column("country", sa.String(2), nullable=False))
    op.create_index("ix_analytics_events_time", "analytics_events", ["occurred_at"])
    op.create_table("analytics_days",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("views", sa.Integer(), nullable=False))
    op.create_table("admin_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_admin_sessions_expires_at", "admin_sessions", ["expires_at"])


def downgrade():
    op.drop_table("admin_sessions")
    op.drop_table("analytics_days")
    op.drop_table("analytics_events")
    op.drop_table("analytics_visitors")
