"""Opt-in smoke tests for the deployed Cloudflare and AWS API endpoints."""

from collections.abc import Generator
import os

import httpx
import pytest


CLOUDFLARE_API_URL = os.getenv(
    "CLOUDFLARE_API_URL",
    "https://api.cardboarddex.app",
).rstrip("/")
AWS_BACKEND_URL = os.getenv("AWS_BACKEND_URL", "").rstrip("/")
RUN_LIVE_TESTS = os.getenv("RUN_LIVE_DEPLOYMENT_TESTS") == "1"
REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not RUN_LIVE_TESTS,
        reason="set RUN_LIVE_DEPLOYMENT_TESTS=1 to call deployed services",
    ),
]


def _client(base_url: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        follow_redirects=False,
        headers={"User-Agent": "CardboardDex deployment smoke tests"},
        timeout=REQUEST_TIMEOUT,
    )


@pytest.fixture
def cloudflare_client() -> Generator[httpx.Client, None, None]:
    with _client(CLOUDFLARE_API_URL) as client:
        yield client


@pytest.fixture
def aws_client() -> Generator[httpx.Client, None, None]:
    if not AWS_BACKEND_URL:
        pytest.skip("set AWS_BACKEND_URL while the direct AWS endpoint is available")
    with _client(AWS_BACKEND_URL) as client:
        yield client


def _assert_healthy(response: httpx.Response) -> None:
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}


def _search_first_card(client: httpx.Client) -> dict[str, object]:
    response = client.get(
        "/cards/search",
        params={"q": "pikachu", "limit": 1, "hide_sealed": "true"},
    )
    assert response.status_code == 200, response.text
    cards = response.json()
    assert isinstance(cards, list)
    assert cards, "expected the production catalog to contain Pikachu"
    first_card = cards[0]
    assert isinstance(first_card, dict)
    assert isinstance(first_card.get("id"), str)
    assert "pikachu" in str(first_card.get("name", "")).lower()
    return first_card


def test_cloudflare_tunnel_health(cloudflare_client: httpx.Client) -> None:
    response = cloudflare_client.get("/health")

    _assert_healthy(response)
    assert response.headers.get("cf-ray"), "response did not pass through Cloudflare"


def test_cloudflare_tunnel_catalog_search(cloudflare_client: httpx.Client) -> None:
    _search_first_card(cloudflare_client)


def test_cloudflare_tunnel_allows_production_cors(
    cloudflare_client: httpx.Client,
) -> None:
    response = cloudflare_client.options(
        "/cards/search",
        headers={
            "Origin": "https://cardboarddex.app",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code in {200, 204}, response.text
    assert response.headers.get("access-control-allow-origin") == "https://cardboarddex.app"
    allowed_methods = response.headers.get("access-control-allow-methods", "")
    assert "GET" in allowed_methods


def test_direct_aws_backend_health(aws_client: httpx.Client) -> None:
    _assert_healthy(aws_client.get("/health"))


def test_cloudflare_and_aws_return_the_same_catalog_card(
    cloudflare_client: httpx.Client,
    aws_client: httpx.Client,
) -> None:
    cloudflare_card = _search_first_card(cloudflare_client)
    aws_card = _search_first_card(aws_client)

    assert cloudflare_card["id"] == aws_card["id"]
    assert cloudflare_card["name"] == aws_card["name"]
