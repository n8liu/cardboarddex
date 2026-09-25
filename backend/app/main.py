import logging
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from anyio import to_thread

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.rate_limiter import check_rate_limit, get_client_ip
from app.common.redis import get_redis as _get_redis, get_durable_redis
from app.config import get_settings
from app.database import get_db
from app.routers import analytics, cards, catalog, market

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

settings = get_settings()

ALLOWED_ORIGIN_REGEX = re.compile(
    r"^(https:\/\/([a-zA-Z0-9\-_]+\.)?cardboarddex\.pages\.dev|https:\/\/(www\.)?cardboarddex\.(app|com)|http:\/\/(localhost|127\.0\.0\.1)(:\d+)?)$"
)


def is_allowed_origin(origin: str | None) -> bool:
    """Validate cross-origin request against exact allowed domains and regex patterns."""
    if not origin:
        return False
    clean_origin = origin.strip().rstrip("/")
    if clean_origin in settings.cors_origins:
        return True
    return bool(ALLOWED_ORIGIN_REGEX.match(clean_origin))


docs_url = "/docs" if settings.enable_api_docs else None
redoc_url = "/redoc" if settings.enable_api_docs else None
openapi_url = "/openapi.json" if settings.enable_api_docs else None

@asynccontextmanager
async def lifespan(app: FastAPI):
    limiter = to_thread.current_default_thread_limiter()
    previous_limit = limiter.total_tokens
    limiter.total_tokens = settings.api_thread_limit
    try:
        yield
    finally:
        limiter.total_tokens = previous_limit


app = FastAPI(
    title="CardboardDex API",
    version="0.1.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
    lifespan=lifespan,
)


@app.middleware("http")
async def security_and_rate_limit_middleware(request: Request, call_next: object) -> Response:
    # 1. Skip rate limiting for health check and preflight OPTIONS requests
    if request.method != "OPTIONS" and request.url.path not in {"/health", "/ready"}:
        client_ip = get_client_ip(request)
        clean_path = request.url.path.rstrip("/")
        is_image_request = clean_path.endswith("/image")
        bucket = "images" if is_image_request else "global"
        max_requests = 6000 if is_image_request else settings.rate_limit_per_minute
        allowed, retry_after = check_rate_limit(
            client_ip=client_ip,
            bucket=bucket,
            max_requests=max_requests,
            window_seconds=60,
        )
        if not allowed:
            logging.warning(
                "Rate limit exceeded for client_ip=%s on bucket=%s path=%s",
                client_ip,
                bucket,
                request.url.path,
            )
            origin = request.headers.get("origin")
            headers: dict[str, str] = {
                "Retry-After": str(retry_after),
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
            }
            if is_allowed_origin(origin):
                headers["Access-Control-Allow-Origin"] = origin  # type: ignore[assignment]
                headers["Access-Control-Allow-Credentials"] = "true"
                headers["Vary"] = "Origin"
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many requests. Please slow down and try again later."},
                headers=headers,
            )

    response = await call_next(request)  # type: ignore[operator]

    # 2. Inject comprehensive security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self' https:;"
    )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX.pattern,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "HEAD"],
    allow_headers=["*"],
)

app.include_router(catalog.router)
app.include_router(market.router)
app.include_router(analytics.router)
app.include_router(cards.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Rule 1: Always log exact exception type, message, and traceback
    logging.exception("Unhandled error processing %s %s: %s", request.method, request.url.path, exc)
    origin = request.headers.get("origin")
    headers: dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-XSS-Protection": "1; mode=block",
    }
    if is_allowed_origin(origin):
        headers["Access-Control-Allow-Origin"] = origin  # type: ignore[assignment]
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"

    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."},
        headers=headers,
    )


@app.get("/health")
def health(
    details: bool = False,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Active health probe verifying status with optional component diagnostics."""
    if not details:
        return {"status": "ok"}

    db_ok = False
    try:
        db.execute(select(1)).scalar()
        db_ok = True
    except Exception as exc:
        logging.debug("Health probe database query failed: %s", exc)

    redis_ok = False
    try:
        r = _get_redis()
        if r is not None:
            redis_ok = bool(r.ping())
    except Exception as exc:
        logging.debug("Health probe Redis ping failed: %s", exc)

    return {
        "status": "ok",
        "database": "connected" if db_ok else "unreachable",
        "redis": "connected" if redis_ok else "unavailable",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.get("/ready")
def ready(db: Session = Depends(get_db)) -> JSONResponse:
    try:
        db.execute(select(1)).scalar_one()
        get_durable_redis().ping()
        cache = _get_redis()
        if cache is None or not cache.ping():
            raise ConnectionError("Cache Redis unavailable")
    except Exception as exc:
        logging.error("Readiness failed error=%s: %s", type(exc).__name__, exc)
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ready"})


@app.get("/health/quotas")
def get_quotas() -> dict[str, Any]:
    """Report daily provider quota limits, requests used, and remaining headroom."""
    tcg_limit = settings.tcgapi_daily_request_limit
    ebay_limit = settings.ebay_daily_request_limit
    tcg_used = 0
    ebay_used = 0
    r = get_durable_redis()
    if r is not None:
        try:
            day_bucket = int(datetime.now(UTC).timestamp() // 86400)
            tcg_val = r.get(f"cardboarddex:tcgapi:requests:{day_bucket}")
            if tcg_val:
                tcg_used = int(tcg_val)
            ebay_val = r.get(f"cardboarddex:ebay:requests:{day_bucket}")
            if ebay_val:
                ebay_used = int(ebay_val)
        except Exception as exc:
            logging.warning("Failed reading quota counters from Redis: %s", exc)
            return JSONResponse({"status": "unavailable"}, status_code=503)

    return {
        "tcgapi": {
            "daily_limit": tcg_limit,
            "requests_used": tcg_used,
            "requests_remaining": max(0, tcg_limit - tcg_used),
        },
        "ebay": {
            "daily_limit": ebay_limit,
            "requests_used": ebay_used,
            "requests_remaining": max(0, ebay_limit - ebay_used),
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }
