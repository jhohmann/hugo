"""Shared quota cooldown and public status; never infer a subscription reset."""

from datetime import datetime, timezone
import time
from uuid import uuid4

from app.storage import model_oauth


def reserve_plan_attempt(retry_seconds):
    with model_oauth.locked_registration() as (_, registration):
        if not registration.get("refresh_token") or not registration.get("usage_blocked"):
            return True, None
        now = time.time()
        if registration.get("quota_retry_at", 0) > now:
            return False, None
        # Only one web/worker request probes availability during the cooldown.
        probe = uuid4().hex
        registration.update(quota_retry_at=now + retry_seconds, quota_probe=probe)
        return True, probe


def mark_quota_exhausted(retry_seconds):
    with model_oauth.locked_registration() as (_, registration):
        registration.update(usage_blocked=True, quota_seen_at=time.time(),
                            quota_retry_at=time.time() + retry_seconds)
        registration.pop("quota_probe", None)


def record_success(route, response, probe=None):
    usage = getattr(response, "usage", None)
    with model_oauth.locked_registration() as (_, registration):
        if route == "chatgpt" and probe and registration.get("quota_probe") == probe:
            for key in ("usage_blocked", "quota_retry_at", "quota_probe", "quota_seen_at"):
                registration.pop(key, None)
        registration["last_model_call"] = {
            "route": route, "model": response.model, "at": time.time(),
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        }


def reset_quota_pause():
    with model_oauth.locked_registration() as (_, registration):
        for key in ("usage_blocked", "quota_retry_at", "quota_probe", "quota_seen_at"):
            registration.pop(key, None)


def public_status():
    _, registration = model_oauth.read_registration()
    retry = registration.get("quota_retry_at")
    last = registration.get("last_model_call", {})
    # Explicit allowlist: no credential record reaches templates or JSON endpoints.
    return {
        "connected": bool(registration.get("refresh_token")),
        "limited": bool(registration.get("usage_blocked")),
        "retry_at": datetime.fromtimestamp(retry, timezone.utc) if retry else None,
        "last": {key: last.get(key) for key in ("route", "model", "input_tokens", "output_tokens")},
    }
