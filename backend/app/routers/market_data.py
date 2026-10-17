from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Card, PriceObservation
from app.services.market_data_service import freshness, history_series, sales_activity

router = APIRouter(tags=["Provider market data"])


@router.get("/market/sales-activity")
def get_sales_activity(response: Response, days: Literal["7", "30", "90"] = "30",
                       q: str = Query(default="", max_length=120), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "public, max-age=60"
    return sales_activity(db, int(days), q)


@router.get("/cards/{card_id}/market-history")
def get_market_history(card_id: str, response: Response, days: Literal["30", "90", "180", "365"] = "30",
                       db: Session = Depends(get_db)):
    if db.get(Card, card_id) is None:
        raise HTTPException(404, "Card not found")
    response.headers["Cache-Control"] = "public, max-age=60"
    from app.services.ppt_prices import market_history
    ppt = market_history(db, card_id, int(days))
    if ppt:
        ppt.update(freshness({"market_price_as_of": ppt["return_end"]}))
        ppt["market_price"] = ppt["comparison_price"]
        ppt["checked_at"] = ppt["synced_at"]
        return ppt
    latest = db.scalar(select(PriceObservation).where(PriceObservation.card_id == card_id,
        PriceObservation.provider == "tcgapi", PriceObservation.grading_company.is_(None))
        .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc()).limit(1))
    printing = latest.printing if latest else None
    if printing == "Standard":
        printing = "Normal"
    result = history_series(db, card_id, int(days), printing)
    result.update(freshness(latest.payload if latest else None))
    result["market_price"] = float(latest.price) if latest else None
    result["checked_at"] = latest.provider_updated_at if latest else None
    return result
