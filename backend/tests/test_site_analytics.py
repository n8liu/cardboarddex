from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.database import Base, get_db
from app.main import app
from app.models.analytics import AdminSession, AnalyticsDay, AnalyticsEvent, AnalyticsVisitor
from app.schemas.analytics import PageView
from app.services.site_analytics_service import cleanup, record_page_view, report

ORIGIN = "https://cardboarddex.app"


@pytest.fixture
def db(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_api_key", "test-admin-secret")
    monkeypatch.setattr(settings, "analytics_identity_secret", "a" * 32)
    monkeypatch.setattr(settings, "analytics_enabled", True)
    monkeypatch.setattr(settings, "admin_cookie_secure", True)
    monkeypatch.setattr(settings, "analytics_trusted_proxy_cidrs", "")
    monkeypatch.setattr(settings, "admin_allowed_origins", ORIGIN)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    # Only new tables: this feature has no dependency on the catalog schema.
    for model in (AnalyticsVisitor, AnalyticsEvent, AnalyticsDay, AdminSession):
        model.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr("app.main.check_rate_limit", lambda **kwargs: (True, 0))
    monkeypatch.setattr("app.common.admin_auth.check_rate_limit", lambda *args, **kwargs: (True, 0))
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, base_url="https://api.cardboarddex.app", headers={"Origin": ORIGIN}, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def event(visitor=None, path="/catalog"):
    return PageView(event_id=uuid4(), visitor_id=visitor or uuid4(), path=path)


def login(client):
    return client.post("/admin/login", json={"secret": "test-admin-secret"})


def test_auth_cookie_logout_rotation_and_no_store(client, db, monkeypatch):
    response = client.get("/admin/stats")
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert client.post("/admin/login", json={"secret": "wrong"}).status_code == 401
    response = login(client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    for value in ("HttpOnly", "Secure", "SameSite=strict", "Path=/admin"):
        assert value in cookie
    assert client.get("/admin/stats").status_code == 200
    assert client.post("/admin/logout").status_code == 200
    assert client.get("/admin/stats").status_code == 401
    login(client)
    monkeypatch.setattr(get_settings(), "admin_api_key", "rotated-secret")
    assert client.get("/admin/stats").status_code == 401
    monkeypatch.setattr(get_settings(), "admin_api_key", None)
    assert client.get("/admin/stats").status_code == 403


def test_expiry_and_origin_enforcement(client, db):
    login(client)
    session = db.scalar(select(AdminSession))
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert client.get("/admin/stats").status_code == 401
    for origin in ("https://evil.example", "https://preview.cardboarddex.pages.dev", "null", ""):
        assert client.post("/admin/login", headers={"Origin": origin}, json={"secret": "test-admin-secret"}).status_code == 403
        assert client.get("/admin/stats", headers={"Origin": origin}).status_code == 403


def test_custom_domain_admin_origin(client, monkeypatch):
    monkeypatch.delenv("ADMIN_ALLOWED_ORIGINS", raising=False)
    monkeypatch.setattr(
        get_settings(), "admin_allowed_origins", Settings(_env_file=None).admin_allowed_origins,
    )
    origin = "https://cardboarddex.nliu.org"
    client.headers["Origin"] = origin
    response = login(client)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    assert client.get("/admin/stats").status_code == 200
    for rejected in ("https://other.nliu.org", "https://cardboarddex.nliu.org.attacker.com", "http://cardboarddex.nliu.org"):
        headers = {"Origin": rejected}
        assert client.post("/admin/login", headers=headers, json={"secret": "test-admin-secret"}).status_code == 403
        assert client.get("/admin/stats", headers=headers).status_code == 403
        assert client.post("/admin/logout", headers=headers).status_code == 403
    assert client.post("/admin/logout").status_code == 200


def test_login_rate_limit(client, monkeypatch):
    monkeypatch.setattr("app.common.admin_auth.check_rate_limit", lambda *args, **kwargs: (False, 42))
    response = login(client)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "42"


def test_deduplication_sessions_and_range_uniques(db):
    now = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    visitor = uuid4()
    first = event(visitor)
    assert record_page_view(db, first, "US", now - timedelta(days=1))
    assert not record_page_view(db, first, "US", now)
    record_page_view(db, event(visitor), "US", now)
    record_page_view(db, event(visitor, "/pokedex"), "CA", now + timedelta(minutes=29))
    record_page_view(db, event(visitor), "CA", now + timedelta(minutes=59))
    record_page_view(db, event(), "ZZ", now)
    result = report(db, (now - timedelta(days=1)).date(), now.date(), now)
    assert result["current"] == {"views": 5, "visitors": 2, "sessions": 4}
    assert [row["visitors"] for row in result["daily"]] == [1, 2]
    assert result["total_visitors"] == 2
    assert result["total_views"] == 5
    assert db.scalar(select(AnalyticsVisitor.id)) != str(visitor)


def test_country_trust_disabled_tracking_and_bot_filter(client, db, monkeypatch):
    payload = event().model_dump(mode="json")
    assert client.post("/telemetry/page-view", json=payload, headers={"CF-IPCountry": "US"}).status_code == 204
    assert db.scalar(select(AnalyticsEvent.country)) == "ZZ"
    monkeypatch.setattr("app.routers.telemetry.trusted_proxy", lambda request: True)
    client.post("/telemetry/page-view", json=event().model_dump(mode="json"), headers={"CF-IPCountry": "CA"})
    assert set(db.scalars(select(AnalyticsEvent.country))) == {"ZZ", "CA"}
    client.post("/telemetry/page-view", json=event().model_dump(mode="json"), headers={"User-Agent": "Googlebot"})
    monkeypatch.setattr(get_settings(), "analytics_enabled", False)
    client.post("/telemetry/page-view", json=event().model_dump(mode="json"))
    assert db.scalar(select(func.count()).select_from(AnalyticsEvent)) == 2


def test_peer_trust_and_ip_spoofing(monkeypatch):
    from starlette.requests import Request
    from app.common.admin_auth import request_identity, trusted_proxy
    monkeypatch.setattr(get_settings(), "analytics_trusted_proxy_cidrs", "127.0.0.1/32")
    def request(peer):
        return Request({"type": "http", "client": (peer, 123), "headers": [(b"cf-connecting-ip", b"8.8.8.8")]})
    assert not trusted_proxy(request("192.0.2.1"))
    assert request_identity(request("192.0.2.1")) == "192.0.2.1"
    assert trusted_proxy(request("127.0.0.1"))
    assert request_identity(request("127.0.0.1")) == "8.8.8.8"


def test_reject_sensitive_or_invalid_payloads(client):
    for path in ("/admin/stats", "/catalog?q=secret", "/unknown", "/cards/../../secret"):
        payload = event().model_dump(mode="json")
        payload["path"] = path
        assert client.post("/telemetry/page-view", json=payload).status_code == 422
    payload = event().model_dump(mode="json")
    payload["country"] = "US"
    assert client.post("/telemetry/page-view", json=payload).status_code == 422


def test_retention_preserves_totals_and_rejects_unavailable_dates(db):
    now = datetime.now(UTC)
    old = now - timedelta(days=91)
    record_page_view(db, event(), "US", old)
    record_page_view(db, event(), "CA", now)
    assert cleanup(db, now) == 1
    result = report(db, now.date(), now.date(), now)
    assert result["total_views"] == 2
    assert result["total_visitors"] == 2
    assert result["current"]["views"] == 1
    assert result["tracking_started_at"].date() == old.date()
    with pytest.raises(ValueError):
        report(db, old.date(), now.date(), now)
    with pytest.raises(ValueError):
        report(db, now.date(), (now + timedelta(days=1)).date(), now)
    assert report(db, (now - timedelta(days=89)).date(), now.date(), now)["previous"] is None


def test_empty_report_and_invalid_api_range(client):
    login(client)
    response = client.get("/admin/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_views"] == data["total_visitors"] == 0
    assert data["tracking_started_at"] is None
    assert len(data["daily"]) == 7
    assert client.get("/admin/stats?start=2000-01-01").status_code == 422


def test_storage_failure_is_logged_without_disrupting_pages(client, monkeypatch, caplog):
    from sqlalchemy.exc import OperationalError
    def fail(*args):
        raise OperationalError("write", {}, Exception("database offline"))
    monkeypatch.setattr("app.routers.telemetry.record_page_view", fail)
    response = client.post("/telemetry/page-view", json=event().model_dump(mode="json"))
    assert response.status_code == 503
    assert "database offline" in caplog.text
    assert "database offline" not in response.text
    assert client.get("/health").status_code == 200


def test_admin_internal_errors_are_private_and_not_cached(client, monkeypatch):
    login(client)
    def fail(*args):
        raise RuntimeError("private database failure")
    monkeypatch.setattr("app.routers.admin.report", fail)
    response = client.get("/admin/stats")
    assert response.status_code == 500
    assert response.headers["cache-control"] == "no-store"
    assert "private database failure" not in response.text


def test_analytics_configuration_rejects_invalid_secrets_and_proxy_networks():
    from pydantic import ValidationError
    from app.config import Settings
    with pytest.raises(ValidationError):
        Settings(_env_file=None, analytics_enabled=True, analytics_identity_secret="short")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, analytics_trusted_proxy_cidrs="not-a-network")


def test_repeat_page_visits_keep_one_visitor_across_sessions_and_days(db):
    now = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    visitor = uuid4()
    for offset in (timedelta(days=-1), timedelta(), timedelta(minutes=1), timedelta(minutes=31)):
        view = event(visitor, "/catalog")
        assert record_page_view(db, view, "US", now + offset)
        assert not record_page_view(db, view, "US", now + offset)
    result = report(db, (now - timedelta(days=1)).date(), now.date(), now)
    assert result["current"] == {"views": 4, "visitors": 1, "sessions": 3}
    assert result["total_views"] == 4
    assert result["total_visitors"] == 1
    assert [row["views"] for row in result["daily"]] == [1, 3]
    assert [row["visitors"] for row in result["daily"]] == [1, 1]
