"""Opt-in local Edge checks: HUGO_BROWSER_TESTS=1, Playwright installed."""

import os
from pathlib import Path
from time import monotonic

import pytest

from test_timeline import client

pytestmark = pytest.mark.skipif(os.getenv("HUGO_BROWSER_TESTS") != "1", reason="Opt-in browser checks")


@pytest.fixture
def browser(client, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    monkeypatch.setenv("HUGO_TIMELINE_DEMO", "true")
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        yield browser
        browser.close()


def setup_page(browser, client, **options):
    context = browser.new_context(**options)
    def serve(route):
        response = client.get(route.request.url)
        route.fulfill(status=response.status_code, body=response.content,
                      content_type=response.headers.get("content-type", "text/plain"))
    context.route("**/*", serve)
    return context, context.new_page()


def test_desktop_filters_zoom_details_and_url(browser, client):
    context, page = setup_page(browser, client, viewport={"width": 1440, "height": 1100}, timezone_id="America/Los_Angeles")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://testserver/ui/zeitleiste?demo=1")
    assert page.locator("#timeline-app").is_visible()
    assert page.locator(".tl-row:not(.tl-axis)").count() == 2
    page.select_option("#tl-range", "all")
    assert page.locator(".tl-node.group").count() >= 1
    group = page.locator(".tl-node.group").first
    group.focus()
    assert page.locator("#tl-tooltip").is_visible()
    group.press("Enter")
    assert page.locator("#tl-detail").is_visible()
    assert page.locator(".tl-detail-item").count() > 1
    page.keyboard.press("Escape")
    assert not page.locator("#tl-detail").is_visible()
    page.locator('.tl-layers input[value="idea"]').uncheck()
    assert page.locator(".tl-node.idea").count() == 0
    assert page.locator("#tl-undated-items button").count() == 0
    page.select_option("#tl-status", "inactive")
    assert page.locator(".tl-title").all_text_contents() == ["Werkstattbesuch"]
    page.reload()
    assert page.locator("#tl-status").input_value() == "inactive"
    assert not page.locator('.tl-layers input[value="idea"]').is_checked()
    page.select_option("#tl-status", "all")
    page.select_option("#tl-tag", "arbeit")
    assert page.locator(".tl-row:not(.tl-axis)").count() == 1
    page.select_option("#tl-tag", "all")
    page.locator('.tl-layers input[value="idea"]').check()
    page.select_option("#tl-range", "90")
    page.click("#tl-today")
    Path("logs").mkdir(exist_ok=True)
    page.screenshot(path="logs/timeline-desktop.png", full_page=True)
    assert not errors
    context.close()


def test_mobile_and_no_javascript(browser, client):
    context, page = setup_page(browser, client, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page.goto("http://testserver/ui/zeitleiste?demo=1&range=all")
    assert page.evaluate("document.body.scrollWidth <= innerWidth + 1")
    page.locator(".tl-node.planning").first.tap()
    assert page.locator("#tl-detail").is_visible()
    page.click("#tl-close")
    page.screenshot(path="logs/timeline-mobile.png", full_page=True)
    context.close()
    context, page = setup_page(browser, client, java_script_enabled=False)
    page.goto("http://testserver/ui/zeitleiste?demo=1")
    assert not page.locator("#timeline-app").is_visible()
    assert page.locator("#tl-fallback").is_visible()
    assert "Reiseplanung" in page.locator("#tl-fallback").inner_text()
    context.close()


def test_large_dataset(browser, client):
    context, page = setup_page(browser, client, viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    started = monotonic()
    page.goto("http://testserver/ui/zeitleiste?demo=1&size=large&range=all", timeout=60000)
    assert page.locator(".tl-row:not(.tl-axis)").count() == 100
    assert page.evaluate("JSON.parse(document.querySelector('#timeline-data').textContent).points.length") == 5000
    print(f"100 Spuren / 5000 Punkte: {monotonic() - started:.2f}s bis Browseransicht")
    page.select_option("#tl-range", "30")
    page.click("#tl-today")
    assert page.locator(".tl-node").count() == 5000
    assert not errors
    context.close()
