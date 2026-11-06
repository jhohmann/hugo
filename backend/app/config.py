"""Shared configuration for local Python processes and Docker services."""

import os
from pathlib import Path

from dotenv import load_dotenv
from psycopg.conninfo import make_conninfo

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_environment(path: str | Path | None = None) -> None:
    """Explicit process environment takes precedence over the env file."""
    env_file = Path(path) if path is not None else PROJECT_ROOT / ".env"
    if path is not None and not env_file.is_file():
        raise FileNotFoundError(f"Umgebungsdatei nicht gefunden: {env_file}")
    load_dotenv(env_file, override=False)


def database_url() -> str:
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    # Docker passes individual fields, so passwords need no URL encoding.
    return make_conninfo(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "hugo"),
        user=os.getenv("DB_USER", "hugo"),
        password=os.getenv("DB_PASSWORD", "hugo_dev"),
    )
