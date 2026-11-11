"""OAuth boundaries, real SDK stream decoding and serialized DB refresh; no model calls."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt
import pytest

from app.agent import chatgpt_auth as auth, model_client, model_usage
from app.storage import model_oauth as storage
from test_follow_up import store


@pytest.fixture
def registration(monkeypatch):
    monkeypatch.setenv("HUGO_API_FALLBACK_ENABLED", "false")
    data = {"client_id": "oaiapp_hugo", "subject": "user1", "access_token": "access",
            "refresh_token": "refresh", "expires_at": time.time() + 600,
            "scopes": [auth.PLAN_SCOPE]}

    @contextmanager
    def locked():
        yield "urn:uuid:example", data

    monkeypatch.setattr(storage, "locked_registration", locked)
    monkeypatch.setattr(auth, "locked_registration", locked)
    return data


def token_body(**changes):
    return {"access_token": "new-access", "refresh_token": "new-refresh", "id_token": "id",
            "expires_in": 3600, "token_type": "Bearer", "scope": auth.SCOPES, **changes}


def test_pkce_dynamic_registration_and_returning_account():
    pending, url = auth.authorization("urn:uuid:host", {}, "http://127.0.0.1:1457/auth/callback")
    params = parse_qs(urlparse(url).query)
    assert params["client_id"] == ["dynamic_agent_client"]
    assert params["agent_name_hint"] == ["Hugo"]
    assert params["code_challenge_method"] == ["S256"]
    assert pending["verifier"] not in url
    _, returning = auth.authorization("urn:uuid:host", {"client_id": "issued", "id_token": "secret"}, pending["redirect_uri"])
    assert "agent_name_hint" not in returning and "secret" not in returning
    assert "client_id=issued" in returning


@pytest.mark.parametrize("query", [
    {"state": "wrong", "code": "code", "client_id": "issued"},
    {"state": "valid", "error": "access_denied"},
    {"state": "valid", "code": "code"},
    {"state": "valid", "code": "code", "client_id": "dynamic_agent_client"},
])
def test_invalid_callback_never_exchanges_code(monkeypatch, query):
    pending, _ = auth.authorization("host", {}, "http://127.0.0.1:1457/auth/callback")
    pending["state"] = "valid"
    monkeypatch.setattr(auth, "token_request", lambda *_: pytest.fail("Invalid callback exchanged"))
    with pytest.raises(auth.ChatGPTAuthError):
        auth.complete_authorization(pending, query)


def test_exchange_requires_identity_and_scope(monkeypatch):
    pending, _ = auth.authorization("host", {}, "http://127.0.0.1:1457/auth/callback")
    calls = []
    monkeypatch.setattr(auth, "token_request", lambda data: calls.append(data) or token_body())
    monkeypatch.setattr(auth, "validated_identity", lambda *_: {"sub": "user1", "email": "test@example.org"})
    query = {"state": pending["state"], "code": "code", "client_id": "issued"}
    result = auth.complete_authorization(pending, query)
    assert result["client_id"] == "issued" and result["subject"] == "user1"
    assert calls[0]["redirect_uri"] == pending["redirect_uri"]
    assert calls[0]["code_verifier"] == pending["verifier"]
    monkeypatch.setattr(auth, "token_request", lambda _: token_body(scope="openid"))
    with pytest.raises(auth.ChatGPTAuthError, match="nicht freigegeben"):
        auth.complete_authorization(pending, query)


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.parametrize("change", [{}, {"nonce": "wrong"}, {"aud": "wrong"}, {"iss": "https://attacker.test"}, {"exp": 1}])
def test_signed_id_token_validation(monkeypatch, signing_key, change):
    claims = {"iss": auth.ISSUER, "aud": "issued", "sub": "user1", "nonce": "nonce",
              "iat": int(time.time()), "exp": int(time.time()) + 600, **change}
    token = jwt.encode(claims, signing_key, algorithm="RS256")
    monkeypatch.setattr(jwt.PyJWKClient, "get_signing_key_from_jwt", lambda *_: SimpleNamespace(key=signing_key.public_key()))
    if change:
        with pytest.raises(auth.ChatGPTAuthError):
            auth.validated_identity(token, "issued", "nonce")
    else:
        assert auth.validated_identity(token, "issued", "nonce")["sub"] == "user1"


@pytest.mark.parametrize("terminal", [False, True])
def test_refresh_failures_preserve_or_clear_session(monkeypatch, registration, terminal):
    registration["expires_at"] = 0
    def fail(_):
        raise auth.ChatGPTAuthError("failed", terminal=terminal)
    monkeypatch.setattr(auth, "token_request", fail)
    with pytest.raises(auth.ChatGPTAuthError):
        auth.access_token()
    assert ("refresh_token" in registration) is not terminal
    assert registration["client_id"] == "oaiapp_hugo"


def test_real_db_serializes_rotating_refresh(store, monkeypatch):
    monkeypatch.setattr(storage, "get_connection", store)
    with storage.locked_registration() as (_, registration):
        registration.update(client_id="issued", subject="user1", refresh_token="old", expires_at=0)
    calls = []
    def refresh(data):
        calls.append(data)
        return token_body()
    monkeypatch.setattr(auth, "token_request", refresh)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: auth.access_token(), range(2))) == ["new-access", "new-access"]
    assert len(calls) == 1
    assert storage.read_registration()[1]["refresh_token"] == "new-refresh"


def response_body(output=None):
    return {"id": "resp_test", "object": "response", "created_at": 1, "model": "eligible-model",
            "status": "completed", "output": output or [], "parallel_tool_calls": False,
            "tools": [], "tool_choice": "auto"}


def sdk_client(monkeypatch, events, requests):
    monkeypatch.setenv("HUGO_MODEL_PROVIDER", "chatgpt")
    monkeypatch.setenv("HUGO_MODEL", "eligible-model")
    def transport(request):
        requests.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer access"
        data = "".join("data: " + json.dumps(event) + "\n\n" for event in events)
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, content=data)
    return model_client.ModelClient(http_client=httpx.Client(transport=httpx.MockTransport(transport)))


def test_real_sdk_stream_function_roundtrip(monkeypatch, registration):
    requests = []
    function = {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "current_time",
                "namespace": "hugo", "arguments": "{}", "status": "completed"}
    client = sdk_client(monkeypatch, [{"type": "response.completed", "response": response_body([function]), "sequence_number": 1}], requests)
    response = client.create(model="eligible-model", input=[{"role": "user", "content": "Zeit?"}],
                             tools=[{"type": "function", "name": "current_time", "parameters": {"type": "object"}}],
                             max_output_tokens=100, max_tool_calls=3)
    assert response.output[0].name == "current_time"
    assert response.output[0].model_dump()["namespace"] == "hugo"
    assert requests[0]["tools"][0]["type"] == "namespace"
    assert requests[0]["store"] is False and requests[0]["stream"] is True
    assert "max_output_tokens" not in requests[0] and "max_tool_calls" not in requests[0]
    assert requests[0]["include"] == ["reasoning.encrypted_content"]


@pytest.mark.parametrize("event_type", ["response.failed", "response.incomplete", "error", "response.output_text.delta"])
def test_incomplete_stream_never_returns_tool_result(monkeypatch, registration, event_type):
    event = {"type": event_type, "response": {**response_body(), "status": "failed"},
             "sequence_number": 1, "delta": "partial"}
    client = sdk_client(monkeypatch, [event], [])
    with pytest.raises(model_client.ModelAccessError):
        client.create(model="eligible-model", input=[])


def test_quota_error_pauses_following_calls_without_fallback(monkeypatch, registration):
    event = {"type": "response.failed", "sequence_number": 1, "response": {
        **response_body(), "status": "failed", "error": {
            "code": "subscription_sharing_usage_limit_exceeded", "message": "quota"}}}
    requests = []
    client = sdk_client(monkeypatch, [event], requests)
    with pytest.raises(model_client.ModelAccessError, match="Kontingentgrenze"):
        client.create(model="eligible-model", input=[])
    assert registration["usage_blocked"]
    with pytest.raises(model_client.PlanQuotaExceeded, match="Kontingentgrenze"):
        client.create(model="eligible-model", input=[])
    assert len(requests) == 1


@pytest.mark.parametrize("stream_error", [True, False])
def test_quota_switches_same_request_once_to_api(monkeypatch, registration, stream_error):
    from openai import OpenAI
    monkeypatch.setenv("HUGO_MODEL_PROVIDER", "chatgpt")
    monkeypatch.setenv("HUGO_MODEL", "eligible-model")
    monkeypatch.setenv("HUGO_API_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("HUGO_API_FALLBACK_MODEL", "gpt-5-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "api-test-key")
    calls = []
    def transport(request):
        body = json.loads(request.content)
        calls.append((request.headers["authorization"], body))
        if len(calls) == 1:
            error = {"code": "subscription_sharing_usage_limit_exceeded", "message": "limit"}
            if not stream_error:
                return httpx.Response(429, json={"error": error})
            event = {"type": "response.failed", "sequence_number": 2,
                     "response": {**response_body(), "status": "failed", "error": error}}
            # Earlier partial content must not escape or trigger tools before completion.
            partial = {"type": "response.output_text.delta", "delta": "unvollständig", "sequence_number": 1}
            return httpx.Response(200, headers={"Content-Type": "text/event-stream"},
                                  content="".join("data: " + json.dumps(e) + "\n\n" for e in [partial, event]))
        return httpx.Response(200, json={**response_body(), "model": "gpt-5-mini"})
    monkeypatch.setattr(model_client, "OpenAI", lambda **kw: OpenAI(
        **kw, http_client=httpx.Client(transport=httpx.MockTransport(transport))))
    history = [
        {"role": "user", "content": "Wie spät?"},
        {"type": "reasoning", "id": "secret-id", "encrypted_content": "private-plan-reasoning"},
        {"type": "function_call", "id": "fc1", "call_id": "call1", "namespace": "hugo",
         "name": "current_time", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call1", "output": "10 Uhr"},
    ]
    client = model_client.ModelClient()
    assert client.create(model="eligible-model", input=history, max_output_tokens=300).status == "completed"
    assert calls[0][0] == "Bearer access" and calls[1][0] == "Bearer api-test-key"
    api_body = calls[1][1]
    assert api_body["model"] == "gpt-5-mini" and api_body["max_output_tokens"] == 300
    assert "private-plan-reasoning" not in json.dumps(api_body)
    assert api_body["input"][-1] == history[-1]  # completed action result is preserved
    assert "namespace" not in api_body["input"][-2]
    assert history[1]["encrypted_content"]  # original request never mutated
    client.create(model="eligible-model", input=history)
    assert len(calls) == 3 and calls[2][0] == "Bearer api-test-key"
    assert model_usage.public_status()["last"]["route"] == "api"


@pytest.mark.parametrize("code", ["rate_limit_exceeded", "subscription_sharing_usage_unavailable",
                                  "subscription_sharing_user_not_eligible", "invalid_api_key"])
def test_other_failures_never_switch_billing(monkeypatch, registration, code):
    event = {"type": "response.failed", "sequence_number": 1, "response": {
        **response_body(), "status": "failed", "error": {"code": code, "message": "failure"}}}
    requests = []
    client = sdk_client(monkeypatch, [event], requests)
    monkeypatch.setenv("HUGO_API_FALLBACK_ENABLED", "true")
    with pytest.raises(model_client.ModelAccessError):
        client.create(model="eligible-model", input=[])
    assert len(requests) == 1 and not registration.get("usage_blocked")


def test_plan_recovers_after_probe_without_replaying_tools(monkeypatch, registration):
    registration.update(usage_blocked=True, quota_retry_at=0)
    requests = []
    client = sdk_client(monkeypatch, [{"type": "response.completed", "sequence_number": 1,
                                     "response": response_body()}], requests)
    client.create(model="eligible-model", input=[
        {"type": "reasoning", "encrypted_content": "api-reasoning"},
        {"type": "function_call", "id": "api-fc", "call_id": "call1", "name": "current_time", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call1", "output": "10 Uhr"},
    ])
    assert not registration.get("usage_blocked")
    assert requests[0]["input"][0]["namespace"] == "hugo"
    assert "api-reasoning" not in json.dumps(requests[0])
    assert model_usage.public_status()["last"]["route"] == "chatgpt"


def test_missing_key_and_explicit_check_cannot_fallback(monkeypatch, registration):
    monkeypatch.setenv("HUGO_MODEL_PROVIDER", "chatgpt")
    monkeypatch.setenv("HUGO_API_FALLBACK_ENABLED", "true")
    registration.update(usage_blocked=True, quota_retry_at=time.time() + 1000)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(model_client.ModelAccessError, match="API-Schlüssel"):
        model_client.ModelClient().create(model="eligible-model", input=[])
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with pytest.raises(model_client.PlanQuotaExceeded):
        model_client.ModelClient(allow_api_fallback=False).with_options(timeout=60).create(model="eligible-model", input=[])


def test_real_db_allows_one_recovery_probe(store, monkeypatch):
    monkeypatch.setattr(storage, "get_connection", store)
    with storage.locked_registration() as (_, registration):
        registration.update(usage_blocked=True, quota_retry_at=0, refresh_token="test-refresh")
    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = list(pool.map(lambda _: model_usage.reserve_plan_attempt(1800), range(2)))
    assert sum(allowed for allowed, _ in attempts) == 1


def test_usage_status_never_exposes_credentials(monkeypatch, registration):
    monkeypatch.setenv("HUGO_MODEL_PROVIDER", "chatgpt")
    status = model_client.usage_status()
    assert status["connected"]
    assert not {"access_token", "refresh_token", "subject", "client_id", "email"} & status.keys()


def test_api_provider_keeps_original_request(monkeypatch, registration):
    monkeypatch.setenv("HUGO_MODEL_PROVIDER", "api")
    def transport(request):
        body = json.loads(request.content)
        assert body["max_output_tokens"] == 100 and "stream" not in body
        return httpx.Response(200, json=response_body())
    client = model_client.ModelClient(http_client=httpx.Client(transport=httpx.MockTransport(transport)))
    assert client.create(model="gpt-5-mini", input=[], max_output_tokens=100).status == "completed"
    assert registration["last_model_call"]["route"] == "api"


def test_explicit_oauth_diagnostic_cannot_use_saved_api_provider(monkeypatch, registration):
    from app.storage import settings
    monkeypatch.setattr(settings, "read_settings", lambda: {"values": {"HUGO_MODEL_PROVIDER": "api"}})
    requests = []
    prototype = sdk_client(monkeypatch, [{"type": "response.completed", "response": response_body(), "sequence_number": 1}], requests)
    client = model_client.ModelClient(provider_override="chatgpt", allow_api_fallback=False, **prototype.options).with_options(timeout=30)
    assert client.create(model="eligible-model", input=[]).status == "completed"
    assert len(requests) == 1 and registration["last_model_call"]["route"] == "chatgpt"
