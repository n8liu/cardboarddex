from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = "sqlite:///./cardboarddex.db"
    redis_url: str = "redis://localhost:6379/0"
    cache_redis_url: str | None = None
    redis_socket_timeout: float = Field(default=2.0, gt=0, le=30)
    db_pool_size: int = Field(default=3, ge=1, le=10)
    db_max_overflow: int = Field(default=2, ge=0, le=10)
    api_thread_limit: int = Field(default=8, ge=1, le=40)
    postgres_host: str | None = None
    postgres_user: str = "cardboarddex"
    postgres_db: str = "cardboarddex"
    postgres_password: str | None = None

    @property
    def effective_database_url(self) -> str:
        if not self.postgres_host:
            return self.database_url
        if not self.postgres_password:
            raise ValueError("POSTGRES_PASSWORD is required when POSTGRES_HOST is set")
        from sqlalchemy.engine import URL
        return URL.create(
            "postgresql+psycopg", username=self.postgres_user,
            password=self.postgres_password, host=self.postgres_host,
            port=5432, database=self.postgres_db,
        ).render_as_string(hide_password=False)
    tcgapi_api_key: str | None = None
    tcgapi_base_url: str = "https://api.tcgapi.dev/v1"
    tcgapi_daily_request_limit: int = 2000
    tcgapi_sync_set_limit: int = 250
    ebay_client_id: str | None = None
    ebay_client_secret: str | None = None
    ebay_relay_url: str | None = None
    ebay_relay_key: str | None = None
    ebay_marketplace_id: str = "EBAY_US"
    ebay_daily_request_limit: int = 500
    price_collection_card_limit: int = 5
    backend_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
    psa_value_fee: float = 24.99
    image_cdn_enabled: bool = False
    image_cdn_base_url: str = Field(default="https://images.cardboarddex.app", pattern=r"^https://images\.cardboarddex\.app/?$")
    image_manifest_path: str = "/var/lib/cardboarddex/images/manifest.json"
    s3_bucket_name: str | None = None
    aws_region: str = "us-west-2"
    cloudfront_domain: str | None = None
    admin_api_key: str | None = None
    enable_api_docs: bool = False
    rate_limit_per_minute: int = 300
    rate_limit_track_action_per_minute: int = 30
    rate_limit_heavy_per_minute: int = 60

    @property
    def cors_origins(self) -> list[str]:
        origins: list[str] = []
        for raw in self.backend_cors_origins.split(","):
            cleaned = raw.strip().rstrip("/")
            if cleaned and cleaned not in origins:
                origins.append(cleaned)
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
