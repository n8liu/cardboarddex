import hmac
import secrets
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.common.admin_auth import (
    COOKIE_NAME, SESSION_SECONDS, limit, require_admin, require_admin_origin, session_hash,
)
from app.config import get_settings
from app.database import get_db
from app.models.analytics import AdminSession
from app.schemas.analytics import AdminLogin, StatsReport
from app.services.site_analytics_service import report

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/login", dependencies=[Depends(require_admin_origin)])
def login(payload: AdminLogin, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    limit(request, "admin_login", 5)
    settings = get_settings()
    expected = (settings.admin_api_key or "").strip()
    if not expected:
        raise HTTPException(403, "Admin functionality is not enabled")
    if not hmac.compare_digest(payload.secret.get_secret_value().encode(), expected.encode()):
        raise HTTPException(401, "Invalid admin secret")
    token = secrets.token_urlsafe(32)
    old_token = request.cookies.get(COOKIE_NAME)
    if old_token and len(old_token) <= 128:
        old = db.get(AdminSession, session_hash(old_token))
        if old:
            db.delete(old)
    db.add(AdminSession(token_hash=session_hash(token), expires_at=datetime.now(UTC) + timedelta(seconds=SESSION_SECONDS)))
    db.commit()
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=settings.admin_cookie_secure, samesite="strict", path="/admin")
    return {"status": "ok"}


@router.post("/logout")
def logout(response: Response, session: AdminSession = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    db.delete(session)
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/admin", secure=get_settings().admin_cookie_secure,
                           httponly=True, samesite="strict")
    return {"status": "ok"}


@router.get("/stats", response_model=StatsReport)
def stats(request: Request, start: date | None = None, end: date | None = None,
          _: AdminSession = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    limit(request, "admin_stats", 30)
    last = end or datetime.now(UTC).date()
    first = start or last - timedelta(days=6)
    try:
        return report(db, first, last)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
