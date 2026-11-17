"""Opt-in UI checks against simulated storage, using a local browser executable."""

import os
from datetime import timezone
from pathlib import Path

import pytest

from test_web import client, fake_storage
from app.web import routes

pytestmark = pytest.mark.skipif(os.getenv("HUGO_BROWSER_TESTS") != "1", reason="Opt-in browser checks")


@pytest.mark.parametrize("width,height", [(1440, 1000), (390, 844)])
def test_decision_form_on_desktop_and_phone(client, fake_storage, monkeypatch, tmp_path, width, height):
    from playwright.sync_api import sync_playwright
    calls = []
    fake_storage["threads"][0]["updated_at"] = fake_storage["threads"][0]["updated_at"].replace(tzinfo=timezone.utc)
    monkeypatch.setattr(routes, "update_thread", lambda tid, **kw: calls.append((tid, kw)) or {"id": tid})
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("HUGO_BROWSER_EXECUTABLE", "/usr/bin/chromium"), headless=True)
        context = browser.new_context(viewport={"width": width, "height": height}, timezone_id="America/Los_Angeles")
        def serve(route):
            request = route.request
            response = client.request(request.method, request.url, content=request.post_data,
                                      headers={"Content-Type": request.headers.get("content-type", ""),
                                               "Origin": "http://testserver"})
            route.fulfill(status=response.status_code, body=response.content,
                          content_type=response.headers.get("content-type", "text/plain"))
        context.route("**/*", serve)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://testserver/ui/threads/5#entscheidung")
        page.locator("#entscheidung").scroll_into_view_if_needed()
        page.locator("#entscheidung").scroll_into_view_if_needed()
        assert page.locator("#decision-deadline").input_value() == "2027-03-01"
        assert page.evaluate("document.body.scrollWidth <= innerWidth + 1")
        page.locator("#decision-deadline").fill("2027-03-28")
        screenshot = Path(os.getenv("HUGO_BROWSER_ARTIFACTS", str(tmp_path)))
        screenshot.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot / f"thread-decision-{width}.png"), full_page=True)
        with page.expect_navigation():
            page.get_by_role("button", name="Frist verbindlich setzen").click()
        assert calls[0][0] == 5
        assert calls[0][1]["deadline"].isoformat() == "2027-03-28T23:59:59.999999+02:00"
        assert calls[0][1]["user_decision"] is True
        with page.expect_navigation():
            page.get_by_role("button", name="Als erledigt markieren").click()
        assert calls[-1][1]["status"] == "completed"
        assert not errors
        browser.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_typed_today_cards_in_browser(client, fake_storage, monkeypatch, tmp_path, width):
    from playwright.sync_api import sync_playwright
    base = fake_storage["suggestions"][0]
    fake_storage["suggestions"] = [
        {**base, "id": 51, "kind": "status_check", "revision": 1,
         "content": "Wie ist der Stand deiner Reiseplanung?", "reason": "Seit dem letzten Gespräch fehlt eine aktuelle Rückmeldung."},
        {**base, "id": 52, "kind": "question", "revision": 1,
         "content": "Wie viel Arbeitszeit benötigst du ungefähr?", "reason": "Die grobe Schätzung hilft, das passende Zeitfenster einzuordnen.", "response_options": ["Ein Tag", "Eine Woche"], "allow_free_text": True},
    ]
    calls = []
    monkeypatch.setattr(routes, "answer_suggestion", lambda sid, answer, **kw: calls.append((sid, answer, kw)) or {"answered": True})
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("HUGO_BROWSER_EXECUTABLE", "/usr/bin/chromium"), headless=True)
        context = browser.new_context(viewport={"width": width, "height": 900})
        def serve(route):
            request = route.request
            response = client.request(request.method, request.url, content=request.post_data,
                                      headers={"Content-Type": request.headers.get("content-type", ""), "Origin": "http://testserver"})
            route.fulfill(status=response.status_code, body=response.content,
                          content_type=response.headers.get("content-type", "text/plain"))
        context.route("**/*", serve)
        page = context.new_page()
        page.goto("http://testserver/ui/heute")
        assert page.get_by_role("button", name="Bin dran", exact=True).is_visible()
        assert page.get_by_role("button", name="Pausiert", exact=True).is_visible()
        assert page.get_by_role("button", name="Eine Woche", exact=True).is_visible()
        assert page.evaluate("document.body.scrollWidth <= innerWidth + 1")
        page.locator("#reply-52").fill("Etwa zwei Wochen")
        screenshot = Path(os.getenv("HUGO_BROWSER_ARTIFACTS", str(tmp_path)))
        screenshot.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot / f"typed-today-{width}.png"), full_page=True)
        with page.expect_navigation():
            page.get_by_role("button", name="Antworten", exact=True).click()
        assert calls[0] == (52, "text", {"expected_revision": 1, "text": "Etwa zwei Wochen", "source": "ui"})
        with page.expect_navigation():
            page.get_by_role("button", name="Bin dran", exact=True).click()
        assert calls[-1][0:2] == (51, "in_progress")
        browser.close()
