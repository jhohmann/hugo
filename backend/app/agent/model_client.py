"""One Responses interface for API billing and the optional ChatGPT-plan grant."""

import os
import logging

from openai import APIConnectionError, APIStatusError, OpenAI
from app.settings import get_value, snapshot

logger = logging.getLogger(__name__)


class ModelAccessError(RuntimeError):
    pass


class PlanQuotaExceeded(ModelAccessError):
    pass


def provider():
    value = get_value("HUGO_MODEL_PROVIDER", "api")
    if value not in {"api", "chatgpt"}:
        raise ValueError("HUGO_MODEL_PROVIDER muss api oder chatgpt sein.")
    return value


def fallback_enabled():
    return get_value("HUGO_API_FALLBACK_ENABLED", "false").lower() == "true"


def retry_seconds():
    value = int(get_value("HUGO_CHATGPT_RETRY_SECONDS", "1800"))
    if not 60 <= value <= 86400:
        raise ValueError("HUGO_CHATGPT_RETRY_SECONDS muss zwischen 60 und 86400 liegen.")
    return value


def usage_status():
    from app.agent import model_usage
    if provider() == "api":
        return {"provider": "api"}
    return {**model_usage.public_status(), "provider": "chatgpt",
            "fallback": fallback_enabled(), "api_ready": bool(os.getenv("OPENAI_API_KEY")),
            "fallback_model": get_value("HUGO_API_FALLBACK_MODEL") or "gpt-5.6-terra"}


def plan_error(code):
    if code == "subscription_sharing_usage_limit_exceeded":
        return PlanQuotaExceeded("ChatGPT-Kontingentgrenze erreicht.")
    messages = {
        "subscription_sharing_user_not_eligible": "Dieses ChatGPT-Konto ist für die Abo-Nutzung in Hugo nicht freigeschaltet.",
        "subscription_sharing_usage_unavailable": "ChatGPT-Kontingent ist vorübergehend nicht prüfbar.",
        "subscription_sharing_unsupported_capability": "Das ChatGPT-Konto unterstützt diese Modellfunktion nicht.",
    }
    return ModelAccessError(messages.get(code, "ChatGPT-Modellaufruf fehlgeschlagen; kein Wechsel zur kostenpflichtigen API."))


class ModelClient:
    """Keep callers and test doubles independent of the selected billing path."""

    def __init__(self, *, allow_api_fallback=True, provider_override=None, **options):
        if provider_override not in {None, "api", "chatgpt"}:
            raise ValueError("Unbekannter KI-Zugang.")
        self.options = options
        self.allow_api_fallback = allow_api_fallback
        self.provider_override = provider_override
        self.responses = self

    def with_options(self, **options):
        return ModelClient(allow_api_fallback=self.allow_api_fallback, provider_override=self.provider_override,
                           **{**self.options, **options})

    def create(self, **request):
        with snapshot():
            return self._create(request)

    def _create(self, request):
        from app.agent import model_usage
        if (self.provider_override or provider()) == "api":
            with OpenAI(**self.options) as client:
                response = client.responses.create(**request)
            if response.status == "completed":
                model_usage.record_success("api", response)
            return response

        attempt, probe = model_usage.reserve_plan_attempt(retry_seconds())
        if attempt:
            try:
                response = self._plan_response(request)
            except PlanQuotaExceeded:
                model_usage.mark_quota_exhausted(retry_seconds())
            else:
                model_usage.record_success("chatgpt", response, probe)
                return response
        if not (self.allow_api_fallback and fallback_enabled()):
            raise PlanQuotaExceeded("ChatGPT-Kontingentgrenze erreicht; API-Reserve ist deaktiviert.")
        if not os.getenv("OPENAI_API_KEY"):
            raise ModelAccessError("ChatGPT-Kontingentgrenze erreicht; für die API-Reserve fehlt der API-Schlüssel.")
        response = self._api_fallback(request)
        if response.status == "completed":
            model_usage.record_success("api", response)
        return response

    def _api_fallback(self, request):
        request = dict(request)
        request["model"] = get_value("HUGO_API_FALLBACK_MODEL") or "gpt-5.6-terra"
        # A different model/account cannot consume encrypted reasoning from the plan.
        # Preserve completed tool calls + results, so actions are not replayed.
        request["input"] = [
            {key: value for key, value in item.items() if key not in {"id", "namespace"}}
            for item in request["input"] if item.get("type") not in {"reasoning", "web_search_call"}
        ]
        request["store"] = False
        logger.info("Hugo model: API fallback after ChatGPT quota limit, model=%s", request["model"])
        try:
            with OpenAI(**{**self.options, "max_retries": 0}) as client:
                return client.responses.create(**request)
        except (APIStatusError, APIConnectionError):
            raise ModelAccessError("Die ChatGPT-Kontingentgrenze ist erreicht und die API-Reserve derzeit nicht verfügbar.") from None

    def _plan_response(self, request):
        from app.agent.chatgpt_auth import RESOURCE, access_token
        if not request.get("model"):
            raise ModelAccessError("Bitte ein Modell aus dem ChatGPT-Modellkatalog wählen.")
        # The direct plan preview requires streaming, stateless input and namespaced functions.
        request = dict(request)
        if any(item.get("type") == "function_call" and item.get("namespace") != "hugo"
               for item in request["input"]):
            # A recovered plan can continue a tool round previously answered by the API.
            request["input"] = [
                {**{key: value for key, value in item.items() if key not in {"id", "namespace"}},
                 **({"namespace": "hugo"} if item.get("type") == "function_call" else {})}
                for item in request["input"] if item.get("type") not in {"reasoning", "web_search_call"}
            ]
        request.pop("max_output_tokens", None)
        request.pop("max_tool_calls", None)
        functions = [tool for tool in request.get("tools", []) if tool["type"] == "function"]
        tools = [tool for tool in request.get("tools", []) if tool["type"] != "function"]
        if functions:
            tools.append({"type": "namespace", "name": "hugo", "description": "Hugos Werkzeuge", "tools": functions})
        if tools:
            request["tools"] = tools
        request.update(store=False, stream=True, include=["reasoning.encrypted_content"])
        options = {"timeout": 120, **self.options, "max_retries": 0}
        try:
            with OpenAI(api_key=access_token(), base_url=RESOURCE, **options) as client:
                with client.responses.create(**request) as stream:
                    completed = None
                    for event in stream:
                        if event.type == "response.completed":
                            completed = event.response
                        elif event.type in {"response.failed", "response.incomplete"}:
                            error = getattr(event.response, "error", None)
                            raise plan_error(getattr(error, "code", None))
                        elif event.type == "error":
                            raise plan_error(getattr(event, "code", None))
                    if completed is None or completed.status != "completed":
                        raise ModelAccessError("ChatGPT-Antwort wurde unterbrochen. Keine vollständige Antwort empfangen.")
                    return completed
        except APIStatusError as exc:
            logger.warning("ChatGPT response: HTTP status=%s request_id=%s", exc.status_code, exc.request_id)
            raise plan_error(getattr(exc, "code", None)) from None
        except APIConnectionError:
            raise ModelAccessError("ChatGPT ist vorübergehend nicht erreichbar. Kein Wechsel zur kostenpflichtigen API.") from None
