import logging
import re

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.common.rate_limiter import check_rate_limit, get_client_ip
from app.config import get_settings
from app.routers import cards

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

app = FastAPI(
    title="CardboardDex API",
    version="0.1.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
)


@app.middleware("http")
async def security_and_rate_limit_middleware(request: Request, call_next: object) -> Response:
    # 1. Skip rate limiting for health check and preflight OPTIONS requests
    if request.method != "OPTIONS" and request.url.path != "/health":
        client_ip = get_client_ip(request)
        allowed, retry_after = check_rate_limit(
            client_ip=client_ip,
            bucket="global",
            max_requests=settings.rate_limit_per_minute,
            window_seconds=60,
        )
        if not allowed:
            logging.warning("Global rate limit exceeded for client_ip=%s on path=%s", client_ip, request.url.path)
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
def health() -> dict[str, str]:
    return {"status": "ok"}
