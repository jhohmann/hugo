"""Allowlisted user preferences. Environment remains the deployment default."""

from contextlib import contextmanager
from contextvars import ContextVar
import logging
import os
import re

from app.storage import settings as storage

logger = logging.getLogger(__name__)
_snapshot = ContextVar("hugo_settings", default=None)

# key: (default, label, minimum, maximum); bounds apply only to integer fields.
FIELDS = {
    "HUGO_MODEL_PROVIDER": ("api", "KI-Zugang", None, None),
    "HUGO_MODEL": ("gpt-5.6-terra", "Hauptmodell", None, None),
    "HUGO_API_FALLBACK_ENABLED": ("false", "API-Reserve", None, None),
    "HUGO_API_FALLBACK_MODEL": ("gpt-5.6-terra", "Reservemodell", None, None),
    "HUGO_CHATGPT_RETRY_SECONDS": ("1800", "Erneuter Abo-Versuch", 60, 86400),
    "HUGO_WEB_SEARCH_ENABLED": ("true", "Webrecherche", None, None),
    "HUGO_WEB_SEARCH_MAX_CALLS": ("3", "Webaktionen je Lauf", 1, 10),
    "HUGO_CHAT_HISTORY_TOKENS": ("12000", "Gesprächsbudget", 2000, 60000),
    "SCHEDULER_HOUR": ("8", "Auswertungsstunde", 0, 23),
    "SCHEDULER_MINUTE": ("0", "Auswertungsminute", 0, 59),
}
BOOLEAN_FIELDS = {"HUGO_API_FALLBACK_ENABLED", "HUGO_WEB_SEARCH_ENABLED"}


def get_value(key, default=None):
    if key not in FIELDS:
        raise KeyError(key)
    overrides = _snapshot.get()
    if overrides is None:
        overrides = storage.read_settings()["values"]
    return overrides.get(key, os.getenv(key, default))


@contextmanager
def snapshot():
    """Use a consistent provider/fallback configuration for one model request."""
    if _snapshot.get() is not None:
        yield
        return
    token = _snapshot.set(storage.read_settings()["values"])
    try:
        yield
    finally:
        _snapshot.reset(token)


def current():
    stored = storage.read_settings()
    return {**stored, "values": {
        key: stored["values"].get(key, os.getenv(key) or spec[0])
        for key, spec in FIELDS.items()
    }, "customized": bool(stored["values"])}


def validate(values):
    if set(values) != set(FIELDS):
        raise ValueError("Unvollständige oder unbekannte Einstellungen. Bitte die Seite neu laden.")
    result = {}
    for key, raw in values.items():
        value = str(raw).strip()
        _, label, minimum, maximum = FIELDS[key]
        if minimum is not None:
            if not re.fullmatch(r"[0-9]{1,6}", value) or not minimum <= int(value) <= maximum:
                raise ValueError(f"{label}: Bitte einen Wert zwischen {minimum} und {maximum} wählen.")
            value = str(int(value))
        elif key in BOOLEAN_FIELDS:
            if value not in {"true", "false"}:
                raise ValueError(f"{label}: Ungültiger Wert.")
        elif key == "HUGO_MODEL_PROVIDER":
            if value not in {"api", "chatgpt"}:
                raise ValueError("KI-Zugang: Bitte API oder ChatGPT-Abo wählen.")
        elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}", value):
            raise ValueError(f"{label}: Bitte einen gültigen Modellnamen eingeben.")
        result[key] = value
    return result


def save(values, revision):
    validated = validate(values)
    storage.save_settings(validated, revision)
    logger.info("Application settings saved; revision=%s", revision + 1)


def reset(revision):
    storage.save_settings({}, revision)
    logger.info("Application settings reset to environment defaults; revision=%s", revision + 1)
