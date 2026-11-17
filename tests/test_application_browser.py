"""Opt-in end-to-end checks with app.dev, real sessions and disposable PostgreSQL.

No model or external calendar calls. The server is always terminated afterwards.
"""

import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

import httpx
import psycopg
import pytest

from app import migrate
from app.passwords import hash_password
from test_migrations import database

pytestmark = pytest.mark.skipif(os.getenv("HUGO_BROWSER_TESTS") != "1", reason="Opt-in browser checks")


@pytest.mark.parametrize("width", [1440, 390])
def test_real_start_login_and_typed_answers(database, tmp_path, width):
    from playwright.sync_api import sync_playwright
    assert migrate.run_migrations(database)["status"] == "ok"
    with psycopg.connect(database) as conn:
        tid = conn.execute("INSERT INTO threads (title) VALUES ('Synthetisches Browserprojekt') RETURNING id").fetchone()[0]
        sid = conn.execute("INSERT INTO suggestions (thread_id, kind, content, priority) VALUES (%s, 'status_check', 'Wie ist der aktuelle Stand?', 5) RETURNING id", (tid,)).fetchone()[0]
        conn.cursor().executemany("INSERT INTO suggestions (content, priority) VALUES (%s, 1)",
                                  [(f"Allgemeine Browserentscheidung {i}",) for i in range(11)])
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    password = secrets.token_urlsafe(24)
    env = {**os.environ, "DATABASE_URL": database, "HUGO_PASSWORD_HASH": hash_password(password),
           "HUGO_COOKIE_SECURE": "false", "HUGO_WEB_SEARCH_ENABLED": "false", "HUGO_MODEL_PROVIDER": "api"}
    log = (tmp_path / "app.log").open("w")
    server = subprocess.Popen([sys.executable, "-m", "app.dev", "--no-reload", "--port", str(port)],
                              cwd=Path(__file__).parents[1] / "backend", env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        ready_until = time.monotonic() + 30
        while True:
            if server.poll() is not None:
                pytest.fail("Development server exited before readiness; inspect temporary app.log")
            try:
                if httpx.get(url + "/health", timeout=1).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if time.monotonic() > ready_until:
                pytest.fail("Development server did not become ready")
            time.sleep(.2)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("HUGO_BROWSER_EXECUTABLE", "/usr/bin/chromium"), headless=True)
            context = browser.new_context(viewport={"width": width, "height": 900})
            page = context.new_page()
            page.goto(url + "/ui/heute")
            assert "/ui/login" in page.url
            page.locator('input[name="password"]').fill(password)
            with page.expect_navigation():
                page.get_by_role("button", name="Anmelden", exact=True).click()
            assert page.get_by_role("button", name="Pausiert", exact=True).is_visible()
            assert page.get_by_text("Seite 1 von 2", exact=True).is_visible()
            with psycopg.connect(database) as conn:
                assert conn.execute("SELECT count(*) FROM suggestions WHERE delivery_status='pending'").fetchone()[0] == 2
            with page.expect_navigation():
                page.get_by_role("link", name="Weitere Meldungen", exact=True).click()
            assert "page=2" in page.url
            with page.expect_navigation():
                page.get_by_role("button", name="Bestätigen", exact=True).first.click()
            assert "page=2" in page.url
            with psycopg.connect(database) as conn:
                assert conn.execute("SELECT count(*) FROM suggestion_responses WHERE answer='accepted'").fetchone()[0] == 1
            page.goto(url + "/ui/heute")
            with page.expect_navigation():
                page.get_by_role("button", name="Pausiert", exact=True).click()
            with psycopg.connect(database) as conn:
                assert conn.execute("SELECT paused, last_progress_on, last_confirmed_at IS NOT NULL FROM threads WHERE id=%s", (tid,)).fetchone() == (True, None, True)
                assert conn.execute("SELECT answer FROM suggestion_responses WHERE suggestion_id=%s", (sid,)).fetchone()[0] == "paused"
            page.goto(url + f"/ui/threads/{tid}")
            with page.expect_navigation():
                page.get_by_role("button", name="Vorhaben fortsetzen", exact=True).click()
            with psycopg.connect(database) as conn:
                assert not conn.execute("SELECT paused FROM threads WHERE id=%s", (tid,)).fetchone()[0]
                sid2 = conn.execute("INSERT INTO suggestions (thread_id, kind, content, priority) VALUES (%s, 'status_check', 'Ist das Vorhaben inzwischen abgeschlossen?', 5) RETURNING id", (tid,)).fetchone()[0]
            page.goto(url + "/ui/heute")
            with page.expect_navigation():
                page.get_by_role("button", name="Erledigt", exact=True).click()
            with psycopg.connect(database) as conn:
                assert conn.execute("SELECT status FROM threads WHERE id=%s", (tid,)).fetchone()[0] == "completed"
                assert conn.execute("SELECT answer FROM suggestion_responses WHERE suggestion_id=%s", (sid2,)).fetchone()[0] == "completed"
                second = conn.execute("INSERT INTO threads (title) VALUES ('Zweites Browserprojekt') RETURNING id").fetchone()[0]
                qid = conn.execute("INSERT INTO suggestions (thread_id, kind, content, allow_free_text, priority) VALUES (%s, 'question', 'Wie viel Arbeitszeit benötigst du ungefähr?', TRUE, 5) RETURNING id", (second,)).fetchone()[0]
            page.goto(url + "/ui/heute")
            page.locator(f"#reply-{qid}").fill("Ungefähr zwei Tage.")
            assert page.evaluate("document.body.scrollWidth <= innerWidth + 1")
            artifacts = Path(os.getenv("HUGO_BROWSER_ARTIFACTS", str(tmp_path)))
            artifacts.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(artifacts / f"real-today-{width}.png"), full_page=False)
            with page.expect_navigation():
                page.get_by_role("button", name="Antworten", exact=True).click()
            with psycopg.connect(database) as conn:
                assert conn.execute("SELECT response_text, source FROM suggestion_responses WHERE suggestion_id=%s", (qid,)).fetchone() == ("Ungefähr zwei Tage.", "ui")
                assert conn.execute("SELECT last_response_at IS NOT NULL, last_progress_on FROM threads WHERE id=%s", (second,)).fetchone() == (True, None)
                assert conn.execute("SELECT count(*) FROM thread_events WHERE origin='user_decision'").fetchone()[0] >= 4
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)
        log.close()
