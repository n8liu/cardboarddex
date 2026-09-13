from collections.abc import Generator
from datetime import date
import pytest
from starlette.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.database import Base, get_db
from app.main import app, is_allowed_origin
from app.models import Card, PriceObservation, Set
from app.routers.cards import _extract_listing_url
from app.common.rate_limiter import check_rate_limit, _check_in_memory_rate_limit


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Set(id="1", name="Base Set", series="Original", release_date=date(1999, 1, 9)))
        session.add(Card(id="pikachu-1", name="Pikachu", set_id="1", number="58", image_url="https://test/img.png"))
        session.commit()

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def test_cors_origin_validation() -> None:
    """Verify that only legitimate domains are permitted, blocking substring tricks."""
    # Legitimate origins
    assert is_allowed_origin("https://cardboarddex.pages.dev") is True
    assert is_allowed_origin("https://cardboarddex.app") is True
    assert is_allowed_origin("https://www.cardboarddex.app") is True
    assert is_allowed_origin("https://cardboarddex.com") is True
    assert is_allowed_origin("https://www.cardboarddex.com") is True
    assert is_allowed_origin("http://localhost:3000") is True
    assert is_allowed_origin("http://127.0.0.1:3000") is True

    # Malicious origins attempting substring or spoofing
    assert is_allowed_origin("https://attacker-pages.dev") is False
    assert is_allowed_origin("https://malicious.com/?pages.dev") is False
    assert is_allowed_origin("https://evilcardboarddex.com") is False
    assert is_allowed_origin("https://cardboarddex.com.attacker.com") is False
    assert is_allowed_origin("https://evilcardboarddex.app") is False
    assert is_allowed_origin("https://cardboarddex.app.attacker.com") is False
    assert is_allowed_origin("https://random-app.pages.dev") is False
    assert is_allowed_origin(None) is False
    assert is_allowed_origin("") is False


def test_extract_listing_url_sanitization() -> None:
    """Verify that malicious protocols (javascript:, data:, file:) and untrusted domains are stripped."""
    # 1. Valid eBay URL
    valid_ebay = PriceObservation(
        provider="ebay",
        provider_card_id="v1|123456789|0",
        payload={"itemWebUrl": "https://www.ebay.com/itm/123456789"},
    )
    assert _extract_listing_url(valid_ebay) == "https://www.ebay.com/itm/123456789"

    # 2. Valid TCGPlayer URL
    valid_tcg = PriceObservation(
        provider="tcgapi",
        provider_card_id="tcg-1",
        payload={"item_url": "https://tcgplayer.com/product/12345"},
    )
    assert _extract_listing_url(valid_tcg) == "https://tcgplayer.com/product/12345"

    # 3. JavaScript injection attempt
    xss_obs = PriceObservation(
        provider="ebay",
        provider_card_id="bad-1",
        payload={"itemWebUrl": "javascript:alert(document.cookie)"},
    )
    assert _extract_listing_url(xss_obs) is None

    # 4. Data URI injection attempt
    data_obs = PriceObservation(
        provider="ebay",
        provider_card_id="bad-2",
        payload={"itemWebUrl": "data:text/html,<script>alert(1)</script>"},
    )
    assert _extract_listing_url(data_obs) is None

    # 5. Untrusted phishing domain
    phish_obs = PriceObservation(
        provider="ebay",
        provider_card_id="bad-3",
        payload={"itemWebUrl": "https://phishing-scam.com/steal-login"},
    )
    assert _extract_listing_url(phish_obs) is None


def test_card_id_path_traversal_prevention(client: TestClient) -> None:
    """Verify that path traversal characters in /cards/{card_id}/image return 400 Bad Request."""
    # Traversal strings
    res = client.get("/cards/..%2F..%2Fetc%2Fpasswd/image")
    assert res.status_code in (400, 404)

    res2 = client.get("/cards/../../image")
    assert res2.status_code in (400, 404)

    # Oversized card ID (>64 chars)
    res3 = client.get(f"/cards/{'a' * 100}/image")
    assert res3.status_code == 400
    assert "Invalid card ID format" in res3.json()["detail"]


def test_live_updates_query_length_validation(client: TestClient) -> None:
    """Verify that oversized search queries (>100 chars) are rejected with 422."""
    res = client.get(f"/cards/live-updates?q={'a' * 150}")
    assert res.status_code == 422


def test_track_action_schema_validation(client: TestClient) -> None:
    """Verify that track-action enforces entity_id length and character constraints."""
    # Valid payload
    valid_res = client.post(
        "/cards/track-action",
        json={"entity_type": "search", "entity_id": "charizard base set", "action": "search"},
    )
    assert valid_res.status_code == 200

    # Oversized entity_id (>100 chars)
    oversized_res = client.post(
        "/cards/track-action",
        json={"entity_type": "search", "entity_id": "a" * 150, "action": "search"},
    )
    assert oversized_res.status_code == 422

    # Malicious script characters in entity_id
    bad_chars_res = client.post(
        "/cards/track-action",
        json={"entity_type": "card", "entity_id": "<script>alert(1)</script>", "action": "click"},
    )
    assert bad_chars_res.status_code == 422


def test_admin_trending_reset_auth(client: TestClient) -> None:
    """Verify that POST /cards/trending/reset requires a valid X-Admin-Token."""
    settings = get_settings()
    original_key = settings.admin_api_key

    try:
        # Case 1: Unconfigured admin key -> 403 Forbidden
        settings.admin_api_key = None
        res_unconfigured = client.post("/cards/trending/reset")
        assert res_unconfigured.status_code == 403

        # Case 2: Configured admin key, missing token -> 401 Unauthorized
        settings.admin_api_key = "secure-super-token-123"
        res_missing = client.post("/cards/trending/reset")
        assert res_missing.status_code == 401

        # Case 3: Configured admin key, wrong token -> 401 Unauthorized
        res_wrong = client.post(
            "/cards/trending/reset",
            headers={"X-Admin-Token": "wrong-token"},
        )
        assert res_wrong.status_code == 401

        # Case 4: Correct token -> 200 OK
        res_ok = client.post(
            "/cards/trending/reset",
            headers={"X-Admin-Token": "secure-super-token-123"},
        )
        assert res_ok.status_code == 200
        assert res_ok.json()["status"] == "ok"
    finally:
        settings.admin_api_key = original_key


def test_rate_limiter_in_memory_sliding_window() -> None:
    """Verify that in-memory rate limiter correctly throttles when limit is exceeded."""
    key = "test-rate-limit-key"
    max_req = 5
    window = 10

    # First 5 calls pass
    for _ in range(max_req):
        assert _check_in_memory_rate_limit(key, max_requests=max_req, window_seconds=window) is True

    # 6th call exceeds limit
    assert _check_in_memory_rate_limit(key, max_requests=max_req, window_seconds=window) is False


def test_response_security_and_cache_headers(client: TestClient) -> None:
    """Verify that responses contain comprehensive security headers and Cache-Control headers."""
    res = client.get("/health")
    assert res.status_code == 200

    # Security Headers
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "Strict-Transport-Security" in res.headers
    assert "Content-Security-Policy" in res.headers

    # Cache-Control headers on read endpoints
    sets_res = client.get("/cards/sets")
    assert sets_res.status_code == 200
    assert "Cache-Control" in sets_res.headers
    assert "public" in sets_res.headers["Cache-Control"]

    live_res = client.get("/cards/live-updates")
    assert live_res.status_code == 200
    assert "Cache-Control" in live_res.headers
    assert "max-age=5" in live_res.headers["Cache-Control"]


def test_error_response_sanitization(client: TestClient) -> None:
    """Verify that 500 error responses do not leak internal exception class names."""
    from unittest.mock import patch

    with patch("app.routers.cards.get_set_statistics", side_effect=ValueError("Secret DB column failure")):
        res = client.get("/cards/sets/1/stats")
        assert res.status_code == 500
        # Detail must be sanitized
        assert res.json()["detail"] == "An internal server error occurred. Please try again later."
        assert "ValueError" not in res.json()["detail"]
        assert "Secret DB" not in res.json()["detail"]
