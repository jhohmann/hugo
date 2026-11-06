from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from apscheduler.schedulers.blocking import BlockingScheduler

from app import worker


def test_worker_can_start_with_valid_listeners_and_single_daily_job(monkeypatch):
    inspected = []

    def inspect(scheduler):
        job, = scheduler.get_jobs()
        assert str(job.trigger.timezone) == "UTC"
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
