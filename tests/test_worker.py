from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from apscheduler.schedulers.blocking import BlockingScheduler

from app import worker
from datetime import datetime, timedelta, timezone

import pytest


def test_worker_can_start_with_valid_listeners_and_single_daily_job(monkeypatch):
    inspected = []

    def inspect(scheduler):
        job, = scheduler.get_jobs()
        assert str(job.trigger.timezone) == "Europe/Berlin"
        assert job.max_instances == 1 and job.coalesce
        assert {mask for _, mask in scheduler._listeners} == {EVENT_JOB_EXECUTED, EVENT_JOB_ERROR}
        inspected.append(True)

    monkeypatch.setattr(BlockingScheduler, "start", inspect)
    worker.run_worker(6, 30)
    assert inspected


def test_successful_evaluation_logs_completed_result(monkeypatch, caplog):
    from app.agent import evaluation
    monkeypatch.setattr(evaluation, "run_evaluation", lambda trigger: {"status": "completed", "suggestions_created": 2})
    with caplog.at_level("INFO"):
        worker.scheduled_evaluation()
    assert "Generated 2 suggestions" in caplog.text
    assert "failed" not in caplog.text


@pytest.mark.parametrize("day, utc_hour", [
    ("2027-01-15", 7), ("2027-07-15", 6),
    ("2027-03-28", 6), ("2027-10-31", 7),
])
def test_daily_evaluation_stays_at_eight_berlin_across_dst(monkeypatch, day, utc_hour):
    monkeypatch.delenv("SCHEDULER_HOUR", raising=False)
    monkeypatch.delenv("SCHEDULER_MINUTE", raising=False)

    def inspect(scheduler):
        trigger = scheduler.get_job("daily_evaluation").trigger
        start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
        first = trigger.get_next_fire_time(None, start)
        assert (first.hour, first.minute) == (8, 0)
        assert first.astimezone(timezone.utc).hour == utc_hour
        following = trigger.get_next_fire_time(first, first + timedelta(seconds=1))
        assert following.date() == first.date() + timedelta(days=1)
        assert (following.hour, following.minute) == (8, 0)

    monkeypatch.setattr(BlockingScheduler, "start", inspect)
    worker.run_worker()
