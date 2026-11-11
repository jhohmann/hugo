"""Official Sign in with ChatGPT public-client flow; never reads Codex credentials."""

import base64
import hashlib
import logging
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt

from app.storage.model_oauth import locked_registration
from app.agent.model_client import ModelAccessError

ISSUER = "https://auth.openai.com"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
TOKEN = ISSUER + "/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = "openid profile email offline_access resource.invoke " + PLAN_SCOPE
TERMINAL_REFRESH_ERRORS = {
    "invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired",
    "refresh_token_invalidated", "refresh_token_reused",
}
logger = logging.getLogger(__name__)


class ChatGPTAuthError(ModelAccessError):
    def __init__(self, message, *, terminal=False):
        super().__init__(message)
        self.terminal = terminal


def authorization(host_id, previous, redirect_uri):
    pending = {
        "state": secrets.token_urlsafe(32), "nonce": secrets.token_urlsafe(32),
        "verifier": secrets.token_urlsafe(48), "redirect_uri": redirect_uri,
        "previous": dict(previous), "started_at": time.monotonic(),
    }
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(pending["verifier"].encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    params = {
        "client_id": previous.get("client_id", "dynamic_agent_client"),
        "ext_agent_host_id": host_id, "response_type": "code", "redirect_uri": redirect_uri,
        "scope": SCOPES, "resource": RESOURCE, "state": pending["state"],
        "nonce": pending["nonce"], "code_challenge_method": "S256", "code_challenge": challenge,
    }
    if not previous.get("client_id"):
        params["agent_name_hint"] = "Hugo"
    # No ID token in a printable authorization URL. Account selection is intentional.
    return pending, AUTHORIZE + "?" + urlencode(params)


def token_request(data):
    try:
        response = httpx.post(TOKEN, data={**data, "resource": RESOURCE}, timeout=25)
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("Invalid token response")
        if response.is_error:
            terminal = isinstance(body.get("error"), str) and body["error"] in TERMINAL_REFRESH_ERRORS
            raise ChatGPTAuthError(
                "ChatGPT-Anmeldung erneuern." if terminal else
                "ChatGPT-Tokenabruf fehlgeschlagen; Verbindung bleibt erhalten.",
                terminal=terminal,
            )
        return body
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("ChatGPT token exchange failed: %s", type(exc).__name__)
        raise ChatGPTAuthError("ChatGPT-Tokenabruf vorübergehend nicht verfügbar.") from None


def validated_identity(id_token, client_id, nonce):
    try:
        key = jwt.PyJWKClient(ISSUER + "/.well-known/jwks.json", timeout=15).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token, key.key, algorithms=["RS256"], issuer=ISSUER, audience=client_id,
            leeway=5, options={"require": ["sub", "exp", "iat", "nonce"]},
        )
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise ValueError("Missing subject")
        if not secrets.compare_digest(str(claims["nonce"]), nonce):
            raise ValueError("Invalid nonce")
        return claims
    except (jwt.PyJWTError, ValueError, TypeError):
        raise ChatGPTAuthError("ChatGPT-Identität konnte nicht sicher bestätigt werden.") from None


def merge_tokens(body, previous):
    result = dict(previous)
    scopes = body.get("scope", " ".join(previous.get("scopes", []))).split()
    if PLAN_SCOPE not in scopes:
        raise ChatGPTAuthError("Nutzung des ChatGPT-Abos wurde nicht freigegeben.", terminal=True)
    if body.get("token_type", "").lower() != "bearer" or not body.get("access_token"):
        raise ChatGPTAuthError("Ungültige ChatGPT-Tokenantwort.")
    try:
        lifetime = int(body["expires_in"])
        if lifetime <= 0:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise ChatGPTAuthError("ChatGPT-Tokenantwort enthält keine gültige Laufzeit.") from None
    for name in ("access_token", "refresh_token", "id_token"):
        if body.get(name):
            result[name] = body[name]
    if not result.get("refresh_token"):
        raise ChatGPTAuthError("ChatGPT-Anmeldung enthält keine erneuerbare Sitzung.")
    result.update(expires_at=time.time() + lifetime, scopes=scopes)
    return result


def complete_authorization(pending, query):
    if time.monotonic() - pending["started_at"] > 600:
        raise ChatGPTAuthError("ChatGPT-Anmeldung ist abgelaufen.")
    if not secrets.compare_digest(query.get("state", ""), pending["state"]):
        raise ChatGPTAuthError("Ungültiger Anmeldestatus.")
    if query.get("error"):
        raise ChatGPTAuthError("ChatGPT-Anmeldung wurde abgebrochen.")
    previous = pending["previous"]
    client_id = query.get("client_id") or previous.get("client_id")
    if not client_id or client_id == "dynamic_agent_client" or not query.get("code"):
        raise ChatGPTAuthError("ChatGPT-Registrierung ist unvollständig.")
    if previous.get("client_id") and client_id != previous["client_id"]:
        raise ChatGPTAuthError("ChatGPT-Registrierung hat unerwartet gewechselt.")
    body = token_request({
        "grant_type": "authorization_code", "client_id": client_id, "code": query["code"],
        "code_verifier": pending["verifier"], "redirect_uri": pending["redirect_uri"],
    })
    claims = validated_identity(body.get("id_token", ""), client_id, pending["nonce"])
    if previous.get("subject") and claims["sub"] != previous["subject"]:
        raise ChatGPTAuthError("Die Anmeldung gehört zu einem anderen ChatGPT-Konto.")
    return merge_tokens(body, {
        "client_id": client_id, "subject": claims["sub"], "email": claims.get("email", ""),
    })


def clear_tokens(registration):
    for name in ("access_token", "refresh_token", "id_token", "expires_at", "scopes"):
        registration.pop(name, None)


def access_token():
    failure = None
    with locked_registration() as (_, registration):
        if not registration.get("refresh_token"):
            raise ChatGPTAuthError("Bitte Hugo zuerst mit ChatGPT verbinden (scripts/chatgpt_login.py login).")
        if registration.get("expires_at", 0) <= time.time() + 60:
            try:
                body = token_request({
                    "grant_type": "refresh_token", "client_id": registration["client_id"],
                    "refresh_token": registration["refresh_token"],
                })
                registration.update(merge_tokens(body, registration))
            except ChatGPTAuthError as exc:
                if exc.terminal:
                    clear_tokens(registration)
                failure = exc
        token = registration.get("access_token")
    # Raise after commit, so invalid refresh tokens are not retried by the worker.
    if failure:
        raise failure
    return token


def model_catalog():
    with httpx.Client(timeout=25) as client:
        response = client.get(RESOURCE + "/models", headers={"Authorization": "Bearer " + access_token()})
        if response.is_error:
            raise ChatGPTAuthError("Modellkatalog des ChatGPT-Kontos ist nicht verfügbar.")
        return [m for m in response.json()["models"] if m.get("visibility") == "list"]


def sign_out():
    revoked = False
    with locked_registration() as (_, registration):
        if registration.get("refresh_token"):
            try:
                metadata = httpx.get(ISSUER + "/.well-known/openid-configuration", timeout=15)
                metadata.raise_for_status()
                endpoint = metadata.json()["revocation_endpoint"]
                if not endpoint.startswith(ISSUER + "/"):
                    raise ValueError("Unexpected revocation endpoint")
                response = httpx.post(endpoint, data={
                    "client_id": registration["client_id"], "token": registration["refresh_token"],
                    "token_type_hint": "refresh_token",
                }, timeout=15)
                revoked = response.status_code == 200
            except (httpx.HTTPError, ValueError, KeyError):
                pass
        clear_tokens(registration)
    return revoked
