"""Settings persistence, cross-process use and protected UI; no model calls."""

from copy import deepcopy
import os
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
import pytest

from app import settings, worker
from app.agent import model_client, model_usage
from app.agent.chat_context import history_budget
from app.agent.web_research import web_search_limit
from app.storage import settings as storage
from app.storage.settings import read_settings as real_read, save_settings as real_save
from app.web import routes
from test_migrations import database
from test_web import client, fake_storage


@pytest.fixture
def preferences(monkeypatch):
    state = {"values": {}, "revision": 0, "updated_at": None}

    def save(values, revision):
        if revision != state["revision"]:
            raise storage.SettingsConflict("Die Einstellungen wurden inzwischen geändert. Bitte neu laden.")
        state.update(values=dict(values), revision=revision + 1)

    monkeypatch.setattr(storage, "read_settings", lambda: deepcopy(state))
    monkeypatch.setattr(storage, "save_settings", save)
    monkeypatch.setattr(model_usage, "public_status", lambda: {
        "connected": True, "limited": False, "last": {}, "retry_at": None,
    })
    monkeypatch.setattr(routes.calendar_client, "is_configured", lambda: True)
    monkeypatch.setattr(routes.calendar_client, "is_connected", lambda: True)
    monkeypatch.setattr(routes, "count_open_suggestions", lambda: 2)
    return state


def form_values():
    return {key: spec[0] for key, spec in settings.FIELDS.items()}


def test_settings_store_persists_and_rejects_stale_updates(database, monkeypatch):
    from app import migrate
    assert migrate.run_migrations(database)["status"] == "ok"
    monkeypatch.setattr(storage, "get_connection", lambda: psycopg.connect(database))
    monkeypatch.setattr(storage, "read_settings", real_read)
    monkeypatch.setattr(storage, "save_settings", real_save)
    assert settings.current()["revision"] == 0
    values = {**form_values(), "HUGO_MODEL": "saved-model", "SCHEDULER_HOUR": "15"}
    settings.save(values, 0)
    assert settings.current()["values"]["HUGO_MODEL"] == "saved-model"
    with pytest.raises(storage.SettingsConflict):
        settings.save(form_values(), 0)
    assert worker.configured_schedule() == (15, 0)
    settings.reset(1)
    assert real_read()["values"] == {} and real_read()["revision"] == 2


def test_runtime_overrides_and_consistent_snapshot(preferences, monkeypatch):
    monkeypatch.setenv("HUGO_MODEL_PROVIDER", "api")
    settings.save({**form_values(), "HUGO_MODEL_PROVIDER": "chatgpt", "HUGO_CHAT_HISTORY_TOKENS": "3000",
                   "HUGO_WEB_SEARCH_ENABLED": "false", "HUGO_API_FALLBACK_MODEL": "reserve-model"}, 0)
    assert model_client.provider() == "chatgpt"
    assert history_budget() == 3000 and web_search_limit() == 0
    assert model_client.usage_status()["fallback_model"] == "reserve-model"
    with settings.snapshot():
        settings.save(form_values(), 1)
        assert model_client.provider() == "chatgpt"
    assert model_client.provider() == "api"


@pytest.mark.parametrize("key,value", [("HUGO_MODEL", "bad model"), ("HUGO_MODEL_PROVIDER", "unknown"),
    ("HUGO_API_FALLBACK_ENABLED", "yes"), ("SCHEDULER_HOUR", "24"), ("SCHEDULER_MINUTE", "-1"),
    ("HUGO_CHAT_HISTORY_TOKENS", "1999"), ("HUGO_WEB_SEARCH_MAX_CALLS", "11"), ("OPENAI_API_KEY", "secret")])
def test_invalid_settings_never_written(preferences, key, value):
    with pytest.raises(ValueError):
        settings.save({**form_values(), key: value}, 0)
    assert preferences["revision"] == 0


def test_settings_page_save_reset_and_no_secrets(client, fake_storage, preferences, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "DO-NOT-RENDER-API-KEY")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "DO-NOT-RENDER-GOOGLE-SECRET")
    page = client.get("/ui/settings")
    assert page.status_code == 200
    assert "Hugo 0.4.0" in page.text and "Restkontingent nicht abrufbar" in page.text
    assert "Geplant" in page.text and "Google Kalender" in page.text
    assert "Stunde (Europe/Berlin)" in page.text
    assert "DO-NOT-RENDER" not in page.text
    values = form_values()
    del values["HUGO_WEB_SEARCH_ENABLED"]
    saved = client.post("/ui/settings", data={**values, "revision": "0"})
    assert saved.status_code == 200 and "Einstellungen gespeichert" in saved.text
    assert preferences["values"]["HUGO_WEB_SEARCH_ENABLED"] == "false"
    assert client.post("/ui/settings", data={**values, "revision": "0"}).status_code == 409
    assert client.post("/ui/settings", data={**values, "revision": "1", "SCHEDULER_HOUR": "25"}).status_code == 400
    assert preferences["revision"] == 1
    assert client.post("/ui/settings", data={"action": "reset", "revision": "1"}).status_code == 200
    assert preferences["values"] == {}


def test_connection_check_success_and_safe_failure(client, fake_storage, preferences, monkeypatch):
    monkeypatch.setattr(routes.calendar_client, "list_calendars", lambda: [{"id": "test"}])
    assert "1 Kalender erreichbar" in client.post("/ui/settings/calendar-check").text

    def fail():
        raise routes.calendar_client.CalendarError("private upstream detail")
    monkeypatch.setattr(routes.calendar_client, "list_calendars", fail)
    failed = client.post("/ui/settings/calendar-check")
    assert failed.status_code == 502 and "private upstream" not in failed.text


def test_schedule_updates_once_without_duplicate_evaluation_jobs(preferences, monkeypatch):
    from apscheduler.schedulers.blocking import BlockingScheduler

    def inspect(scheduler):
        assert {job.id for job in scheduler.get_jobs()} == {"daily_evaluation", "settings_sync"}
        settings.save({**form_values(), "SCHEDULER_HOUR": "9", "SCHEDULER_MINUTE": "15"}, 0)
        worker.sync_schedule(scheduler)
        job = scheduler.get_job("daily_evaluation")
        assert "hour='9'" in str(job.trigger) and "minute='15'" in str(job.trigger)
        assert str(job.trigger.timezone) == "Europe/Berlin" and job.max_instances == 1 and job.coalesce
        unchanged = job.trigger
        worker.sync_schedule(scheduler)
        assert job.trigger is unchanged
    monkeypatch.setattr(BlockingScheduler, "start", inspect)
    worker.run_worker()


def test_settings_require_login_and_same_origin(fake_storage, preferences, monkeypatch):
    from fastapi.testclient import TestClient
    from app import auth
    from app.main import app
    monkeypatch.setattr(auth, "password_hash", lambda: "configured")
    monkeypatch.setattr(auth.storage, "valid_session", lambda *_: False)
    with TestClient(app, follow_redirects=False) as anonymous:
        assert anonymous.get("/ui/settings").status_code == 303
        assert anonymous.post("/ui/settings", data={"revision": "0"}).status_code in {303, 401, 403}
    monkeypatch.setattr(auth.storage, "valid_session", lambda *_: True)
    with TestClient(app) as authenticated:
        response = authenticated.post("/ui/settings", headers={"Origin": "https://untrusted.example"}, data={"revision": "0"})
        assert response.status_code == 403 and preferences["revision"] == 0


@pytest.mark.skipif(os.getenv("HUGO_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("width", [390, 1280])
def test_settings_browser_save_and_responsive_layout(client, fake_storage, preferences, width):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": width, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def serve(route):
            request = route.request
            url = urlsplit(request.url)
            response = client.request(request.method, url.path + ("?" + url.query if url.query else ""),
                                      content=request.post_data_buffer,
                                      headers={"Content-Type": request.headers.get("content-type", "")},
                                      follow_redirects=False)
            route.fulfill(status=response.status_code, body=response.content,
                          headers=dict(response.headers))
        page.route("**/*", serve)
        page.goto("http://testserver/ui/settings")
        assert page.get_by_role("heading", name="Einstellungen", exact=True).is_visible()
        assert page.get_by_role("link", name="Einstellungen", exact=True).get_attribute("aria-current") == "page"
        assert page.evaluate("document.body.scrollWidth <= innerWidth + 1")
        page.get_by_label("Hauptmodell", exact=False).fill("saved-browser-model")
        page.get_by_role("button", name="Einstellungen speichern", exact=True).click()
        page.get_by_role("status").filter(has_text="Einstellungen gespeichert.").wait_for()
        assert preferences["values"]["HUGO_MODEL"] == "saved-browser-model"
        page.reload()
        assert page.get_by_role("alert").count() == 0
        assert page.get_by_label("Hauptmodell", exact=False).input_value() == "saved-browser-model"
        assert page.evaluate("document.body.scrollWidth <= innerWidth + 1")
        Path("logs").mkdir(exist_ok=True)
        page.screenshot(path=f"logs/settings-{width}.png", full_page=True)
        if width == 1280:
            page.emulate_media(color_scheme="dark")
            page.screenshot(path="logs/settings-dark.png", full_page=True)
        else:
            page.set_viewport_size({"width": 320, "height": 740})
            assert page.evaluate("document.body.scrollWidth <= innerWidth + 1")
        assert not errors
        browser.close()
