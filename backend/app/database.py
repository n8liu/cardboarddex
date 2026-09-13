from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
if not settings.database_url.startswith("sqlite"):
    engine_kwargs.update({
        "pool_size": 15,
        "max_overflow": 15,
        "pool_timeout": 5.0,
        "pool_recycle": 1800,
    })

db_url = settings.database_url
if db_url.startswith("postgresql+psycopg://"):
    try:
        import psycopg  # noqa: F401
    except ImportError:
        db_url = db_url.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
elif db_url.startswith("postgresql://") or db_url.startswith("postgresql+psycopg2://"):
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        try:
            import psycopg  # noqa: F401
            db_url = db_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
            db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        except ImportError:
            pass

engine = create_engine(db_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
