import logging
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.common.rate_limiter import rate_limit
from app.config import get_settings
from app.database import get_db
from app.models import Card
from app.schemas.cards import (
    PokemonVolumeResponse,
    PortfolioValuationRequest,
    PortfolioValuationResponse,
    TrackActionRequest,
    TrendingDashboardResponse,
)
from app.services.catalog_service import (
    calculate_top_pokemon_volume,
    match_to_pokemon,
)
from app.services.portfolio_service import calculate_portfolio_valuation
from app.services.trending_service import (
    get_trending_dashboard,
    record_action,
    reset_trending_analytics,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cards", tags=["Analytics"])

ADMIN_TOKEN_HEADER = "x-admin-token"


def verify_admin_token(x_admin_token: str | None = Header(default=None, alias=ADMIN_TOKEN_HEADER)) -> None:
    settings = get_settings()
    configured_token = (settings.admin_api_key or "").strip()
    if not configured_token:
        logger.warning("Admin action attempted but ADMIN_API_KEY is not configured on server")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin functionality is not enabled",
        )
    if not x_admin_token or x_admin_token != configured_token:
        logger.warning("Unauthorized admin access attempt with token present=%s", bool(x_admin_token))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: invalid or missing admin token",
        )


@router.get("/top-pokemon-volume", response_model=PokemonVolumeResponse)
def get_top_pokemon_volume(
    response: Response,
    timeframe: Literal["24h", "7d", "30d", "all_time", "2026_ytd"] = Query(
        default="7d", description="Observed market value timeframe"
    ),
    sort_by: Literal["volume_desc", "sales_desc", "growth_desc", "avg_price_desc"] = Query(
        default="volume_desc", description="Rank sorting metric"
    ),
    q: str | None = Query(default=None, max_length=100, description="Search Pokémon by name"),
    db: Session = Depends(get_db),
) -> PokemonVolumeResponse:
    """Top 50 Pokémon ranked by aggregated observed market value — computed live from the database."""
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=600, stale-while-revalidate=1200"
    return calculate_top_pokemon_volume(db, timeframe=timeframe, sort_by=sort_by, q=q)


@router.get("/trending", response_model=TrendingDashboardResponse)
def get_trending(
    response: Response,
    timeframe: Literal["24h", "7d", "30d", "all_time", "2026_ytd"] = Query(
        default="7d", description="Timeframe for trending volume calculations"
    ),
    q: str | None = Query(default=None, max_length=100, description="Search cards and Pokémon"),
    db: Session = Depends(get_db),
) -> TrendingDashboardResponse:
    """Returns the 3-column Trending Dashboard: Trending Cards, Popular Pokémon, and Volume Leaders."""
    response.headers["Cache-Control"] = "public, max-age=30, s-maxage=60, stale-while-revalidate=120"
    return get_trending_dashboard(db, timeframe=timeframe, q=q)


@router.post("/trending/reset", dependencies=[Depends(verify_admin_token)])
def reset_trending() -> dict[str, str]:
    """Reset all click and search counters to zero and invalidate trending caches."""
    reset_trending_analytics()
    return {"status": "ok", "message": "Trending analytics reset to zero"}


@router.post(
    "/track-action",
    dependencies=[
        Depends(
            rate_limit(
                max_requests=get_settings().rate_limit_track_action_per_minute,
                bucket="track_action",
            )
        )
    ],
)
def track_user_action(payload: TrackActionRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    """Track user clicks, searches, and views for real-time trending analytics."""
    record_action(entity_type=payload.entity_type, entity_id=payload.entity_id, action=payload.action)
    if payload.entity_type == "card":
        card = db.query(Card).filter(Card.id == payload.entity_id).first()
        if card:
            poke = match_to_pokemon(card.name)
            if poke:
                record_action("pokemon", poke, payload.action)
    return {"status": "ok"}


@router.post("/portfolio-valuation", response_model=PortfolioValuationResponse)
def get_portfolio_valuation(
    payload: PortfolioValuationRequest,
    db: Session = Depends(get_db),
) -> PortfolioValuationResponse:
    """Calculates combined current value, deltas, and historical daily curves across a portfolio of cards."""
    return calculate_portfolio_valuation(db, card_ids=payload.card_ids, days=payload.days)
