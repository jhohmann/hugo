"""Context construction without network calls or model-based assertions."""

from types import SimpleNamespace

import pytest

from app.agent import chat_context as context


def records(count=13, size=600):
    return [{"id": i + 1, "role": "user" if i % 2 == 0 else "assistant",
             "content": f"Nachricht {i}: " + "x" * size,
             "created_at": "2026-11-09T10:00:00+01:00"} for i in range(count)]


@pytest.fixture
def state(monkeypatch):
    data = {"summary": None, "messages": records(), "calls": [], "saves": []}
    monkeypatch.setenv("HUGO_CHAT_HISTORY_TOKENS", "2000")
    monkeypatch.setattr(context, "load_context", lambda *_: (
        data["summary"], [m for m in data["messages"]
                          if m["id"] > (data["summary"] or {}).get("through_message_id", 0)]))

    def summarize(previous, batch, limit):
        data["calls"].append((previous, list(batch)))
        return "Projekt bleibt unverbindlich; Rückmeldung steht aus."

    def save(cid, through, content, expected):
        data["saves"].append((through, expected))
        data["summary"] = {"through_message_id": through, "content": content}
        return True

    monkeypatch.setattr(context, "summarize", summarize)
    monkeypatch.setattr(context, "save_summary", save)
    return data


def test_short_history_does_not_call_summary(state):
    state["messages"] = records(3, 20)
    assert context.prepare_context(1, 3) == context.as_input(None, state["messages"])
    assert state["calls"] == state["saves"] == []


def test_long_history_keeps_recent_turns_and_reuses_checkpoint(state):
    originals = list(state["messages"])
    prepared = context.prepare_context(1, 13)
    assert len(state["calls"]) == 1
    assert prepared[0]["role"] == "user"  # never elevate derived text to system instructions
    assert prepared[1:] == context.as_input(None, originals[6:])
    assert state["calls"][0][1] == originals[:6]  # includes timestamps for relative dates
    assert context.estimate_tokens(prepared) < 2000
    assert state["messages"] == originals
    assert context.prepare_context(1, 13) == prepared
    assert len(state["calls"]) == 1
    state["messages"].extend({**m, "id": m["id"] + 13} for m in records(8))
    context.prepare_context(1, 21)
    assert state["calls"][1][0] == state["summary"]["content"]
    assert all(m["id"] > 6 for m in state["calls"][1][1])


@pytest.mark.parametrize("failure", ["model", "storage", "conflict", "no_reduction"])
def test_failed_compaction_keeps_all_pending_text(state, monkeypatch, failure):
    state["summary"] = {"through_message_id": 1, "content": "Vorheriger Kontext"}
    expected = context.as_input(state["summary"], state["messages"][1:])

    def fail(*_):
        raise RuntimeError("simulated")

    if failure == "model":
        monkeypatch.setattr(context, "summarize", fail)
    elif failure == "storage":
        monkeypatch.setattr(context, "save_summary", fail)
    elif failure == "conflict":
        monkeypatch.setattr(context, "save_summary", lambda *_: False)
    else:
        monkeypatch.setattr(context, "summarize", lambda *_: "x" * 20000)
    assert context.prepare_context(1, 13) == expected


def test_oversized_recent_turn_is_never_truncated(state):
    state["messages"] = records(5, 4000)
    assert context.prepare_context(1, 5) == context.as_input(None, state["messages"])
    assert not state["calls"]


def test_backlog_work_is_bounded_and_unprocessed_text_retained(state, monkeypatch):
    state["messages"] = records(80)
    monkeypatch.setattr(context, "MAX_SUMMARY_CALLS", 2)
    result = context.prepare_context(1, 80)
    assert len(state["calls"]) == 2
    cutoff = state["summary"]["through_message_id"]
    assert result[1:] == context.as_input(None, state["messages"][cutoff:])


@pytest.mark.parametrize("status,text", [("incomplete", "Teil"), ("completed", ""),
                                         ("completed", "x" * 101)])
def test_incomplete_summaries_are_rejected(monkeypatch, status, text):
    fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: SimpleNamespace(
        status=status, output_text=text, usage=None)))
    monkeypatch.setattr(context, "client", SimpleNamespace(with_options=lambda **_: fake))
    with pytest.raises(ValueError):
        context.summarize("", records(1), 100)


def test_summary_request_has_no_tools_and_contains_source_dates(monkeypatch):
    requests = []

    def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(status="completed", output_text="Gültiger Kontext", usage=None)

    fake = SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr(context, "client", SimpleNamespace(with_options=lambda **_: fake))
    assert context.summarize("Alter Kontext", records(1), 100) == "Gültiger Kontext"
    assert not requests[0].get("tools")
    assert "2026-11-09" in requests[0]["input"][0]["content"]
    assert "Alter Kontext" in requests[0]["input"][0]["content"]


@pytest.mark.parametrize("value", ["0", "1999", "60001", "invalid"])
def test_invalid_budget(monkeypatch, value):
    monkeypatch.setenv("HUGO_CHAT_HISTORY_TOKENS", value)
    with pytest.raises(ValueError):
        context.history_budget()
