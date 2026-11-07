"""Kalendersuche: echter Werkzeugpfad mit simulierten Google-Antworten."""

from datetime import datetime

import httpx
import pytest

from app.agent import assistant, evaluation
from app.calendar import client
from app.tools import dates


@pytest.fixture(autouse=True)
def no_google_access(monkeypatch):
    def unexpected_request(*args, **kwargs):
        pytest.fail("Unerwarteter Google-Zugriff")

    monkeypatch.setattr(client, "_request", unexpected_request)
    monkeypatch.setattr(
        dates, "now_berlin", lambda: datetime(2026, 11, 7, tzinfo=dates.BERLIN)
    )


def event(event_id, start="2027-06-01T10:00:00+02:00"):
    return {
        "id": event_id,
        "summary": "Fortbildung",
        "start": {"dateTime": start},
        "end": {"dateTime": "2027-06-01T12:00:00+02:00"},
        "status": "confirmed",
    }


def invoke(**kwargs):
    return assistant.execute_tool("search_events", {
        "query": "Fortbildung", "calendar_id": None, "limit": 20,
        "offset": 0, **kwargs,
    })


def test_search_loads_all_calendar_and_event_pages_before_tool_pagination(monkeypatch):
    calls = []

    def request(method, path, **kwargs):
        assert method == "GET"
        params = kwargs["params"]
        calls.append((path, dict(params)))
        token = params.get("pageToken")
        if path == "/users/me/calendarList":
            assert params["showHidden"] == "true"
            data = (
                {"items": [{"id": "work", "accessRole": "reader"}],
                 "nextPageToken": "more-calendars"}
                if token is None else
                {"items": [{"id": "private", "accessRole": "owner"}]}
            )
        else:
            assert params["q"] == "Fortbildung"
            assert params["timeMin"] == "2026-01-01T00:00:00+01:00"
            assert params["timeMax"] == "2028-01-01T00:00:00+01:00"
            assert params["timeZone"] == "Europe/Berlin"
            assert params["singleEvents"] == "true"
            assert params["showDeleted"] == "false"
            if path == "/calendars/work/events":
                if token is None:
                    data = {"items": [event(f"series-{i:03}") for i in range(101)],
                            "nextPageToken": "empty-page"}
                elif token == "empty-page":
                    data = {"items": [], "nextPageToken": "last-page"}
                else:
                    data = {"items": [event("late", "2027-12-31T10:00:00+01:00"),
                                      {"id": "cancelled", "status": "cancelled"}]}
            else:
                data = {"items": [{
                    "id": "past-all-day", "summary": "Fortbildung",
                    "start": {"date": "2026-01-01"},
                    "end": {"date": "2026-01-02"},
                }]}
        return httpx.Response(200, json=data)

    monkeypatch.setattr(client, "_request", request)
    first = invoke(limit=100)
    assert first["total_count"] == 103
    assert first["has_more"] is True
    assert first["next_offset"] == 100
    assert first["searched_calendars"] == ["work", "private"]
    assert first["unsearchable_calendars"] == []
    assert first["events"][0]["event_id"] == "past-all-day"
    assert first["events"][0]["end"] == "2026-01-01"
    assert first["events"][0]["all_day"] is True
    last = invoke(limit=100, offset=first["next_offset"])
    assert [e["event_id"] for e in last["events"]] == ["series-099", "series-100", "late"]
    assert last["has_more"] is False
    assert last["next_offset"] is None
    assert len(calls) == 12


@pytest.mark.parametrize("instant,year", [
    ("2026-12-31T22:59:59+00:00", 2026),
    ("2026-12-31T23:00:00+00:00", 2027),
    ("2027-12-31T23:00:00+00:00", 2028),
])
def test_search_year_follows_berlin_year_boundary(monkeypatch, instant, year):
    monkeypatch.setattr(dates, "now_berlin", lambda: datetime.fromisoformat(instant).astimezone(dates.BERLIN))
    monkeypatch.setattr(client, "list_calendars", lambda: [])
    result = invoke()
    assert result["time_min"] == f"{year}-01-01T00:00:00+01:00"
    assert result["time_max"] == f"{year + 2}-01-01T00:00:00+01:00"
    assert result["total_count"] == 0
    assert result["events"] == []
    assert result["has_more"] is False


def test_search_sorting_uses_actual_instants_and_calendar_filter(monkeypatch):
    monkeypatch.setattr(client, "list_calendars", lambda: [{"id": "work"}, {"id": "private"}])

    def search(calendar_id, time_min, time_max, query):
        assert calendar_id == "private"
        assert query == "Fortbildung"
        return [event("later", "2027-06-01T09:00:00Z"),
                event("earlier", "2027-06-01T10:00:00+02:00")]

    monkeypatch.setattr(client, "search_events", search)
    result = invoke(query=" Fortbildung ", calendar_id="private")
    assert [e["event_id"] for e in result["events"]] == ["earlier", "later"]
    assert result["searched_calendars"] == ["private"]
    with pytest.raises(ValueError, match="Kalender nicht gefunden"):
        invoke(calendar_id="unknown")


def test_search_marks_calendars_without_readable_details(monkeypatch):
    monkeypatch.setattr(client, "list_calendars", lambda: [
        {"id": "busy-only", "access_role": "freeBusyReader"},
        {"id": "readable", "access_role": "reader"},
    ])
    calls = []

    def search(calendar_id, *args):
        calls.append(calendar_id)
        return []

    monkeypatch.setattr(client, "search_events", search)
    result = invoke()
    assert calls == ["readable"]
    assert result["unsearchable_calendars"] == ["busy-only"]
    assert result["searched_calendars"] == ["readable"]


def test_google_failure_does_not_return_partial_results_as_success(monkeypatch):
    monkeypatch.setattr(client, "list_calendars", lambda: [{"id": "first"}, {"id": "second"}])

    def search(calendar_id, *args):
        if calendar_id == "second":
            raise client.GoogleApiError(503, "Unavailable")
        return [event("found")]

    monkeypatch.setattr(client, "search_events", search)
    with pytest.raises(client.GoogleApiError):
        invoke()


def test_disconnected_search_returns_existing_error_contract(monkeypatch):
    def disconnected():
        raise client.CalendarNotConnectedError()

    monkeypatch.setattr(client, "list_calendars", disconnected)
    assert invoke() == {"error": "not_connected"}


@pytest.mark.parametrize("arguments", [
    {"query": " "}, {"query": "x" * 201}, {"query": None},
    {"limit": 0}, {"limit": 101}, {"limit": True},
    {"offset": -1}, {"offset": 1.5},
])
def test_invalid_search_rejected_before_io(arguments):
    with pytest.raises(ValueError):
        invoke(**arguments)


def test_search_available_in_chat_and_evaluation_with_strict_schema():
    for tools in (assistant.TOOLS, evaluation.EVALUATION_TOOLS):
        tool = next(t for t in tools if t["name"] == "search_events")
        assert tool["strict"] is True
        schema = tool["parameters"]
        assert set(schema["properties"]) == set(schema["required"])
        assert schema["additionalProperties"] is False
