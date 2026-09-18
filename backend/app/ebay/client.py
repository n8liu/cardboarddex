import base64
import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import httpx

from redis import Redis
from redis.exceptions import RedisError

from app.config import get_settings
from app.providers import DailyRequestLimiter

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.ebay.com"
DEFAULT_AUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
MAX_ATTEMPTS = 3
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
REDIS_TOKEN_KEY = "cardboarddex:ebay:oauth_access_token"


class EbayConfigurationError(RuntimeError):
    pass


class EbayClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        marketplace_id: str | None = None,
        base_url: str | None = None,
        auth_url: str | None = None,
        timeout: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        time_func: Callable[[], float] = time.time,
        acquire_request: Callable[[], None] | None = None,
        redis_client: Redis | None = None,
    ) -> None:
        settings = get_settings()
        self.client_id = (client_id if client_id is not None else settings.ebay_client_id or "").strip()
        self.client_secret = (client_secret if client_secret is not None else settings.ebay_client_secret or "").strip()
        self.marketplace_id = marketplace_id or settings.ebay_marketplace_id
        self._relay_headers: dict[str, str] = {}
        relay = settings.ebay_relay_url
        # Explicit endpoint overrides opt out of the relay as a pair, ensuring
        # its shared secret can never be sent to an overridden origin.
        if relay and base_url is None and auth_url is None:
            parsed = urlsplit(relay)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                    or parsed.password or parsed.path not in ("", "/")
                    or parsed.query or parsed.fragment or not settings.ebay_relay_key):
                raise EbayConfigurationError("eBay relay requires an HTTPS origin and EBAY_RELAY_KEY")
            self.base_url = relay.rstrip("/")
            self.auth_url = self.base_url + "/identity/v1/oauth2/token"
            self._relay_headers = {"X-CardboardDex-Proxy-Key": settings.ebay_relay_key}
        else:
            self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
            self.auth_url = auth_url or DEFAULT_AUTH_URL
        self.timeout = timeout
        self.sleep = sleep
        self.time_func = time_func
        self.acquire_request = acquire_request or DailyRequestLimiter(
            settings.redis_url, "ebay", settings.ebay_daily_request_limit
        ).acquire

        if redis_client is not None:
            self._redis = redis_client
        elif acquire_request is None and settings.redis_url:
            try:
                self._redis = Redis.from_url(
                    settings.redis_url, decode_responses=True,
                    socket_connect_timeout=settings.redis_socket_timeout,
                    socket_timeout=settings.redis_socket_timeout,
                )
            except Exception as exc:
                logger.warning("Could not initialize Redis client for eBay token sharing: %s: %s", type(exc).__name__, exc)
                self._redis = None
        else:
            self._redis = None

        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    def _get_auth_header(self) -> str:
        if not self.client_id or not self.client_secret:
            error = EbayConfigurationError("EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are required")
            logger.error("eBay configuration error error=%s: %s", type(error).__name__, error)
            raise error
        raw_auth = f"{self.client_id}:{self.client_secret}"
        return base64.b64encode(raw_auth.encode()).decode()

    def get_access_token(self) -> str:
        """Obtain or return cached valid OAuth 2.0 application access token."""
        now = self.time_func()
        # 1. Check in-memory token first if valid for at least 5 minutes
        if self._access_token and now < (self._token_expires_at - 300):
            return self._access_token

        # 2. Check shared Redis cache
        if self._redis is not None:
            try:
                cached_token = self._redis.get(REDIS_TOKEN_KEY)
                if cached_token:
                    self._access_token = cached_token
                    # Estimate expiration based on Redis TTL
                    ttl = self._redis.ttl(REDIS_TOKEN_KEY)
                    self._token_expires_at = now + (ttl if ttl > 0 else 3600)
                    return cached_token
            except RedisError as exc:
                logger.warning(
                    "Redis error fetching shared eBay OAuth token error=%s: %s",
                    type(exc).__name__,
                    exc,
                )

        headers = {
            **self._relay_headers,
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {self._get_auth_header()}",
        }
        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        }

        logger.info("Requesting fresh eBay OAuth 2.0 application access token")
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = httpx.post(
                    self.auth_url,
                    headers=headers,
                    data=data,
                    timeout=httpx.Timeout(connect=5.0, read=25.0, write=10.0, pool=5.0),
                )
                response.raise_for_status()
                payload = response.json()
                token = payload.get("access_token")
                expires_in = int(payload.get("expires_in", 7200))
                if not token:
                    error = ValueError("eBay OAuth response missing access_token")
                    logger.error("eBay OAuth error: missing access_token in payload=%s", payload)
                    raise error
                self._access_token = token
                self._token_expires_at = now + expires_in

                # Store token in shared Redis cache
                if self._redis is not None:
                    try:
                        redis_ttl = max(60, expires_in - 300)
                        self._redis.set(REDIS_TOKEN_KEY, token, ex=redis_ttl)
                    except RedisError as exc:
                        logger.warning(
                            "Failed to store eBay OAuth token in Redis error=%s: %s",
                            type(exc).__name__,
                            exc,
                        )

                return token
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                logger.error(
                    "eBay OAuth HTTP error url=%s status=%s attempt=%s/%s error=%s: %s body=%s",
                    self.auth_url,
                    status,
                    attempt,
                    MAX_ATTEMPTS,
                    type(exc).__name__,
                    exc,
                    exc.response.text[:500],
                )
                if status not in RETRYABLE_STATUSES or attempt == MAX_ATTEMPTS:
                    raise
            except httpx.RequestError as exc:
                logger.error(
                    "eBay OAuth network request failed url=%s attempt=%s/%s error=%s: %s",
                    self.auth_url,
                    attempt,
                    MAX_ATTEMPTS,
                    type(exc).__name__,
                    exc,
                )
                if attempt == MAX_ATTEMPTS:
                    raise
            self.sleep(2 ** (attempt - 1))
        raise RuntimeError("eBay OAuth token request exhausted retry attempts")

    def search_item_summaries(
        self,
        query: str,
        limit: int = 50,
        category_ids: str | None = None,
        filter_exp: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search eBay Browse API item summaries.
        Endpoint: GET /buy/browse/v1/item_summary/search
        """
        token = self.get_access_token()
        path = "/buy/browse/v1/item_summary/search"
        url = f"{self.base_url}{path}"
        headers = {
            **self._relay_headers,
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
            "Accept": "application/json",
        }
        params: dict[str, Any] = {"q": query, "limit": min(limit, 50)}
        if category_ids:
            params["category_ids"] = category_ids
        if filter_exp:
            params["filter"] = filter_exp

        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.acquire_request()
            try:
                response = httpx.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=httpx.Timeout(connect=5.0, read=25.0, write=10.0, pool=5.0),
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    error = TypeError(f"eBay search response must be a JSON object, got {type(payload).__name__}")
                    logger.error("eBay search invalid payload url=%s error=%s: %s", url, type(error).__name__, error)
                    raise error
                items = payload.get("itemSummaries") or []
                if not isinstance(items, list):
                    return []
                return [item for item in items if isinstance(item, dict)]
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                logger.error(
                    "eBay Browse API HTTP error path=%s params=%s status=%s attempt=%s/%s error=%s: %s body=%s",
                    path,
                    params,
                    status,
                    attempt,
                    MAX_ATTEMPTS,
                    type(exc).__name__,
                    exc,
                    exc.response.text[:500],
                )
                if status not in RETRYABLE_STATUSES or attempt == MAX_ATTEMPTS:
                    raise
            except httpx.RequestError as exc:
                logger.error(
                    "eBay Browse API request failed path=%s params=%s attempt=%s/%s error=%s: %s",
                    path,
                    params,
                    attempt,
                    MAX_ATTEMPTS,
                    type(exc).__name__,
                    exc,
                )
                if attempt == MAX_ATTEMPTS:
                    raise
            self.sleep(2 ** (attempt - 1))
        raise RuntimeError("eBay Browse search exhausted retry attempts")
