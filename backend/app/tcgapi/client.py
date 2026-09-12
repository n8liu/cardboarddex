import hashlib
import logging
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.providers import DailyRequestLimiter

logger = logging.getLogger(__name__)
DEFAULT_BASE_URL = "https://api.tcgapi.dev/v1"
PAGE_SIZE = 100
MAX_ATTEMPTS = 4
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class TCGAPIConfigurationError(RuntimeError):
    pass


def local_card_id(source_id: object) -> str:
    value = str(source_id)
    if len(value) <= 64:
        return value
    return hashlib.sha256(f"tcgapi:{value}".encode()).hexdigest()


def parse_release_date(value: object) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError as exc:
        logger.warning(
            "TCG API release date invalid value=%s error=%s: %s",
            value,
            type(exc).__name__,
            exc,
        )
        return None


def split_card_number(value: object, printed_total: int | None) -> tuple[str, int | None]:
    number = str(value or "").strip()
    if "/" not in number:
        return number, printed_total
    printed, denominator = number.split("/", 1)
    try:
        return printed.strip(), int(denominator)
    except ValueError as exc:
        logger.warning(
            "TCG API card number denominator invalid value=%s error=%s: %s",
            value,
            type(exc).__name__,
            exc,
        )
        return number, printed_total


class TCGAPIClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        acquire_request: Callable[[], None] | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.tcgapi_api_key
        self.base_url = (base_url or settings.tcgapi_base_url).rstrip("/")
        self.timeout = timeout
        self.sleep = sleep
        self.acquire_request = acquire_request or DailyRequestLimiter(
            settings.redis_url, "tcgapi", settings.tcgapi_daily_request_limit
        ).acquire

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            error = TCGAPIConfigurationError("TCGAPI_API_KEY is required")
            logger.error("TCG API configuration error error=%s: %s", type(error).__name__, error)
            raise error
        return {"Accept": "application/json", "X-API-Key": self.api_key}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_params = params or {}
        url = f"{self.base_url}{path}"
        headers = self._headers()
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.acquire_request()
            try:
                response = httpx.get(
                    url,
                    headers=headers,
                    params=request_params,
                    timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
                )
                response.raise_for_status()
                try:
                    payload = response.json()
                except ValueError as exc:
                    logger.error(
                        "TCG API invalid JSON path=%s params=%s status=%s error=%s: %s body=%s",
                        path,
                        request_params,
                        response.status_code,
                        type(exc).__name__,
                        exc,
                        response.text[:500],
                    )
                    raise
                if not isinstance(payload, dict):
                    error = TypeError(
                        f"TCG API response must be an object, received {type(payload).__name__}"
                    )
                    logger.error(
                        "TCG API invalid payload path=%s params=%s status=%s error=%s: %s",
                        path,
                        request_params,
                        response.status_code,
                        type(error).__name__,
                        error,
                    )
                    raise error
                return payload
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                logger.error(
                    "TCG API HTTP error path=%s params=%s status=%s attempt=%s/%s "
                    "error=%s: %s body=%s",
                    path,
                    request_params,
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
                    "TCG API request failed path=%s params=%s attempt=%s/%s error=%s: %s",
                    path,
                    request_params,
                    attempt,
                    MAX_ATTEMPTS,
                    type(exc).__name__,
                    exc,
                )
                if attempt == MAX_ATTEMPTS:
                    raise
            self.sleep(2 ** (attempt - 1))
        raise RuntimeError("TCG API request exhausted attempts")

    def iter_sets(self, game: str = "pokemon") -> Iterator[dict[str, Any]]:
        page = 1
        while True:
            payload = self._get(
                "/sets", {"game": game, "page": page, "per_page": PAGE_SIZE}
            )
            data = payload.get("data") or []
            if not isinstance(data, list):
                error = TypeError("TCG API /sets response field 'data' must be a list")
                logger.error(
                    "TCG API invalid sets payload path=/sets page=%s game=%s error=%s: %s",
                    page,
                    game,
                    type(error).__name__,
                    error,
                )
                raise error
            yield from (item for item in data if isinstance(item, dict))
            meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
            if not meta.get("has_more", len(data) == PAGE_SIZE):
                return
            page += 1

    def iter_cards(self, set_ids: Iterable[str]) -> Iterator[dict[str, Any]]:
        for set_id in set_ids:
            page = 1
            while True:
                path = f"/sets/{quote(str(set_id), safe='')}/cards"
                payload = self._get(path, {"page": page, "per_page": PAGE_SIZE})
                data = payload.get("data") or []
                if not isinstance(data, list):
                    error = TypeError(
                        f"TCG API set cards must be a list for set_id={set_id}"
                    )
                    logger.error(
                        "TCG API invalid cards payload path=%s page=%s error=%s: %s",
                        path,
                        page,
                        type(error).__name__,
                        error,
                    )
                    raise error
                for card in data:
                    if isinstance(card, dict):
                        yield {**card, "_set_id": str(set_id)}
                meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
                if not meta.get("has_more", len(data) == PAGE_SIZE):
                    break
                page += 1

    def get_card(self, card_id: str) -> dict[str, Any]:
        return self._get(f"/cards/{quote(card_id, safe='')}")

    def get_card_prices(self, card_id: str, printing: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if printing:
            params["printing"] = printing
        return self._get(f"/cards/{quote(card_id, safe='')}/prices", params=params or None)

    def get_top_movers(
        self,
        game: str = "pokemon",
        direction: str = "up",
        period: str = "24h",
        printing: str | None = None,
        type: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "game": game,
            "direction": direction,
            "period": period,
            "limit": limit,
        }
        if printing:
            params["printing"] = printing
        if type:
            params["type"] = type
        return self._get("/prices/top-movers", params=params)

    def get_bulk_prices(self, card_ids: Iterable[str | int]) -> dict[str, Any]:
        ids_str = ",".join(str(card_id) for card_id in card_ids)
        return self._get("/bulk/prices", params={"ids": ids_str})

    def get_image(self, source_url: str) -> tuple[bytes, str]:
        from urllib.parse import urlparse

        parsed = urlparse(source_url)
        hostname = (parsed.hostname or "").lower()
        allowed_domains = (
            "tcgplayer.com",
            "tcgapi.dev",
            "pokemontcg.io",
            "pokemon.com",
            "githubusercontent.com",
            "pokeapi.co",
        )
        if not hostname or not any(hostname == d or hostname.endswith(f".{d}") for d in allowed_domains):
            error = ValueError(f"Image URL host '{hostname}' is not in the approved image domain allowlist")
            logger.error("Image request blocked by SSRF host filter url=%s error=%s", source_url, error)
            raise error

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = httpx.get(
                    source_url,
                    headers={"Accept": "image/avif,image/webp,image/*"},
                    timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
                    follow_redirects=True,
                )
                response.raise_for_status()
                return response.content, response.headers.get("content-type", "image/jpeg")
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                logger.error(
                    "TCG API image HTTP error url=%s status=%s attempt=%s/%s error=%s: %s",
                    source_url,
                    status,
                    attempt,
                    MAX_ATTEMPTS,
                    type(exc).__name__,
                    exc,
                )
                if status not in RETRYABLE_STATUSES or attempt == MAX_ATTEMPTS:
                    raise
            except httpx.RequestError as exc:
                logger.error(
                    "TCG API image request failed url=%s attempt=%s/%s error=%s: %s",
                    source_url,
                    attempt,
                    MAX_ATTEMPTS,
                    type(exc).__name__,
                    exc,
                )
                if attempt == MAX_ATTEMPTS:
                    raise
            self.sleep(2 ** (attempt - 1))
        raise RuntimeError("TCG API image request exhausted attempts")
