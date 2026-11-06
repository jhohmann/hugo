"""
Background-Worker für Hugo mit täglicher proaktiver Auswertung.

Startet einen APScheduler, der um 06:00 UTC täglich run_evaluation(trigger='scheduled') aufruft.
Dieser Worker läuft als separater Container in der Produktionsumgebung.
"""

import logging
import os
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from app.config import load_environment

logger = logging.getLogger(__name__)


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


def run_worker(schedule_hour: int = 6, schedule_minute: int = 0):
    """
    Startet den Background-Worker mit APScheduler.
    
    Args:
        schedule_hour: Stunde (0-23 UTC) für die tägliche Auswertung (default: 6)
        schedule_minute: Minute (0-59) für die tägliche Auswertung (default: 0)
    """
    configure_logging()
    
    logger.info("Hugo Background Worker starting...")
    logger.info(f"Scheduled evaluation: daily at {schedule_hour:02d}:{schedule_minute:02d} UTC")
    
    scheduler = BlockingScheduler()
    
    # Registriere die tägliche Auswertung
    scheduler.add_job(
        scheduled_evaluation,
        "cron",
        hour=schedule_hour,
        minute=schedule_minute,
        id="daily_evaluation",
        name="Daily Proactivity Evaluation",
        timezone="UTC",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    
    # Logging für Scheduler-Events
    def log_job_executed(event):
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
    # Konfigurierbar via Umgebungsvariablen
    hour = int(os.getenv("SCHEDULER_HOUR", "6"))
    minute = int(os.getenv("SCHEDULER_MINUTE", "0"))
    run_worker(schedule_hour=hour, schedule_minute=minute)
