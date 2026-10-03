"""Run database migrations without an alembic.ini.

python -m shared.migrate                 # upgrade to the latest schema
python -m shared.migrate revision "msg"  # autogenerate a new migration (dev)
"""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS = Path(__file__).parent / "migrations"


def alembic_config(url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    if url:
        cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def upgrade(url: str | None = None, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[1] == "revision":
        command.revision(alembic_config(), message=sys.argv[2], autogenerate=True)
    else:
        upgrade()
        print("Database is at the latest schema")


if __name__ == "__main__":
    main()
