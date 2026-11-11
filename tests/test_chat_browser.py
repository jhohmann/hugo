"""Opt-in layout smoke test: HUGO_BROWSER_TESTS=1 and local Edge/Playwright."""

import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape
import pytest


@pytest.mark.skipif(os.getenv("HUGO_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("mobile", [False, True])
def test_chat_scroll_and_visible_composer(mobile):
    playwright = pytest.importorskip("playwright.sync_api")
    web = Path(__file__).resolve().parents[1] / "backend" / "app" / "web"
    templates = Environment(loader=FileSystemLoader(web / "templates"), autoescape=select_autoescape())
    templates.filters.update(de_datetime=str, source_links=lambda value: value)
    messages = [
        {"role": "assistant" if i % 2 else "user", "content": f"Nachricht {i}: " + "Langer Verlauf. " * 30}
        for i in range(40)
    ]
    html = templates.get_template("chat.html").render(
        nav_active="chat", conversations=[{"id": 7, "preview": "Nächste Schritte für den Umbau",
                                            "last_activity": "09.11.2026", "threads": [{"id": 42, "title": "Arbeitszimmer umbauen"}]}], conversation_id=7,
        referenced_threads=[{"id": 42, "title": "Arbeitszimmer umbauen"}],
        available_threads=[{"id": 42, "title": "Arbeitszimmer umbauen"}],
        messages=messages, draft="", error=None,
        model_usage={"provider": "chatgpt", "connected": True, "limited": True,
                     "fallback": True, "api_ready": True, "fallback_model": "gpt-5-mini", "retry_at": None,
                     "last": {"route": "api", "model": "gpt-5-mini", "input_tokens": 120, "output_tokens": 20}},
    )
    from app.web import formatting as fmt
    templates.filters["de_date"] = fmt.de_date
    templates.filters["de_datetime"] = fmt.de_datetime
    thread_html = templates.get_template("thread_detail.html").render(
        nav_active="threads", fmt=fmt, suggestions=[],
        thread={"id": 42, "title": "Arbeitszimmer umbauen", "status": "active", "priority": 4,
                "description": "Mehr Platz für konzentriertes Arbeiten. Der Zeitplan hängt noch vom Angebot der Schreinerei ab.",
                "next_action": "Angebot prüfen und Ausführung abstimmen", "tags": ["privat"],
                "waiting_for": "Angebot der Schreinerei", "created_at": datetime(2026, 11, 1), "updated_at": datetime(2026, 11, 9)},
        thread_chats={"page": 1, "has_more": False, "items": [{"id": 7, "preview": "Nächste Schritte für den Umbau",
                      "last_linked": datetime(2026, 11, 9, 13, 30), "has_older": False,
                      "messages": [{"role": "user", "content": "V-42: Das Angebot kommt am Freitag. Was bedeutet das für den Zeitplan?"},
                                   {"role": "assistant", "content": "Dann lässt sich die Ausführung erst nach der Prüfung verbindlich abstimmen. Entscheidend ist, ob der vorgesehene Termin danach noch verfügbar ist."}]}]},
    )
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 390 if mobile else 1280, "height": 844},
                                is_mobile=mobile, has_touch=mobile)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def serve(route):
            path = urlsplit(route.request.url).path
            if path == "/ui/chat/7":
                route.fulfill(body=html, content_type="text/html; charset=utf-8")
            elif path == "/ui/threads/42":
                route.fulfill(body=thread_html, content_type="text/html; charset=utf-8")
            elif path.startswith("/static/"):
                route.fulfill(path=str(web / path.removeprefix("/")))
            else:
                route.abort()

        page.route("**/*", serve)
        # Model keyboard occlusion independently of the CSS/layout viewport.
        if mobile:
            page.add_init_script("""
                const viewport = new EventTarget();
                Object.assign(viewport, {height: 844, offsetTop: 0, scale: 1});
                Object.defineProperty(window, 'visualViewport', {value: viewport});
                window.resizeKeyboard = (height, top) => {
                    Object.assign(viewport, {height, offsetTop: top});
                    viewport.dispatchEvent(new Event('resize'));
                    viewport.dispatchEvent(new Event('scroll'));
                };
            """)
        page.goto("http://testserver/ui/chat/7")
        page.locator(".model-usage summary").click()
        assert page.get_by_text("Das verbleibende Abo-Kontingent ist hier nicht abrufbar.", exact=False).is_visible()
        assert page.evaluate("document.body.scrollWidth <= innerWidth + 1")
        Path("logs").mkdir(exist_ok=True)
        page.screenshot(path=f"logs/model-usage-{'mobile' if mobile else 'desktop'}.png")
        page.locator(".model-usage summary").click()
        at_end = """() => { const m = document.querySelector('#messages');
            return m.scrollHeight - m.scrollTop - m.clientHeight < 2; }"""
        page.wait_for_function(at_end)
        assert page.locator("#chat-message").evaluate("e => getComputedStyle(e).borderRadius") == "10px"
        assert page.locator(".main-nav .active").evaluate("e => getComputedStyle(e).borderRadius") == "10px"
        assert page.locator(".chat-form button").evaluate("e => getComputedStyle(e).borderRadius") == "10px"
        page.locator("#messages").evaluate("e => e.scrollTop = 120")
        page.wait_for_function("document.querySelector('#messages').scrollTop === 120")
        # Allow the native scroll event before resizing.
        page.evaluate("() => new Promise(requestAnimationFrame)")
        if mobile:
            page.locator("#chat-message").focus()
            page.evaluate("resizeKeyboard(420, 60)")
        else:
            page.set_viewport_size({"width": 1000, "height": 600})
        page.wait_for_function("document.querySelector('.chat-form').getBoundingClientRect().bottom <= " + ("481" if mobile else "601"))
        assert page.locator("#messages").evaluate("e => e.scrollTop") == 120
        assert page.evaluate("document.body.scrollWidth <= innerWidth + 1 && window.scrollY === 0")
        page.locator("#messages").evaluate("e => e.scrollTop = e.scrollHeight")
        page.wait_for_function(at_end)
        page.evaluate("() => new Promise(requestAnimationFrame)")
        if mobile:
            page.evaluate("resizeKeyboard(360, 0)")
        else:
            page.set_viewport_size({"width": 1000, "height": 500})
        page.wait_for_function("document.body.getBoundingClientRect().height <= " + ("360" if mobile else "500"))
        page.wait_for_function(at_end)
        assert page.locator("#messages").bounding_box()["height"] > 30
        composer = page.locator(".chat-form").bounding_box()
        assert composer["y"] + composer["height"] <= (361 if mobile else 501)
        Path("logs").mkdir(exist_ok=True)
        page.screenshot(path=f"logs/chat-{'mobile-keyboard' if mobile else 'desktop'}.png")
        page.locator("#chat-thread").select_option("42")
        assert page.locator("#chat-message").input_value() == "V-42 "
        page.locator("#chat-thread").select_option("42")
        assert page.locator("#chat-message").input_value() == "V-42 "
        page.goto("http://testserver/ui/threads/42")
        page.set_viewport_size({"width": 390 if mobile else 1280, "height": 900})
        assert page.get_by_text("V-42", exact=True).count() >= 1
        assert page.locator(".thread-message-list .message").count() == 2
        assert page.evaluate("document.body.scrollWidth <= innerWidth + 1")
        assert page.locator(".thread-chat-actions a").get_attribute("href") == "/ui/chat?thread_id=42"
        page.screenshot(path=f"logs/thread-chat-{'mobile' if mobile else 'desktop'}.png", full_page=True)
        if not mobile:
            page.emulate_media(color_scheme="dark")
            page.screenshot(path="logs/thread-chat-dark.png", full_page=True)
        assert not errors
        browser.close()
