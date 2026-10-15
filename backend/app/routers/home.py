from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.home import HomeOverview
from app.services.home_service import build_home_overview
from app.common.response_cache import cached_read

router = APIRouter(prefix='/home', tags=['Home'])


@router.get('/overview', response_model=HomeOverview)
@cached_read("home", fresh=300, maximum=1800)
def overview(response: Response, db: Session = Depends(get_db)) -> HomeOverview:
    return build_home_overview(db)


@router.get('/stats')
def stats(response: Response, db: Session = Depends(get_db)):
    # Lightweight reads; do not rebuild market highlights to refresh counters.
    from datetime import UTC, datetime
    from sqlalchemy import func, select
    from app.common.redis import get_redis
    from app.models import Card, Set
    from app.services.collection_stats import live_observation_count

    response.headers["Cache-Control"] = "no-store"
    return {"products": db.scalar(select(func.count()).select_from(Card)) or 0,
            "sets": db.scalar(select(func.count()).select_from(Set)) or 0,
            "price_observations": live_observation_count(db, get_redis()),
            "calculated_at": datetime.now(UTC)}
