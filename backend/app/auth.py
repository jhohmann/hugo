"""Passwort-Anmeldung und gemeinsame Zugriffsschranke für UI und API."""

import logging
import os
from pathlib import Path
from urllib.parse import quote, urlsplit

import psycopg
from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from app.passwords import parse_hash, verify_password
from app.storage import auth as storage

COOKIE = "hugo_session"
REMEMBER_SECONDS = 30 * 24 * 60 * 60
SESSION_SECONDS = 12 * 60 * 60
router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).parent / "web" / "templates")
logger = logging.getLogger(__name__)


def password_hash() -> str | None:
    value = os.getenv("HUGO_PASSWORD_HASH", "")
    try:
        parse_hash(value)
    except ValueError:
        return None
    return value


def secure_cookie() -> bool:
    return os.getenv("HUGO_COOKIE_SECURE", "true").lower() != "false"


def safe_next(value: str) -> str:
    if (value.startswith("/ui/") and not value.startswith("/ui/login")
            and not value.startswith("/ui/logout")
            and not any(c in value for c in ("\\", "\r", "\n"))):
        return value
    return "/ui/heute"


def same_origin(request: Request) -> bool:
    """Browser-Schreibzugriffe nur vom eigenen Origin; CLI nutzt expliziten Header."""
    source = request.headers.get("origin") or request.headers.get("referer")
    if source:
        try:
            parsed = urlsplit(source)
            expected = urlsplit(str(request.base_url))
            return (parsed.scheme, parsed.netloc) == (expected.scheme, expected.netloc)
        except ValueError:
            return False
    return (request.headers.get("x-hugo-request") == "1"
            and request.headers.get("sec-fetch-site") in (None, "same-origin"))


class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if path == "/health" or path.startswith("/static/"):
            return await call_next(request)

        async def guarded():
            configured_hash = password_hash()
            if not configured_hash:
                if path == "/ui/login" and request.method == "GET":
                    return await call_next(request)
                return JSONResponse({"detail": "Hugo-Anmeldung ist noch nicht eingerichtet."}, status_code=503)

            is_login = path == "/ui/login"
            if not is_login:
                token = request.cookies.get(COOKIE, "")
                authenticated = await run_in_threadpool(storage.valid_session, token, configured_hash)
                if not authenticated:
                    if path == "/ui" or path.startswith("/ui/"):
                        target = safe_next(request.url.path + ("?" + request.url.query if request.url.query else ""))
                        return RedirectResponse("/ui/login?next=" + quote(target, safe=""), status_code=303)
                    return JSONResponse({"detail": "Anmeldung erforderlich."}, status_code=401)
            if request.method not in ("GET", "HEAD", "OPTIONS") and not same_origin(request):
                return JSONResponse({"detail": "Ungültiger Anfrage-Ursprung."}, status_code=403)
            return await call_next(request)

        try:
            response = await guarded()
        except psycopg.Error:
            # Do not log exceptions/DSNs, passwords or session cookies.
            logger.error("Datenbankzugriff bei geschützter HTTP-Anfrage fehlgeschlagen")
            response = JSONResponse({"detail": "Hugo ist gerade nicht erreichbar."}, status_code=503)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        return response


def render_login(request, *, next="/ui/heute", error=None, status_code=200):
    return templates.TemplateResponse(
        request, "login.html",
        {"login_page": True, "next": safe_next(next), "error": error},
        status_code=status_code,
    )


@router.get("/ui/login")
def login_page(request: Request, next: str = "/ui/heute"):
    if not password_hash():
        return render_login(request, error="Die Anmeldung ist noch nicht eingerichtet. Bitte HUGO_PASSWORD_HASH konfigurieren.", status_code=503)
    return render_login(request, next=next)


@router.post("/ui/login")
def login(request: Request, password: str = Form(""), remember: bool = Form(False), next: str = Form("/ui/heute")):
    if not storage.allow_login_attempt():
        logger.warning("Anmeldung wegen Versuchslimit abgewiesen")
        response = render_login(request, next=next, error="Zu viele Anmeldeversuche. Bitte in einer Minute erneut versuchen.", status_code=429)
        response.headers["Retry-After"] = "60"
        return response
    configured_hash = password_hash()
    if not configured_hash or not verify_password(password, configured_hash):
        logger.info("Anmeldung mit falschem Passwort abgewiesen")
        return render_login(request, next=next, error="Das Passwort ist nicht richtig.", status_code=401)
    lifetime = REMEMBER_SECONDS if remember else SESSION_SECONDS
    token = storage.create_session(configured_hash, lifetime)
    previous = request.cookies.get(COOKIE)
    if previous:
        storage.delete_session(previous)
    response = RedirectResponse(safe_next(next), status_code=303)
    response.set_cookie(COOKIE, token, max_age=lifetime if remember else None,
                        httponly=True, secure=secure_cookie(), samesite="lax", path="/")
    logger.info("Anmeldung erfolgreich; angemeldet_bleiben=%s", remember)
    return response


@router.post("/ui/logout")
def logout(request: Request):
    storage.delete_session(request.cookies.get(COOKIE, ""))
    logger.info("Sitzung abgemeldet")
    response = RedirectResponse("/ui/login", status_code=303)
    response.delete_cookie(COOKIE, path="/", secure=secure_cookie(), httponly=True, samesite="lax")
    return response
