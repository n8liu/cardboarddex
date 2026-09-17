"""Read-only deployment guard: never migrate production implicitly."""
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.database import engine


def main() -> None:
    expected = set(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())
    with engine.connect() as connection:
        actual = set(MigrationContext.configure(connection).get_current_heads())
    if actual != expected:
        raise SystemExit(f"Schema revision mismatch: actual={actual}, expected={expected}. Review migrations separately.")
    print("Database revision matches release")


if __name__ == "__main__":
    main()
