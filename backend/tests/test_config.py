from pathlib import Path

from app.config import PROJECT_ROOT, Settings


def test_env_file_is_resolved_from_project_root() -> None:
    env_file = Path(Settings.model_config["env_file"])
    assert env_file.is_absolute()
    assert env_file == PROJECT_ROOT / ".env"


def test_tcgapi_defaults_are_server_side_and_bounded() -> None:
    settings = Settings(_env_file=None)
    assert settings.ppt_daily_credit_limit == 20000
    assert settings.ppt_minute_weight_limit == 55
    assert settings.ebay_daily_request_limit == 500
    assert settings.price_collection_card_limit == 8
    assert settings.ebay_scheduled_request_limit == 450
    assert settings.passive_priority_card_count == 1500


def test_default_cors_origins_allow_both_local_loopback_names() -> None:
    settings = Settings(_env_file=None)
    assert settings.cors_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
