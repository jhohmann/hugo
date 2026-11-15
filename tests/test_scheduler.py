"""Scheduler authorization, daily gating and real PostgreSQL exclusion."""
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import Mock

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import auth, main, migrate
from app.agent import evaluation
from app.storage import evaluation as storage
from test_migrations import database


@pytest.mark.parametrize("token,header,code", [
    ("", "", 503), ("short", "Bearer short", 503),
    ("a" * 64, "", 401), ("a" * 64, "Bearer wrong", 401),
    ("a" * 64, "Bearer " + "a" * 64, 200),
])
def test_scheduler_credential_is_scoped(monkeypatch, token, header, code):
    monkeypatch.setenv("HUGO_SCHEDULER_TOKEN", token)
    monkeypatch.setattr(auth, "password_hash", lambda: "configured")
    monkeypatch.setattr(auth.storage, "valid_session", lambda *_: False)
    call = Mock(return_value={"status": "skipped", "reason": "not_due"})
    monkeypatch.setattr(main, "run_evaluation", call)
    with TestClient(main.app) as client:
        headers = {"Authorization": header}
        response = client.post("/internal/proactivity/evaluate", headers=headers)
        assert response.status_code == code
        assert client.post("/proactivity/evaluate", headers=headers).status_code == 401
        assert client.get("/threads", headers=headers).status_code == 401
    if code == 200:
        call.assert_called_once_with(trigger="scheduled", only_if_due=True)
    else:
        call.assert_not_called()


def test_scheduler_failure_is_http_error(monkeypatch):
    monkeypatch.setenv("HUGO_SCHEDULER_TOKEN", "a" * 64)
    monkeypatch.setattr(main, "run_evaluation", Mock(side_effect=RuntimeError("upstream")))
    with TestClient(main.app) as client:
        response = client.post("/internal/proactivity/evaluate", headers={"Authorization": "Bearer " + "a" * 64})
        assert response.status_code == 502
        assert "upstream" not in response.text


@pytest.mark.parametrize("day,hour,expected", [
    ("2027-01-15", 6, False), ("2027-01-15", 7, True),
    ("2027-07-15", 5, False), ("2027-07-15", 6, True),
    ("2027-03-28", 6, True), ("2027-10-31", 7, True),
])
def test_daily_schedule_berlin_dst(day, hour, expected):
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = (False,)
    now = datetime.fromisoformat(day).replace(hour=hour, tzinfo=timezone.utc)
    assert storage.scheduled_due(conn, now) is expected
    conn.execute.return_value.fetchone.return_value = (True,)
    assert not storage.scheduled_due(conn, now)


def test_schedule_changes_are_used_immediately(monkeypatch):
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = (False,)
    now = datetime(2027, 1, 15, 7, tzinfo=timezone.utc)
    monkeypatch.setenv("SCHEDULER_HOUR", "9")
    assert not storage.scheduled_due(conn, now)
    monkeypatch.setenv("SCHEDULER_HOUR", "8")
    assert storage.scheduled_due(conn, now)


def test_all_evaluations_use_lock_and_skip_without_creating_run(monkeypatch):
    @contextmanager
    def busy():
        yield None
    monkeypatch.setattr(evaluation, "evaluation_lock", busy)
    run = Mock()
    monkeypatch.setattr(evaluation, "_run_evaluation", run)
    for trigger in ("manual", "scheduled"):
        assert evaluation.run_evaluation(trigger)["reason"] == "already_running"
    run.assert_not_called()


def test_not_due_does_not_invoke_model(monkeypatch):
    @contextmanager
    def locked():
        yield Mock()
    monkeypatch.setattr(evaluation, "evaluation_lock", locked)
    monkeypatch.setattr(evaluation, "scheduled_due", lambda _: False)
    run = Mock()
    monkeypatch.setattr(evaluation, "_run_evaluation", run)
    assert evaluation.run_evaluation("scheduled", only_if_due=True)["reason"] == "not_due"
    run.assert_not_called()


def test_postgres_lock_release_and_daily_attempts(database, monkeypatch):
    migrate.run_migrations(database)
    monkeypatch.setattr(storage, "get_connection", lambda: psycopg.connect(database))
    with storage.evaluation_lock() as first:
        assert first is not None
        with storage.evaluation_lock() as second:
            assert second is None
    with pytest.raises(RuntimeError):
        with storage.evaluation_lock() as acquired:
            assert acquired is not None
            raise RuntimeError("model failed")
    with storage.evaluation_lock() as acquired:
        assert acquired is not None
        now = datetime(2027, 1, 15, 9, tzinfo=timezone.utc)
        assert storage.scheduled_due(acquired, now)
        acquired.execute("INSERT INTO evaluation_runs (trigger_source, status, started_at) "
                         "VALUES ('scheduled', 'failed', %s)", (now,))
        assert not storage.scheduled_due(acquired, now)
        assert storage.scheduled_due(acquired, now.replace(day=16))


def test_evaluation_holds_lock_until_success_or_failure(monkeypatch):
    held = []
    @contextmanager
    def locked():
        held.append(True)
        try:
            yield Mock()
        finally:
            held.pop()
    monkeypatch.setattr(evaluation, "evaluation_lock", locked)
    monkeypatch.setattr(evaluation, "scheduled_due", lambda _: True)
    def run(trigger):
        assert held and trigger == "scheduled"
        return {"status": "completed", "run_id": 1, "suggestions_created": 0}
    monkeypatch.setattr(evaluation, "_run_evaluation", run)
    assert evaluation.run_evaluation("scheduled", only_if_due=True)["status"] == "completed"
    assert not held
    def fail(trigger):
        assert held
        raise RuntimeError("failed")
    monkeypatch.setattr(evaluation, "_run_evaluation", fail)
    with pytest.raises(RuntimeError):
        evaluation.run_evaluation("manual")
    assert not held
