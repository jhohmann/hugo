"""Google-Calendar-Zugriff: OAuth 2.0 und REST-API (v3).

Bewusst ohne google-api-python-client: die Calendar-API ist
eine schlanke REST-API; httpx ist bereits eine Abhängigkeit.
Tokens werden ausschließlich in der Datenbank gehalten und
niemals an das Sprachmodell übergeben.
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import httpx

from app.storage import google_auth

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://www.googleapis.com/calendar/v3"

# Vollständiger Kalenderzugriff: Lesen, Erstellen, Ändern,
# Löschen — für alle Kalender des Kontos.
SCOPE = "https://www.googleapis.com/auth/calendar"

# Sekunden Puffer vor Ablauf des Access-Tokens.
_EXPIRY_MARGIN = 60

_TIMEOUT = httpx.Timeout(15.0)


class CalendarError(Exception):
    """Basisklasse für Kalenderfehler."""


class CalendarConfigError(CalendarError):
    """GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET fehlen."""


class CalendarNotConnectedError(CalendarError):
    """Kein Google-Konto verbunden oder Token ungültig."""


class EventNotFoundError(CalendarError):
    """Termin existiert nicht (mehr)."""


class GoogleApiError(CalendarError):
    """Fehlerantwort der Google-API."""

    def __init__(self, status_code: int, message: str):
        super().__init__(f"Google-API-Fehler {status_code}: {message}")
        self.status_code = status_code


def _client_id() -> str:
    value = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not value:
        raise CalendarConfigError(
            "GOOGLE_CLIENT_ID ist nicht gesetzt."
        )
    return value


def _client_secret() -> str:
    value = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if not value:
        raise CalendarConfigError(
            "GOOGLE_CLIENT_SECRET ist nicht gesetzt."
        )
    return value


def _redirect_uri() -> str:
    return os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/ui/kalender/auth/callback",
    )


def is_configured() -> bool:
    """OAuth-Client-Daten per Umgebungsvariable vorhanden?"""
    return bool(
        os.getenv("GOOGLE_CLIENT_ID", "").strip()
        and os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    )


def is_connected() -> bool:
    """Gespeicherte Tokens vorhanden?"""
    return google_auth.get_credentials() is not None


def new_oauth_state() -> str:
    """Zufälliger CSRF-State, neustartfest in der DB abgelegt."""
    state = secrets.token_urlsafe(32)
    google_auth.save_oauth_state(state)
    return state


def build_auth_url(state: str) -> str:
    """Google-Authorization-URL für den Consent-Screen."""
    params = {
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        # prompt=consent garantiert ein Refresh-Token,
        # auch bei wiederholtem Verbinden.
        "prompt": "consent",
        "state": state,
    }
    query = httpx.QueryParams(params)
    return f"{AUTH_URL}?{query}"


def exchange_code(code: str, state: str) -> None:
    """Authorization-Code gegen Tokens tauschen und speichern."""
    if not google_auth.consume_oauth_state(state):
        raise CalendarError(
            "Ungültiger oder abgelaufener OAuth-State."
        )
    try:
        response = httpx.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": _client_id(),
                "client_secret": _client_secret(),
                "redirect_uri": _redirect_uri(),
                "grant_type": "authorization_code",
            },
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise GoogleApiError(0, f"Token-Abruf fehlgeschlagen: {exc}")
    if response.status_code != 200:
        raise GoogleApiError(response.status_code, response.text[:500])
    data = response.json()
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        raise GoogleApiError(
            0,
            "Google hat kein Refresh-Token geliefert "
            "(prompt=consent aktiv?)",
        )
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=int(data.get("expires_in", 3600))
    )
    google_auth.save_credentials(
        access_token=data["access_token"],
        refresh_token=refresh_token,
        expires_at=expires_at,
        scopes=data.get("scope", SCOPE),
    )
    logger.info("Google-Konto verbunden.")


def disconnect() -> bool:
    """Verbindung trennen (Tokens aus der DB entfernen)."""
    removed = google_auth.delete_credentials()
    if removed:
        logger.info("Google-Konto getrennt.")
    return removed


def _refresh(credentials: dict) -> dict:
    """Access-Token erneuern und in der DB aktualisieren."""
    try:
        response = httpx.post(
            TOKEN_URL,
            data={
                "client_id": _client_id(),
                "client_secret": _client_secret(),
                "refresh_token": credentials["refresh_token"],
                "grant_type": "refresh_token",
            },
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise GoogleApiError(0, f"Token-Refresh fehlgeschlagen: {exc}")
    if response.status_code != 200:
        # z. B. invalid_grant: Nutzer hat Zugriff widerrufen.
        logger.warning(
            "Token-Refresh abgelehnt (%s)", response.status_code
        )
        raise CalendarNotConnectedError(
            "Das Google-Token wurde abgelehnt. "
            "Bitte das Konto erneut verbinden."
        )
    data = response.json()
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=int(data.get("expires_in", 3600))
    )
    google_auth.update_access_token(data["access_token"], expires_at)
    return {**credentials, "access_token": data["access_token"]}


def _access_token() -> str:
    """Gültiges Access-Token; erneuert es bei Bedarf."""
    credentials = google_auth.get_credentials()
    if credentials is None:
        raise CalendarNotConnectedError(
            "Kein Google-Konto verbunden."
        )
    expires_at = credentials["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if now + timedelta(seconds=_EXPIRY_MARGIN) >= expires_at:
        credentials = _refresh(credentials)
    return credentials["access_token"]


def _request(method: str, path: str, **kwargs) -> httpx.Response:
    """Authentifizierter API-Aufruf mit Fehlerbehandlung."""
    token = _access_token()
    try:
        response = httpx.request(
            method,
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT,
            **kwargs,
        )
    except httpx.HTTPError as exc:
        raise GoogleApiError(0, f"Netzwerkfehler: {exc}")
    if response.status_code == 401:
        raise CalendarNotConnectedError(
            "Google hat den Zugriff abgelehnt (401). "
            "Bitte das Konto erneut verbinden."
        )
    if response.status_code == 404 or response.status_code == 410:
        raise EventNotFoundError("Termin nicht gefunden.")
    if response.status_code >= 400:
        raise GoogleApiError(response.status_code, response.text[:500])
    return response


def list_calendars() -> list[dict]:
    """Alle Kalender des Kontos mit Schreibberechtigungs-Flag."""
    response = _request("GET", "/users/me/calendarList")
    items = response.json().get("items", [])
    return [
        {
            "id": item["id"],
            "summary": item.get("summary", item["id"]),
            "primary": bool(item.get("primary")),
            "access_role": item.get("accessRole", "reader"),
            "writable": item.get("accessRole") in ("owner", "writer"),
        }
        for item in items
    ]


def list_events(
    calendar_id: str,
    time_min: datetime,
    time_max: datetime,
    max_results: int = 50,
) -> list[dict]:
    """Termine eines Kalenders im Zeitraum, aufgeteilt und
    nach Start sortiert. Abgesagte Termine werden übersprungen."""
    response = _request(
        "GET",
        f"/calendars/{calendar_id}/events",
        params={
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": str(max_results),
        },
    )
    items = response.json().get("items", [])
    return [e for e in items if e.get("status") != "cancelled"]


def get_event(calendar_id: str, event_id: str) -> dict:
    """Ein einzelnes Ereignis (inkl. etag/updated)."""
    return _request(
        "GET", f"/calendars/{calendar_id}/events/{event_id}"
    ).json()


def insert_event(calendar_id: str, body: dict) -> dict:
    """Termin anlegen. body kann eine eigene Event-ID
    enthalten (Idempotenz bei Wiederholungen)."""
    return _request(
        "POST", f"/calendars/{calendar_id}/events", json=body
    ).json()


def patch_event(calendar_id: str, event_id: str, body: dict) -> dict:
    """Termin ändern (nur übergebene Felder)."""
    return _request(
        "PATCH",
        f"/calendars/{calendar_id}/events/{event_id}",
        json=body,
    ).json()


def delete_event(calendar_id: str, event_id: str) -> None:
    """Termin löschen. Bereits gelöschte Termine gelten als
    erfolgreich gelöscht (idempotent)."""
    try:
        _request(
            "DELETE", f"/calendars/{calendar_id}/events/{event_id}"
        )
    except EventNotFoundError:
        logger.info(
            "Termin %s war bereits gelöscht.", event_id
        )
