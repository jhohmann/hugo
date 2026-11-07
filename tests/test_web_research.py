"""Native Websuche und Quellen: ohne externe API oder Datenbank."""

import copy
import json
from types import SimpleNamespace

import pytest

from app.agent import assistant, evaluation, web_research
from app.tools.links import source_url
from app.web.formatting import source_links


def item(data):
    result = SimpleNamespace(**data)
    result.model_dump = lambda **kwargs: copy.deepcopy(data)
    if isinstance(data.get("action"), dict):
        result.action = SimpleNamespace(**data["action"])
    return result


def response(output, status="completed"):
    return SimpleNamespace(
        status=status, incomplete_details="max_output_tokens",
        output=[item(data) for data in output],
        output_text="".join(part["text"] for data in output
                            if data["type"] == "message"
                            for part in data["content"]),
        usage=SimpleNamespace(input_tokens=120, output_tokens=30),
    )


def message(text="Ein Ergebnis.", annotations=None):
    return {"type": "message", "role": "assistant", "content": [
        {"type": "output_text", "text": text, "annotations": annotations or []},
    ]}


def search(status="completed"):
    return {"type": "web_search_call", "id": "ws_1", "status": status,
            "action": {"type": "search", "query": "private-query-not-for-logs"}}


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setenv("HUGO_WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("HUGO_WEB_SEARCH_MAX_CALLS", "3")
    monkeypatch.setattr(assistant.client.responses, "create", lambda **kw: pytest.fail("Unexpected API call"))
    monkeypatch.setattr(assistant, "execute_tool", lambda *a, **kw: pytest.fail("Unexpected tool execution"))


def test_web_and_function_results_continue_in_same_loop(monkeypatch, caplog):
    requests = []
    citation = {"type": "url_citation", "url": "https://example.org/race",
                "title": "Veranstalter", "start_index": 0, "end_index": 13}
    first = response([search(), {"type": "function_call", "name": "search_events",
                     "call_id": "cal_1", "arguments": '{"query":"private-context"}'}])

    def create(**kwargs):
        requests.append(copy.deepcopy(kwargs))
        return first if len(requests) == 1 else response([message(annotations=[citation])])

    monkeypatch.setattr(assistant.client.responses, "create", create)
    executed = []
    monkeypatch.setattr(assistant, "execute_tool", lambda *a, **kw: executed.append(a) or {"events": []})
    caplog.set_level("INFO", logger=assistant.__name__)
    result = assistant.run_tool_loop("Test", [], [{"type": "function", "name": "search_events"}])
    assert "[Veranstalter](https://example.org/race)" in result
    assert [r["max_tool_calls"] for r in requests] == [3, 2]
    assert requests[1]["input"][0] == search()
    assert requests[1]["input"][-1]["type"] == "function_call_output"
    assert json.loads(requests[1]["input"][-1]["output"]) == {"events": []}
    assert executed[0][0] == "search_events"
    assert "web_search action=search status=completed" in caplog.text
    assert "input_tokens=120 output_tokens=30" in caplog.text
    assert "private-query" not in caplog.text
    assert "private-context" not in caplog.text


def test_search_only_response_can_finish_after_budget_exhaustion(monkeypatch):
    monkeypatch.setenv("HUGO_WEB_SEARCH_MAX_CALLS", "1")
    requests = []

    def create(**kwargs):
        requests.append(copy.deepcopy(kwargs))
        return response([search()]) if len(requests) == 1 else response([message()])

    monkeypatch.setattr(assistant.client.responses, "create", create)
    assert assistant.run_tool_loop("Test", [], []) == "Ein Ergebnis."
    assert requests[0]["tools"] == [web_research.WEB_SEARCH_TOOL]
    assert requests[0]["max_tool_calls"] == 1
    assert requests[1]["tools"] == []
    assert "max_tool_calls" not in requests[1]
    assert "erschöpft" in requests[1]["instructions"]


def test_disabled_search_and_evaluation_share_settings(monkeypatch):
    monkeypatch.setenv("HUGO_WEB_SEARCH_ENABLED", "false")
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return response([message()])

    monkeypatch.setattr(assistant.client.responses, "create", create)
    assistant.run_tool_loop(evaluation.build_evaluation_instructions(), [], evaluation.EVALUATION_TOOLS)
    assert all(t["type"] == "function" for t in captured["tools"])
    assert "max_tool_calls" not in captured
    assert "deaktiviert" in captured["instructions"]
    monkeypatch.setenv("HUGO_WEB_SEARCH_ENABLED", "true")
    assistant.run_tool_loop(evaluation.build_evaluation_instructions(), [], evaluation.EVALUATION_TOOLS)
    assert captured["tools"][-1] == web_research.WEB_SEARCH_TOOL
    assert "konkrete offene Frage" in captured["instructions"]


@pytest.mark.parametrize("state", ["failed", "in_progress"])
def test_failed_search_is_not_a_successful_answer(monkeypatch, state):
    monkeypatch.setattr(assistant.client.responses, "create", lambda **kw: response([search(state), message()]))
    with pytest.raises(RuntimeError, match="nicht erfolgreich"):
        assistant.run_tool_loop("Test", [], [])


def test_provider_budget_violation_and_incomplete_response_fail(monkeypatch):
    monkeypatch.setenv("HUGO_WEB_SEARCH_MAX_CALLS", "1")
    monkeypatch.setattr(assistant.client.responses, "create", lambda **kw: response([search(), search()]))
    with pytest.raises(RuntimeError, match="Aufruflimit"):
        assistant.run_tool_loop("Test", [], [])
    monkeypatch.setattr(assistant.client.responses, "create", lambda **kw: response([message()], "incomplete"))
    with pytest.raises(RuntimeError, match="Incomplete"):
        assistant.run_tool_loop("Test", [], [])
    monkeypatch.setattr(assistant.client.responses, "create", lambda **kw: response([message()], "failed"))
    with pytest.raises(RuntimeError, match="did not complete"):
        assistant.run_tool_loop("Test", [], [])


def test_unavailable_functions_are_never_dispatched(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(copy.deepcopy(kwargs))
        if len(calls) == 1:
            return response([{"type": "function_call", "name": "propose_event_create",
                              "call_id": "denied", "arguments": "{}"}])
        assert "error" in json.loads(kwargs["input"][-1]["output"])
        return response([message()])

    monkeypatch.setattr(assistant.client.responses, "create", create)
    assistant.run_tool_loop("Test", [], [])


@pytest.mark.parametrize("setting,value", [
    ("HUGO_WEB_SEARCH_ENABLED", "maybe"), ("HUGO_WEB_SEARCH_MAX_CALLS", "0"),
    ("HUGO_WEB_SEARCH_MAX_CALLS", "11"), ("HUGO_WEB_SEARCH_MAX_CALLS", "many"),
])
def test_invalid_configuration_fails_before_api(monkeypatch, setting, value):
    monkeypatch.setenv(setting, value)
    with pytest.raises(ValueError):
        assistant.run_tool_loop("Test", [], [])


def test_citations_preserve_claims_unicode_and_multiple_sources():
    text = "Änderung bestätigt.\ue200cite\ue202turn0search0\ue201 Danach folgt mehr."
    end = text.index(" Danach")
    annotations = [
        {"type": "url_citation", "url": "https://example.org/race(2027)",
         "title": "[Veranstalter]", "start_index": 0, "end_index": end},
        {"type": "url_citation", "url": "https://example.net/", "title": "Zweitquelle", "end_index": end},
        {"type": "url_citation", "url": "javascript:alert(1)", "end_index": end},
    ]
    result = web_research.cited_response_text([message(text, annotations)], text)
    assert result.startswith("Änderung bestätigt.")
    assert result.endswith(" Danach folgt mehr.")
    assert "[Veranstalter](https://example.org/race%282027%29)" in result
    assert "[Zweitquelle](https://example.net/)" in result
    assert "turn0search0" not in result
    assert "javascript" not in result


def test_invalid_citation_position_keeps_source_at_end():
    result = web_research.cited_response_text([message("Text", [
        {"type": "url_citation", "url": "https://example.org/", "end_index": 999},
    ])], "")
    assert result == "Text [example.org](https://example.org/)"


def test_existing_inline_link_is_not_duplicated_but_later_claim_gets_its_source():
    link = "[Veranstalter](https://example.org/race)"
    text = f"Erster Termin. ({link}) Zweiter Termin."
    first_end = text.index(" Zweiter")
    result = web_research.cited_response_text([message(text, [
        {"type": "url_citation", "url": "https://example.org/race", "title": "Veranstalter",
         "start_index": text.index("("), "end_index": first_end},
        {"type": "url_citation", "url": "https://example.org/race", "title": "Veranstalter",
         "start_index": first_end + 1, "end_index": len(text)},
    ])], text)
    assert result.count(link) == 2
    assert result.startswith(text)
    assert result.endswith("Zweiter Termin. " + link)


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "data:text/html,bad", "//example.org", "https://user:pass@example.org",
    "https://example.org/\nnext", 'https://example.org/"onclick="bad', "https://example.org:bad/",
    "https://example.org\\evil", "https:///missing-host", None,
])
def test_unsafe_source_urls_rejected(url):
    assert source_url(url) is None


def test_source_renderer_escapes_html_and_link_attributes():
    rendered = str(source_links('<script>alert(1)</script> [<b>Quelle</b>](https://example.org/?a=1&b=2) [x](javascript:alert(1))'))
    assert '<script>' not in rendered and '<b>' not in rendered
    assert '&lt;script&gt;' in rendered and '&lt;b&gt;Quelle&lt;/b&gt;' in rendered
    assert 'href="https://example.org/?a=1&amp;b=2"' in rendered
    assert 'href="javascript:' not in rendered
    assert 'rel="noopener noreferrer"' in rendered
