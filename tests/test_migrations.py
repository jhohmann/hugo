"""Real PostgreSQL tests for fresh installs, adoption and safe updates."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app import migrate
from app.storage.database import DATABASE_URL


@pytest.fixture
def database():
    try:
        admin = psycopg.connect(DATABASE_URL, connect_timeout=2, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL nicht erreichbar")
    name = "test_migrate_" + uuid4().hex
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield make_conninfo(DATABASE_URL, dbname=name)
    finally:
        admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
        admin.close()


@pytest.fixture
def migration_files(tmp_path):
    baseline = migrate.get_migrations_dir() / "001_initial.sql"
    (tmp_path / baseline.name).write_text(baseline.read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def test_fresh_install_and_repeat(database):
    result = migrate.run_migrations(database)
    assert result["status"] == "ok"
    assert [m["version"] for m in result["applied"]] == [1, 2, 3, 4, 5]
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0] == 17
        assert conn.execute("SELECT checksum FROM schema_version").fetchone()[0]
        conn.execute("INSERT INTO conversations (title) VALUES ('preserve me')")
    repeated = migrate.run_migrations(database)
    assert repeated["status"] == "ok" and repeated["applied"] == []
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT title FROM conversations").fetchone()[0] == "preserve me"


def test_adopt_complete_unversioned_development_database(database):
    baseline = (migrate.get_migrations_dir() / "001_initial.sql").read_text(encoding="utf-8")
    with psycopg.connect(database) as conn:
        conn.execute(baseline)
        conn.execute("INSERT INTO conversations (title) VALUES ('existing conversation')")
        conn.execute("INSERT INTO threads (title, event_start, event_end, act_by) VALUES ('existing plan', '2027-03-15', '2027-03-29', '2027-03-01')")
        conn.execute("INSERT INTO auth_sessions VALUES ('token hash', 'password version', NOW(), NOW() + INTERVAL '1 day')")
        before = {table: conn.execute(sql.SQL("SELECT row_to_json(t) FROM {} t").format(sql.Identifier(table))).fetchall()
                  for table in ("conversations", "threads", "auth_sessions")}
    assert migrate.run_migrations(database)["status"] == "ok"
    with psycopg.connect(database) as conn:
        for table, rows in before.items():
            current = conn.execute(sql.SQL("SELECT row_to_json(t) FROM {} t").format(sql.Identifier(table))).fetchall()
            assert len(current) == len(rows)
            for (before,), (after,) in zip(rows, current):
                assert all(after[key] == value for key, value in before.items())


def test_partial_old_schema_is_not_silently_marked_current(database):
    with psycopg.connect(database) as conn:
        conn.execute("CREATE TABLE memories (id bigint PRIMARY KEY, content text)")
        conn.execute("INSERT INTO memories VALUES (1, 'keep this')")
    assert migrate.run_migrations(database)["status"] == "error"
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT content FROM memories").fetchone()[0] == "keep this"
        assert conn.execute("SELECT count(*) FROM schema_version").fetchone()[0] == 0
        assert conn.execute("SELECT to_regclass('public.threads')").fetchone()[0] is None


def test_future_migration_failure_rolls_back_and_can_be_retried(database, migration_files):
    assert migrate.run_migrations(database, directory=migration_files)["status"] == "ok"
    future = migration_files / "002_test.sql"
    future.write_text("ALTER TABLE threads ADD COLUMN test_note TEXT; SELECT * FROM missing_test_table;", encoding="utf-8")
    assert migrate.run_migrations(database, directory=migration_files)["status"] == "error"
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT count(*) FROM schema_version").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM information_schema.columns WHERE table_name='threads' AND column_name='test_note'").fetchone()[0] == 0
    future.write_text("ALTER TABLE threads ADD COLUMN test_note TEXT;", encoding="utf-8")
    result = migrate.run_migrations(database, directory=migration_files)
    assert result["status"] == "ok" and result["applied"][0]["version"] == 2


def test_checksum_change_and_older_checkout_are_rejected(database, migration_files):
    assert migrate.run_migrations(database, directory=migration_files)["status"] == "ok"
    baseline = migration_files / "001_initial.sql"
    original = baseline.read_text(encoding="utf-8")
    baseline.write_text(original + "\n-- edited after application\n", encoding="utf-8")
    assert migrate.run_migrations(database, directory=migration_files)["status"] == "error"
    baseline.write_text(original, encoding="utf-8")
    future = migration_files / "002_test.sql"
    future.write_text("SELECT 1;", encoding="utf-8")
    assert migrate.run_migrations(database, directory=migration_files)["status"] == "ok"
    future.unlink()
    assert migrate.run_migrations(database, directory=migration_files)["status"] == "error"


def test_windows_newlines_have_the_same_checksum(database, migration_files):
    assert migrate.run_migrations(database, directory=migration_files)["status"] == "ok"
    baseline = migration_files / "001_initial.sql"
    baseline.write_bytes(baseline.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
    assert migrate.run_migrations(database, directory=migration_files)["status"] == "ok"


def test_concurrent_runners_apply_once(database):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: migrate.run_migrations(database), range(2)))
    assert all(result["status"] == "ok" for result in results)
    assert sum(len(result["applied"]) for result in results) == 5


def test_duplicate_versions_rejected_before_connect(tmp_path):
    (tmp_path / "001_one.sql").write_text("SELECT 1;")
    (tmp_path / "001_two.sql").write_text("SELECT 2;")
    result = migrate.run_migrations("invalid connection", directory=tmp_path)
    assert result["status"] == "error" and "eindeutige" in result["error"]


def test_failed_migration_cli_has_nonzero_exit(monkeypatch):
    monkeypatch.setattr("sys.argv", ["migrate"])
    monkeypatch.setattr(migrate, "load_environment", lambda *_: None)
    monkeypatch.setattr(migrate, "run_migrations", lambda: {"status": "error"})
    assert migrate.main() == 1


def test_failed_migration_prevents_dev_server_start(monkeypatch):
    from app import dev
    monkeypatch.setattr("sys.argv", ["dev"])
    monkeypatch.setattr(dev, "load_environment", lambda *_: None)
    monkeypatch.setattr(dev, "run_migrations", lambda: {"status": "error"})
    assert dev.main() == 1


def test_thread_tags_persistence_filtering_and_atomic_updates(database, monkeypatch):
    from app.storage import threads

    assert migrate.run_migrations(database)["status"] == "ok"
    monkeypatch.setattr(threads, "get_connection", lambda: psycopg.connect(database))
    vector = [1.0] + [0.0] * 383
    monkeypatch.setattr(threads, "embed_document", lambda _: vector)
    monkeypatch.setattr(threads, "embed_query", lambda _: vector)

    work = threads.create_thread("Projekt", status="active", tags=["arbeit", "arbeit"], preparation_weeks=4)
    private = threads.create_thread("Urlaub", tags=["privat"])
    mixed = threads.create_thread("Fortbildung", tags=["privat", "arbeit"])
    other = threads.create_thread("Noch offen")
    closed = threads.create_thread("Erledigt", status="completed", tags=["arbeit"])
    assert threads.get_thread(work)["tags"] == ["arbeit"]
    assert threads.get_thread(other)["tags"] == []
    assert {t["id"] for t in threads.list_threads(tag="privat")} == {private, mixed}
    assert {t["id"] for t in threads.list_threads(tag="arbeit", open_only=True)} == {work, mixed}
    assert [t["id"] for t in threads.list_threads(tag="arbeit", status="active")] == [work]
    found = threads.search_threads("Projekt", status="active", tag="arbeit")
    assert len(found) == 1 and found[0]["id"] == work
    assert found[0]["preparation_weeks"] == 4
    assert found[0]["tags"] == ["arbeit"] and found[0]["similarity"] == 1.0
    assert threads.update_thread(work, title="Neuer Titel", tags=None)["tags"] == ["arbeit"]
    assert threads.update_thread(work, tags=["privat", "arbeit"])["tags"] == ["arbeit", "privat"]
    assert threads.update_thread(work, tags=[])["tags"] == []
    assert threads.get_thread(private)["tags"] == ["privat"]

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        threads.update_thread(private, tags=["arbeit"], source_message_id=-1)
    assert threads.get_thread(private)["tags"] == ["privat"]
    with psycopg.connect(database) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute("INSERT INTO thread_tags VALUES (%s, 'unknown')", (private,))
        conn.execute("DELETE FROM threads WHERE id = %s", (closed,))
        assert conn.execute("SELECT count(*) FROM thread_tags WHERE thread_id = %s", (closed,)).fetchone()[0] == 0
