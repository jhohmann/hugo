"""Two small real model calls with synthetic tool data; never changes quota state."""

from pathlib import Path
import sys


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.config import load_environment
    load_environment()
    from app.agent.model_client import ModelClient
    from app.settings import get_value
    client = ModelClient(timeout=60, max_retries=0)
    request = {
        "model": get_value("HUGO_MODEL"),
        "instructions": "Rufe test_value auf. Wenn ein test_value-Ergebnis bereits vorliegt, antworte ausschließlich mit dessen value, ohne weiteren Werkzeugaufruf.",
        "input": [{"role": "user", "content": "Bitte den Testwert ausgeben."}],
        "tools": [{"type": "function", "name": "test_value", "description": "Liefert einen synthetischen Testwert.",
                   "strict": True, "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}}],
        "reasoning": {"effort": "low"}, "max_output_tokens": 1000,
    }
    plan = client._plan_response(request)
    calls = [item for item in plan.output if item.type == "function_call"]
    if len(calls) != 1 or calls[0].name != "test_value":
        raise RuntimeError("OAuth-Modell hat den erwarteten Testaufruf nicht geliefert.")
    request["input"].extend(item.model_dump(exclude_none=True) for item in plan.output)
    request["input"].append({"type": "function_call_output", "call_id": calls[0].call_id,
                             "output": '{"value":"OK"}'})
    api = client._api_fallback(request)
    if api.status != "completed" or api.output_text.strip() != "OK":
        raise RuntimeError("API-Fortsetzung wurde nicht wie erwartet abgeschlossen.")
    for name, response in (("ChatGPT-Abo", plan), ("API-Reserve", api)):
        print(name, response.model, response.status,
              "Tokens:", response.usage.input_tokens, response.usage.output_tokens)
    print("OK: synthetisches Werkzeugergebnis nach Wechsel übernommen; keine echte Kontingentgrenze ausgelöst.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
