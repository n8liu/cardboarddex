import logging
import math
import re
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from redis.exceptions import RedisError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.formatters import parse_iso_datetime as _parse_iso_datetime
from app.common.redis import get_redis as _get_redis
from app.config import get_settings
from app.database import get_db
from app.models import Card, PriceObservation, ProviderCardState, Set
from app.schemas.cards import (
    CardDetail,
    CardPricingResponse,
    PriceObservationItem,
    ProviderPricingState,
)
from app.services.catalog_service import (
    build_card_summary as _summary,
    match_to_pokemon,
)
from app.services.trending_service import record_action
from app.tcgapi import TCGAPIClient

# Re-exports for test and backward compatibility
from app.routers.catalog import (  # noqa: F401
    clear_catalog_caches,
    _evict_oldest_cache_entries,
    _SEARCH_LOCAL_CACHE,
    _SETS_LOCAL_CACHE,
)
from app.services.catalog_service import get_set_statistics  # noqa: F401
from app.routers.analytics import verify_admin_token, ADMIN_TOKEN_HEADER  # noqa: F401
from app.routers.market import (  # noqa: F401
    get_tcgapi_client,
    _MOVERS_LOCAL_FALLBACK,
    _compute_db_market_movers,
    _build_mover_item,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cards", tags=["Cards"])

ALLOWED_MARKETPLACE_DOMAINS = {"ebay.com", "tcgplayer.com"}
RE_SAFE_CARD_ID = re.compile(r"^[a-zA-Z0-9_\-]+$")
_S3_CLIENT = None


def _get_s3_client(region_name: str) -> Any:
    global _S3_CLIENT
    if _S3_CLIENT is None:
        try:
            import boto3
            _S3_CLIENT = boto3.client("s3", region_name=region_name)
        except Exception as exc:
            logger.warning("Failed initializing boto3 S3 client error=%s: %s", type(exc).__name__, exc)
            return None
    return _S3_CLIENT


def _extract_listing_url(item: PriceObservation) -> str | None:
    candidate: str | None = None
    if isinstance(item.payload, dict):
        raw_item = item.payload.get("item")
        if isinstance(raw_item, dict) and raw_item.get("itemWebUrl"):
            candidate = str(raw_item["itemWebUrl"])
        elif item.payload.get("itemWebUrl"):
            candidate = str(item.payload["itemWebUrl"])
        elif item.payload.get("item_url"):
            candidate = str(item.payload["item_url"])
    if not candidate and item.provider == "ebay" and item.provider_card_id:
        clean_id = item.provider_card_id.replace("v1|", "").split("|")[0]
        if clean_id.isdigit():
            candidate = f"https://www.ebay.com/itm/{clean_id}"

    if candidate:
        try:
            parsed = urlparse(candidate)
            if parsed.scheme in ("https", "http"):
                host = (parsed.hostname or "").lower()
                if any(host == d or host.endswith(f".{d}") for d in ALLOWED_MARKETPLACE_DOMAINS):
                    return candidate
        except Exception as exc:
            logger.debug("Failed parsing listing URL candidate=%s: %s", candidate, exc)
    return None


def _trim_outliers_iqr(prices: list[float]) -> list[float]:
    """Filter extreme outliers using the Interquartile Range (IQR) rule when >= 4 listings exist."""
    if len(prices) < 4:
        return prices
    sorted_p = sorted(prices)
    n = len(sorted_p)
    q1 = sorted_p[n // 4]
    q3 = sorted_p[(3 * n) // 4]
    iqr = q3 - q1
    if iqr <= 0:
        return prices
    lower_bound = max(0.01, q1 - 1.5 * iqr)
    upper_bound = q3 + 1.5 * iqr
    filtered = [p for p in sorted_p if lower_bound <= p <= upper_bound]
    return filtered if filtered else prices


@router.get("/{card_id}", response_model=CardDetail)
def get_card(
    card_id: str,
    response: Response,
    ref: str | None = Query(default=None, description="Navigation referrer tag"),
    db: Session = Depends(get_db),
) -> CardDetail:
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    row = db.execute(
        select(Card, Set).join(Set, Card.set_id == Set.id).where(Card.id == card_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    card, card_set = row
    if ref != "trending":
        record_action("card", card_id, "view")
        poke = match_to_pokemon(card.name)
        if poke:
            record_action("pokemon", poke, "view")
    latest_synced = db.scalar(
        select(func.max(ProviderCardState.last_synced_at)).where(ProviderCardState.card_id == card_id)
    )
    summary = _summary(card, card_set, last_updated_at=latest_synced)
    return CardDetail(
        **summary.model_dump(),
        series=card_set.series,
        release_date=card_set.release_date,
    )


@router.get("/{card_id}/prices", response_model=CardPricingResponse)
def get_card_prices(
    card_id: str,
    response: Response,
    days: int = Query(default=365, ge=1, le=730),
    db: Session = Depends(get_db),
) -> CardPricingResponse:
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    if db.get(Card, card_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    cutoff = datetime.now(UTC) - timedelta(days=days)
    states = list(
        db.scalars(
            select(ProviderCardState)
            .where(
                ProviderCardState.card_id == card_id,
                or_(
                    ProviderCardState.provider == "tcgapi",
                    ProviderCardState.provider.ilike("%ebay%"),
                ),
            )
            .order_by(ProviderCardState.provider)
        )
    )
    observations = list(
        db.scalars(
            select(PriceObservation)
            .where(
                PriceObservation.card_id == card_id,
                or_(
                    PriceObservation.provider == "tcgapi",
                    PriceObservation.provider.ilike("%ebay%"),
                ),
                or_(
                    PriceObservation.observed_at >= cutoff,
                    PriceObservation.provider_updated_at >= cutoff,
                    PriceObservation.provider_updated_at.is_(None),
                ),
            )
            .order_by(PriceObservation.observed_at.desc())
        )
    )

    def _resolve_obs_payload(item: PriceObservation) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if isinstance(item.payload, dict):
            raw_variant = item.payload.get("variant")
            if isinstance(raw_variant, dict):
                result.update(raw_variant)
            for k, v in item.payload.items():
                if k not in ("variant", "raw_card") and v is not None:
                    result[k] = v
        return result

    def _build_obs_item(item: PriceObservation) -> PriceObservationItem:
        p = _resolve_obs_payload(item)
        low_val = p.get("low_price") or p.get("low")
        med_val = p.get("median_price") or p.get("median")
        ship_val = p.get("lowest_with_shipping") or p.get("direct_low_price")
        buy_val = p.get("buylist_price")
        change_24h = p.get("price_change_24h")
        change_7d = p.get("price_change_7d")
        change_30d = p.get("price_change_30d")
        listings = p.get("total_listings")

        return PriceObservationItem(
            id=item.id,
            card_id=item.card_id,
            provider=item.provider,
            provider_card_id=item.provider_card_id,
            variant_id=item.variant_id,
            condition=item.condition,
            printing=item.printing,
            grading_company=item.grading_company,
            grade=str(item.grade) if item.grade is not None else None,
            price=float(item.price),
            currency=item.currency,
            provider_updated_at=item.provider_updated_at,
            observed_at=item.observed_at,
            listing_url=_extract_listing_url(item),
            low_price=float(low_val) if low_val is not None else None,
            median_price=float(med_val) if med_val is not None else None,
            lowest_with_shipping=float(ship_val) if ship_val is not None else None,
            buylist_price=float(buy_val) if buy_val is not None else None,
            price_change_24h=float(change_24h) if change_24h is not None else None,
            price_change_7d=float(change_7d) if change_7d is not None else None,
            price_change_30d=float(change_30d) if change_30d is not None else None,
            total_listings=int(listings) if listings is not None else None,
        )

    obs_items = [_build_obs_item(item) for item in observations]

    avg_listing_price: float | None = None
    latest_by_variant: dict[str, PriceObservationItem] = {}
    for item in obs_items:
        key = f"{item.provider}:{item.variant_id}:{item.provider_card_id}"
        if key not in latest_by_variant:
            latest_by_variant[key] = item
    latest_items = list(latest_by_variant.values())

    raw_ebay_prices = [
        item.price
        for item in latest_items
        if item.provider == "ebay" and item.grading_company is None and item.price > 0
    ]
    if raw_ebay_prices:
        # Trim extreme asking-price outliers using IQR filtering
        trimmed_ebay_prices = _trim_outliers_iqr(raw_ebay_prices)
        avg_listing_price = round(sum(trimmed_ebay_prices) / len(trimmed_ebay_prices), 2)
    else:
        tcg_state = next((s for s in states if s.provider == "tcgapi" and isinstance(s.payload, dict)), None)
        if tcg_state and isinstance(tcg_state.payload, dict):
            card_payload = tcg_state.payload.get("card") or {}
            variants_list = card_payload.get("variants") or []
            valid_tcg_prices: list[float] = []
            for v in variants_list:
                if isinstance(v, dict):
                    m_p = v.get("market_price")
                    if m_p is not None and float(m_p) > 0:
                        valid_tcg_prices.append(float(m_p))
                    elif v.get("low_price") is not None and float(v.get("low_price")) > 0:
                        valid_tcg_prices.append(float(v.get("low_price")))
            if valid_tcg_prices:
                avg_listing_price = round(sum(valid_tcg_prices) / len(valid_tcg_prices), 2)

        if avg_listing_price is None:
            tcg_prices: list[float] = []
            for item in latest_items:
                if item.provider == "tcgapi":
                    if item.median_price is not None:
                        tcg_prices.append(item.median_price)
                    elif item.low_price is not None:
                        tcg_prices.append(item.low_price)
            avg_listing_price = round(sum(tcg_prices) / len(tcg_prices), 2) if tcg_prices else None

    return CardPricingResponse(
        card_id=card_id,
        provider_states=[ProviderPricingState(
            provider=item.provider,
            match_status=item.match_status,
            last_synced_at=item.last_synced_at,
        ) for item in states],
        observations=obs_items,
        avg_listing_price=avg_listing_price,
    )


_BROKEN_IMG_TTL = 86400  # 24 hours
_PLACEHOLDER_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="560" viewBox="0 0 400 560" fill="none">'
    b'<rect width="400" height="560" rx="16" fill="#1e293b"/>'
    b'<rect x="20" y="20" width="360" height="520" rx="12" stroke="#334155" stroke-width="2" stroke-dasharray="8 8"/>'
    b'<circle cx="200" cy="260" r="32" fill="#334155"/>'
    b'<path d="M190 260h20M200 250v20" stroke="#64748b" stroke-width="3" stroke-linecap="round"/>'
    b'<text x="200" y="320" fill="#94a3b8" font-size="13" font-family="system-ui, -apple-system, sans-serif" font-weight="600" text-anchor="middle">Image Not Available</text>'
    b'</svg>'
)


@router.get("/{card_id}/image")
def get_card_image(
    card_id: str,
    db: Session = Depends(get_db),
    client: TCGAPIClient = Depends(get_tcgapi_client),
) -> Response:
    # 1. Path traversal and injection protection
    if not RE_SAFE_CARD_ID.match(card_id) or len(card_id) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid card ID format",
        )

    _img_redis = _get_redis()
    _broken_key = f"cardboarddex:broken_img:{card_id}"
    _is_broken = False
    if _img_redis is not None:
        try:
            _is_broken = bool(_img_redis.exists(_broken_key))
        except RedisError as exc:
            logger.warning(
                "Broken image Redis check failed card_id=%s error=%s: %s",
                card_id,
                type(exc).__name__,
                exc,
            )
    if _is_broken:
        return Response(
            content=_PLACEHOLDER_SVG,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    card = db.get(Card, card_id)
    if card is None or not card.image_url:
        return Response(
            content=_PLACEHOLDER_SVG,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    settings = get_settings()
    if settings.s3_bucket_name:
        s3_url = f"https://{settings.s3_bucket_name}.s3.{settings.aws_region}.amazonaws.com/cards/{card_id}.png"
        if settings.cloudfront_domain:
            s3_url = f"https://{settings.cloudfront_domain}/cards/{card_id}.png"
        try:
            s3_resp = httpx.head(s3_url, timeout=1.5)
            if s3_resp.status_code == 200:
                return Response(
                    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                    headers={
                        "Location": s3_url,
                        "Cache-Control": "public, max-age=31536000, immutable",
                    },
                )
        except Exception as exc:
            logger.debug("S3 image check skipped card_id=%s: %s", card_id, exc)

    try:
        content, content_type = client.get_image(card.image_url)
        if settings.s3_bucket_name:
            try:
                _s3 = _get_s3_client(settings.aws_region)
                if _s3 is not None:
                    _s3.put_object(
                        Bucket=settings.s3_bucket_name,
                        Key=f"cards/{card_id}.png",
                        Body=content,
                        ContentType=content_type or "image/png",
                        CacheControl="public, max-age=31536000, immutable",
                    )
            except Exception as s3_err:
                logger.debug("Background S3 cache upload skipped card_id=%s: %s", card_id, s3_err)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            if _img_redis is not None:
                try:
                    _img_redis.setex(_broken_key, _BROKEN_IMG_TTL, "1")
                except RedisError as exc2:
                    logger.warning(
                        "Failed to mark broken image in Redis card_id=%s error=%s: %s",
                        card_id,
                        type(exc2).__name__,
                        exc2,
                    )
            logger.info(
                "Card image not found upstream card_id=%s url=%s; caching 404 fallback",
                card_id,
                card.image_url,
            )
            return Response(
                content=_PLACEHOLDER_SVG,
                media_type="image/svg+xml",
                headers={"Cache-Control": "public, max-age=86400"},
            )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Image provider rejected request") from exc
    except (httpx.RequestError, ValueError) as exc:
        if _img_redis is not None:
            try:
                _img_redis.setex(_broken_key, _BROKEN_IMG_TTL, "1")
            except RedisError as exc2:
                logger.warning(
                    "Failed to mark broken image in Redis card_id=%s error=%s: %s",
                    card_id,
                    type(exc2).__name__,
                    exc2,
                )
        logger.warning(
            "Card image request failed card_id=%s error=%s: %s; serving placeholder",
            card_id,
            type(exc).__name__,
            exc,
        )
        return Response(
            content=_PLACEHOLDER_SVG,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "CDN-Cache-Control": "public, max-age=31536000, immutable",
        },
    )
