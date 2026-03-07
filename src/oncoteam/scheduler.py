"""APScheduler lifespan for autonomous task scheduling."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from .config import AUTONOMOUS_ENABLED

logger = logging.getLogger("oncoteam.scheduler")


def _create_scheduler():
    """Create and configure the async scheduler with all jobs."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    from .autonomous_tasks import (
        run_daily_research,
        run_file_scan,
        run_mtb_preparation,
        run_pre_cycle_check,
        run_response_assessment,
        run_trial_monitor,
        run_tumor_marker_review,
        run_weekly_briefing,
    )

    scheduler = AsyncIOScheduler()

    # === Clinical protocol schedule ===

    # Pre-cycle check: every 13 days (1 day before each 14-day FOLFOX cycle)
    scheduler.add_job(run_pre_cycle_check, IntervalTrigger(days=13), id="pre_cycle_check")

    # Tumor marker review: every 4 weeks
    scheduler.add_job(run_tumor_marker_review, IntervalTrigger(weeks=4), id="tumor_marker_review")

    # Response assessment prep: every 8 weeks
    scheduler.add_job(run_response_assessment, IntervalTrigger(weeks=8), id="response_assessment")

    # === Research schedule ===

    # Daily research scan: 7:00 UTC (8:00 CET)
    scheduler.add_job(run_daily_research, CronTrigger(hour=7, minute=0), id="daily_research")

    # Trial monitor: every 6 hours
    scheduler.add_job(run_trial_monitor, IntervalTrigger(hours=6), id="trial_monitor")

    # File scan (new oncofiles documents): every 2 hours
    scheduler.add_job(run_file_scan, IntervalTrigger(hours=2), id="file_scan")

    # === Reporting schedule ===

    # Weekly briefing: Monday 6:00 UTC (7:00 CET)
    scheduler.add_job(
        run_weekly_briefing, CronTrigger(day_of_week="mon", hour=6), id="weekly_briefing"
    )

    # MTB preparation: Friday 14:00 UTC (prepare for Monday MTB)
    scheduler.add_job(
        run_mtb_preparation, CronTrigger(day_of_week="fri", hour=14), id="mtb_preparation"
    )

    return scheduler


@asynccontextmanager
async def autonomous_lifespan(server):
    """FastMCP lifespan: start/stop the autonomous scheduler."""
    if not AUTONOMOUS_ENABLED:
        logger.info("Autonomous agent disabled (AUTONOMOUS_ENABLED=false)")
        yield {}
        return

    scheduler = _create_scheduler()
    scheduler.start()
    logger.info("Autonomous scheduler started with %d jobs", len(scheduler.get_jobs()))

    try:
        yield {"scheduler": scheduler}
    finally:
        scheduler.shutdown(wait=False)
        logger.info("Autonomous scheduler stopped")
