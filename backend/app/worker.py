"""
Background-Worker für Hugo mit täglicher proaktiver Auswertung.

Startet einen APScheduler, der um 08:00 Europe/Berlin täglich run_evaluation(trigger='scheduled') aufruft.
Dieser Worker läuft als separater Container in der Produktionsumgebung.
"""

import logging
import os
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from app.config import load_environment
from app import settings

logger = logging.getLogger(__name__)
SCHEDULE_TIMEZONE = "Europe/Berlin"


def configure_logging():
    """Konfiguriert strukturiertes Logging für den Worker."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def scheduled_evaluation():
    """Wird täglich aufgerufen und führt die proaktive Auswertung durch."""
    logger.info("Starting scheduled evaluation run...")
    try:
        from app.agent.evaluation import run_evaluation
        result = run_evaluation(trigger="scheduled")
        logger.info(f"Evaluation completed: {result.get('status', 'unknown')}")
        
        if result.get("status") == "completed":
            suggestions_count = result.get("suggestions_created", 0)
            logger.info(f"Generated {suggestions_count} suggestions")
        else:
            error = result.get("error")
            logger.error(f"Evaluation failed: {error}")
            
    except Exception as e:
        logger.error(f"Error during scheduled evaluation: {str(e)}", exc_info=True)


def configured_schedule():
    values = settings.current()["values"]
    return int(values["SCHEDULER_HOUR"]), int(values["SCHEDULER_MINUTE"])


def sync_schedule(scheduler):
    """Apply shared preferences without restarting a running worker."""
    hour, minute = configured_schedule()
    job = scheduler.get_job("daily_evaluation")
    fields = {field.name: str(field) for field in job.trigger.fields}
    if ((fields["hour"], fields["minute"]) != (str(hour), str(minute))
            or str(job.trigger.timezone) != SCHEDULE_TIMEZONE):
        scheduler.reschedule_job("daily_evaluation", trigger="cron", hour=hour, minute=minute,
                                 timezone=SCHEDULE_TIMEZONE)
        logger.info("Evaluation schedule changed to %02d:%02d %s", hour, minute, SCHEDULE_TIMEZONE)


def run_worker(schedule_hour: int | None = None, schedule_minute: int | None = None):
    """
    Startet den Background-Worker mit APScheduler.
    
    Args:
        schedule_hour: Stunde (0-23 Europe/Berlin) für die tägliche Auswertung (default: 8)
        schedule_minute: Minute (0-59) für die tägliche Auswertung (default: 0)
    """
    configure_logging()
    dynamic_schedule = schedule_hour is None and schedule_minute is None
    if dynamic_schedule:
        schedule_hour, schedule_minute = configured_schedule()
    else:
        schedule_hour = 8 if schedule_hour is None else schedule_hour
        schedule_minute = 0 if schedule_minute is None else schedule_minute
    
    logger.info("Hugo Background Worker starting...")
    logger.info("Scheduled evaluation: daily at %02d:%02d %s", schedule_hour, schedule_minute, SCHEDULE_TIMEZONE)
    
    scheduler = BlockingScheduler()
    
    # Registriere die tägliche Auswertung
    scheduler.add_job(
        scheduled_evaluation,
        "cron",
        hour=schedule_hour,
        minute=schedule_minute,
        id="daily_evaluation",
        name="Daily Proactivity Evaluation",
        timezone=SCHEDULE_TIMEZONE,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    
    if dynamic_schedule:
        scheduler.add_job(sync_schedule, "interval", seconds=60, args=[scheduler],
                          id="settings_sync", max_instances=1, coalesce=True)

    # Logging für Scheduler-Events
    def log_job_executed(event):
        if event.job_id != "settings_sync":
            logger.info(f"Job executed: {event.job_id}")
    
    def log_job_error(event):
        logger.error(f"Job failed: {event.job_id}, exception: {event.exception}")
    
    scheduler.add_listener(
        log_job_executed,
        mask=EVENT_JOB_EXECUTED,
    )
    scheduler.add_listener(
        log_job_error,
        mask=EVENT_JOB_ERROR,
    )
    
    try:
        logger.info("Worker scheduler started (blocking mode)")
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Worker interrupted, shutting down...")
        scheduler.shutdown()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Worker error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    load_environment()
    run_worker()
