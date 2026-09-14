from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = "sqlite:///./cardboarddex.db"
    redis_url: str = "redis://localhost:6379/0"
    tcgapi_api_key: str | None = None
    tcgapi_base_url: str = "https://api.tcgapi.dev/v1"
    tcgapi_daily_request_limit: int = 2000
    tcgapi_sync_set_limit: int = 250
    ebay_client_id: str | None = None
    ebay_client_secret: str | None = None
    ebay_marketplace_id: str = "EBAY_US"
    ebay_daily_request_limit: int = 500
    price_collection_card_limit: int = 5
    backend_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
    psa_value_fee: float = 24.99
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
