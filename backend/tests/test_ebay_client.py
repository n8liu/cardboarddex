import httpx
import pytest
import respx

from app.ebay.client import EbayClient, EbayConfigurationError


@pytest.fixture
def dummy_client() -> EbayClient:
    return EbayClient(
        client_id="test_client_id",
        client_secret="test_client_secret",
        marketplace_id="EBAY_US",
        base_url="https://api.ebay.com",
        auth_url="https://api.ebay.com/identity/v1/oauth2/token",
        sleep=lambda _: None,
        acquire_request=lambda: None,
    )


def test_missing_credentials_raises_configuration_error() -> None:
    client = EbayClient(client_id="", client_secret="", acquire_request=lambda: None)
    with pytest.raises(EbayConfigurationError, match="EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are required"):
        client.get_access_token()


@respx.mock
def test_oauth_token_is_cached_and_reused(dummy_client: EbayClient) -> None:
    auth_route = respx.post("https://api.ebay.com/identity/v1/oauth2/token").respond(
        200,
        json={"access_token": "mock_token_123", "expires_in": 7200, "token_type": "Application Access Token"},
    )

    token1 = dummy_client.get_access_token()
    token2 = dummy_client.get_access_token()

    assert token1 == "mock_token_123"
    assert token2 == "mock_token_123"
    assert auth_route.call_count == 1


@respx.mock
def test_search_item_summaries_uses_bearer_and_marketplace_headers(dummy_client: EbayClient) -> None:
    respx.post("https://api.ebay.com/identity/v1/oauth2/token").respond(
        200,
        json={"access_token": "mock_token_abc", "expires_in": 7200},
    )
    search_route = respx.get("https://api.ebay.com/buy/browse/v1/item_summary/search").respond(
        200,
        json={
            "total": 1,
            "itemSummaries": [
                {
                    "itemId": "v1|12345|0",
                    "title": "Charizard Base Set 4/102 Holo PSA 10",
                    "price": {"value": "350.00", "currency": "USD"},
                    "itemWebUrl": "https://www.ebay.com/itm/12345",
                }
            ],
        },
    )

    items = dummy_client.search_item_summaries("Charizard Base Set 4", limit=10)
    assert len(items) == 1
    assert items[0]["title"] == "Charizard Base Set 4/102 Holo PSA 10"

    request = search_route.calls[0].request
    assert request.headers["Authorization"] == "Bearer mock_token_abc"
    assert request.headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_US"
    assert request.url.params["q"] == "Charizard Base Set 4"
    assert request.url.params["limit"] == "10"


@respx.mock
def test_search_retries_on_rate_limit_and_server_error(dummy_client: EbayClient) -> None:
    respx.post("https://api.ebay.com/identity/v1/oauth2/token").respond(
        200,
        json={"access_token": "mock_token_abc", "expires_in": 7200},
    )
    search_route = respx.get("https://api.ebay.com/buy/browse/v1/item_summary/search")
    search_route.side_effect = [
        httpx.Response(429, json={"error": "Rate limit exceeded"}),
        httpx.Response(200, json={"itemSummaries": [{"itemId": "v1|1|0", "title": "Card Title"}]}),
    ]

    items = dummy_client.search_item_summaries("Pikachu")
    assert len(items) == 1
    assert search_route.call_count == 2


@respx.mock
def test_redis_token_sharing_reuses_redis_cached_token() -> None:
    fake_redis_store: dict[str, str] = {"cardboarddex:ebay:oauth_access_token": "redis_cached_token_999"}

    class FakeRedis:
        def get(self, key: str) -> str | None:
            return fake_redis_store.get(key)

        def set(self, key: str, value: str, ex: int | None = None) -> bool:
            fake_redis_store[key] = value
            return True

        def ttl(self, key: str) -> int:
            return 3600

    client = EbayClient(
        client_id="test_client_id",
        client_secret="test_client_secret",
        redis_client=FakeRedis(),  # type: ignore[arg-type]
        acquire_request=lambda: None,
    )

    # Token should be loaded directly from Redis without making any HTTP call
    token = client.get_access_token()
    assert token == "redis_cached_token_999"
