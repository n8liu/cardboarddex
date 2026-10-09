import hashlib
import hmac
import ipaddress
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.common.rate_limiter import check_rate_limit
from app.config import get_settings
from app.database import get_db
from app.models.analytics import AdminSession

COOKIE_NAME = "cardboarddex_admin"
SESSION_SECONDS = 8 * 60 * 60


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def trusted_proxy(request: Request) -> bool:
    if not request.client:
        return False
    try:
        peer = ipaddress.ip_address(request.client.host)
    except ValueError:
        return False
    return any(peer in ipaddress.ip_network(cidr.strip()) for cidr in
               get_settings().analytics_trusted_proxy_cidrs.split(",") if cidr.strip())


def request_identity(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    if trusted_proxy(request):
        value = request.headers.get("cf-connecting-ip", "")
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            return peer
    return peer


def limit(request: Request, bucket: str, maximum: int) -> None:
    allowed, retry = check_rate_limit(request_identity(request), bucket=bucket, max_requests=maximum)
    if not allowed:
        raise HTTPException(429, "Too many requests", headers={"Retry-After": str(retry)})


def require_admin_origin(request: Request) -> None:
    allowed = {o.strip().rstrip("/") for o in get_settings().admin_allowed_origins.split(",") if o.strip()}
    if request.headers.get("origin") not in allowed:
        raise HTTPException(403, "Admin origin is not allowed")


def session_hash(token: str) -> str:
    # Rotating ADMIN_API_KEY revokes all existing sessions as well.
    key = (get_settings().admin_api_key or "").strip().encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def require_admin(request: Request, db: Session = Depends(get_db)) -> AdminSession:
    require_admin_origin(request)
    if not (get_settings().admin_api_key or "").strip():
        raise HTTPException(403, "Admin functionality is not enabled")
    token = request.cookies.get(COOKIE_NAME, "")
    if not token or len(token) > 128:
        raise HTTPException(401, "Admin login required")
    session = db.get(AdminSession, session_hash(token))
    if session is None or utc(session.expires_at) <= datetime.now(UTC):
        raise HTTPException(401, "Admin session expired or invalid")
    return session
