"""Transactional, serialized migrations shared by development and Docker."""

import argparse
import hashlib
import logging
from pathlib import Path
import re

import psycopg

from app.config import database_url as configured_database_url, load_environment

logger = logging.getLogger(__name__)
MIGRATION_LOCK = 727976001


class MigrationError(Exception):
    pass


def get_migrations_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "migrations"


def get_migration_files(directory: Path | None = None) -> list[tuple[int, Path]]:
    files = []
    for path in (directory or get_migrations_dir()).glob("*.sql"):
        match = re.fullmatch(r"([0-9]+)_[a-z0-9_]+\.sql", path.name)
        if not match or int(match[1]) < 1:
            raise MigrationError(f"Ungültiger Migrationsname: {path.name}")
        files.append((int(match[1]), path))
    files.sort()
    versions = [version for version, _ in files]
    if not versions or versions[0] != 1 or len(set(versions)) != len(versions):
        raise MigrationError("Migrationen müssen bei 001 beginnen und eindeutige Nummern haben.")
    return files


def run_migrations(database_url: str | None = None, *, directory: Path | None = None) -> dict:
    result = {"status": "ok", "applied": [], "skipped": [], "error": None}
    current = None
    try:
        migrations = []
        for version, path in get_migration_files(directory):
            # Universal newlines make hashes portable across Windows/Linux.
            source = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(source.encode("utf-8")).hexdigest()
            migrations.append((version, path.name, source, checksum))
        with psycopg.connect(
            database_url or configured_database_url(), connect_timeout=5, autocommit=True,
        ) as conn:
            conn.execute("SET lock_timeout = '30s'")
            conn.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK,))
            # Session lock is held across transactions until disconnect.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    filename TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            applied = conn.execute(
                "SELECT version, filename, checksum FROM schema_version ORDER BY version"
            ).fetchall()
            expected = [(version, name, checksum) for version, name, _, checksum in migrations]
            if applied != expected[:len(applied)]:
                raise MigrationError(
                    "Migrationshistorie passt nicht zum Code: angewendete Dateien fehlen, "
                    "wurden verändert oder die Datenbank ist neuer. Keine Migration ausgeführt."
                )
            applied_versions = {row[0] for row in applied}
            for version, name, source, checksum in migrations:
                current = name
                item = {"version": version, "file": name}
                if version in applied_versions:
                    result["skipped"].append(item)
                    continue
                with conn.transaction():
                    conn.execute(source)
                    conn.execute(
                        "INSERT INTO schema_version (version, filename, checksum) VALUES (%s, %s, %s)",
                        (version, name, checksum),
                    )
                result["applied"].append(item)
                logger.info("Migration angewendet: %s", name)
    except (MigrationError, OSError, psycopg.Error, ValueError) as exc:
        # Connection exceptions can contain credentials; don't emit their text.
        detail = str(exc) if isinstance(exc, MigrationError) else type(exc).__name__
        if isinstance(exc, psycopg.Error) and exc.sqlstate:
            detail += f" (SQLSTATE {exc.sqlstate})"
        result.update(status="error", error=f"{current or 'Migrationen'}: {detail}")
        logger.error("%s", result["error"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Hugo-Datenbank initialisieren oder aktualisieren")
    parser.add_argument("--env-file", help="Standard: .env im Projektordner, sofern vorhanden")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    load_environment(args.env_file)
    result = run_migrations()
    if result["status"] != "ok":
        return 1
    logger.info("Schema aktuell: %d angewendet, %d bereits vorhanden", len(result["applied"]), len(result["skipped"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
