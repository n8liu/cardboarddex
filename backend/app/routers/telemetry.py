import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.admin_auth import limit, trusted_proxy
from app.config import get_settings
from app.database import get_db
from app.schemas.analytics import PageView
from app.services.site_analytics_service import record_page_view

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telemetry", tags=["Site telemetry"])


@router.post("/page-view", status_code=204)
def page_view(payload: PageView, request: Request, db: Session = Depends(get_db)) -> Response:
    settings = get_settings()
    if not settings.analytics_enabled:
        return Response(status_code=204)
    # Exact origins only: production and explicitly enabled local environments.
    if request.headers.get("origin") not in {o.strip() for o in settings.admin_allowed_origins.split(",")}:
        raise HTTPException(403, "Origin is not allowed")
    limit(request, "site_telemetry", 60)
    if re.search(r"bot|crawler|spider|headless|slurp", request.headers.get("user-agent", ""), re.I):
        return Response(status_code=204)
    country = request.headers.get("cf-ipcountry", "").upper() if trusted_proxy(request) else ""
    if not re.fullmatch(r"[A-Z]{2}", country) or country in {"XX", "T1"}:
        country = "ZZ"
    try:
        record_page_view(db, payload, country)
    except (SQLAlchemyError, ValueError) as exc:
        db.rollback()
        logger.exception("Site telemetry write failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(503, "Tracking temporarily unavailable") from exc
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
