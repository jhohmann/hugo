"""Calendar identifiers must remain a single URL path segment."""

from datetime import datetime, timezone

import httpx
import pytest

from app.calendar import client


@pytest.mark.parametrize("operation,method,individual", [
    ("list", "GET", False),
    ("search", "GET", False),
    ("get", "GET", True),
    ("insert", "POST", False),
    ("patch", "PATCH", True),
    ("delete", "DELETE", True),
])
def test_calendar_ids_with_hash_reach_google_intact(monkeypatch, operation, method, individual):
    calendar_id = "de.german#holiday@group.v.calendar.google.com"
    event_id = "event/id?x#z%"
    expected = b"/calendar/v3/calendars/de.german%23holiday%40group.v.calendar.google.com/events"
    if individual:
        expected += b"/event%2Fid%3Fx%23z%25"
    requests = []

    def request(actual_method, url, **kwargs):
        outgoing = httpx.Request(actual_method, url, params=kwargs.get("params"))
        assert actual_method == method
        assert outgoing.url.fragment == ""
        assert outgoing.url.raw_path.split(b"?", 1)[0] == expected
        requests.append(outgoing)
        return httpx.Response(200, json={"items": []}, request=outgoing)

    monkeypatch.setattr(client, "_access_token", lambda: "test-token")
    monkeypatch.setattr(client.httpx, "request", request)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2028, 1, 1, tzinfo=timezone.utc)
    if operation == "list":
        client.list_events(calendar_id, start, end)
    elif operation == "search":
        client.search_events(calendar_id, start, end, "Getzen")
    elif operation == "get":
        client.get_event(calendar_id, event_id)
    elif operation == "insert":
        client.insert_event(calendar_id, {})
    elif operation == "patch":
        client.patch_event(calendar_id, event_id, {})
    else:
        client.delete_event(calendar_id, event_id)
    assert len(requests) == 1
