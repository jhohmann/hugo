"""
Idempotente Migrations-Runner für Hugo.

Führt SQL-Migrationen aus `backend/migrations/` in korrekter Reihenfolge aus.
Jede Migration wird nur einmal pro Datenbank-Instanz ausgeführt (tracked via `schema_version` Tabelle).
"""

import logging
import os
from pathlib import Path

import psycopg

logger = logging.getLogger(__name__)


def get_migrations_dir() -> Path:
    """Gibt das Migrationsverzeichnis zurück."""
    return Path(__file__).parent.parent / "migrations"


def get_migration_files() -> list[tuple[int, Path]]:
    """
    Liest alle SQL-Migrationsdateien, sortiert nach Nummer.
    Erwartet: 00X_*.sql Format
    """
    migrations_dir = get_migrations_dir()
    files = []
    
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        try:
            # Extrahiere Versionsnummer aus Dateiname (z.B. "002_embeddings.sql" → 2)
            version_str = sql_file.stem.split("_")[0]
            version = int(version_str)
            files.append((version, sql_file))
        except (ValueError, IndexError):
            logger.warning(f"Skipped file with unexpected name format: {sql_file.name}")
    
    return files


def create_schema_version_table(conn):
    """Erstellt die `schema_version` Tabelle, falls sie nicht existiert."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                id SERIAL PRIMARY KEY,
                version INT NOT NULL UNIQUE,
                filename TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT NOW()
            )
            """
        )
    conn.commit()


def run_migrations(database_url: str | None = None) -> dict:
    """
    Führt alle ausstehenden Migrationen aus.
    
    Args:
        database_url: PostgreSQL Verbindungs-String
                      (Default: DATABASE_URL Umgebungsvariable oder dev-default)
    
    Returns:
        dict mit 'status' ('ok' oder 'error'), 'applied' (Liste), 'skipped' (Liste), 'error' (falls error)
    """
    if database_url is None:
        database_url = os.getenv("DATABASE_URL", "postgresql://hugo:hugo_dev@localhost:5432/hugo")
    
    result = {
        "status": "ok",
        "applied": [],
        "skipped": [],
        "error": None,
    }
    
    try:
        conn = psycopg.connect(database_url)
        logger.info("Connected to database")
        
        # Erstelle schema_version Tabelle
        create_schema_version_table(conn)
        
        # Lese alle Migration-Dateien
        migrations = get_migration_files()
        logger.info(f"Found {len(migrations)} migration files")
        
        # Lese bereits angewendete Versionen
        with conn.cursor() as cur:
            cur.execute("SELECT version FROM schema_version ORDER BY version")
            applied_versions = {row[0] for row in cur.fetchall()}
        
        # Führe ausstehende Migrationen aus
        for version, filepath in migrations:
            if version in applied_versions:
                logger.info(f"Migration {version} ({filepath.name}) already applied")
                result["skipped"].append({"version": version, "file": filepath.name})
                continue
            
            try:
                sql_content = filepath.read_text()
                logger.info(f"Applying migration {version} ({filepath.name})")
                
                with conn.cursor() as cur:
                    # Führe SQL aus
                    cur.execute(sql_content)
                    # Markiere Migration als angewendet
                    cur.execute(
                        "INSERT INTO schema_version (version, filename) VALUES (%s, %s)",
                        (version, filepath.name)
                    )
                
                conn.commit()
                result["applied"].append({"version": version, "file": filepath.name})
                logger.info(f"Migration {version} applied successfully")
                
            except Exception as e:
                conn.rollback()
                error_msg = f"Failed to apply migration {version} ({filepath.name}): {str(e)}"
                logger.error(error_msg)
                result["status"] = "error"
                result["error"] = error_msg
                conn.close()
                return result
        
        conn.close()
        logger.info("All migrations completed successfully")
        
    except Exception as e:
        error_msg = f"Database connection error during migrations: {str(e)}"
        logger.error(error_msg)
        result["status"] = "error"
        result["error"] = error_msg
    
    return result


if __name__ == "__main__":
    # Lokales Testen: python -m app.migrate
    logging.basicConfig(level=logging.INFO)
    result = run_migrations()
    print(f"\nMigration Result:\n{result}")
