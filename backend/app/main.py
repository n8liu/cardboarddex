import logging

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import cards

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

settings = get_settings()

app = FastAPI(title="CardboardDex API", version="0.1.0")


@app.middleware("http")
async def add_security_headers(request: Request, call_next: object) -> Response:
    response = await call_next(request)  # type: ignore[operator]
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^(https:\/\/([a-zA-Z0-9\-_]+\.)*(pages\.dev|cardboarddex\.com)|http:\/\/(localhost|127\.0\.0\.1)(:\d+)?)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(cards.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logging.exception("Unhandled error processing %s %s: %s", request.method, request.url.path, exc)
    origin = request.headers.get("origin")
    headers: dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-XSS-Protection": "1; mode=block",
    }
    if origin:
        if (
            origin in settings.cors_origins
            or "pages.dev" in origin
            or "cardboarddex.com" in origin
            or "localhost" in origin
            or "127.0.0.1" in origin
        ):
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"
            headers["Vary"] = "Origin"
    return JSONResponse(
        status_code=500,
        content={"detail": f"Database or internal service error: {type(exc).__name__}"},
        headers=headers,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

