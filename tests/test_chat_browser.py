"""Opt-in layout smoke test: HUGO_BROWSER_TESTS=1 and local Edge/Playwright."""

import os
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
        nav_active="chat", conversations=[], conversation_id=7,
        messages=messages, draft="", error=None,
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
        page.wait_for_function(at_end)
        assert page.locator("#messages").bounding_box()["height"] > 30
        composer = page.locator(".chat-form").bounding_box()
        assert composer["y"] + composer["height"] <= (361 if mobile else 501)
        Path("logs").mkdir(exist_ok=True)
        page.screenshot(path=f"logs/chat-{'mobile-keyboard' if mobile else 'desktop'}.png")
        assert not errors
        browser.close()
