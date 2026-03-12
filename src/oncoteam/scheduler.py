"""APScheduler lifespan for autonomous task scheduling."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED

from .config import AUTONOMOUS_ENABLED, ONCOFILES_MCP_URL

logger = logging.getLogger("oncoteam.scheduler")


def _job_listener(event):
    """Log job execution results for observability."""
    if hasattr(event, "exception") and event.exception:
        logger.error("Job %s FAILED: %s", event.job_id, event.exception)
    elif hasattr(event, "job_id"):
        logger.info("Job %s completed successfully", event.job_id)


async def _keepalive_ping():
    """Ping oncofiles /health to prevent Railway cold start."""
    # Derive health URL from MCP URL (e.g. .../mcp -> .../health)
    base = ONCOFILES_MCP_URL.rsplit("/", 1)[0] if "/" in ONCOFILES_MCP_URL else ONCOFILES_MCP_URL
    health_url = f"{base}/health"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(health_url)
            logger.debug("Keep-alive ping %s -> %d", health_url, resp.status_code)
    except Exception as e:
        logger.debug("Keep-alive ping failed: %s", e)


def _create_scheduler():
    """Create and configure the async scheduler with all jobs."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    from .autonomous_tasks import (
        run_daily_research,
        run_family_update,
        run_file_scan,
        run_lab_sync,
        run_medication_adherence_check,
        run_mtb_preparation,
        run_pre_cycle_check,
        run_response_assessment,
        run_toxicity_extraction,
        run_trial_monitor,
        run_tumor_marker_review,
        run_weekly_briefing,
        run_weight_extraction,
    )

    scheduler = AsyncIOScheduler()

    # Event listeners for observability
    scheduler.add_listener(_job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED | EVENT_JOB_MISSED)

    now = datetime.now(UTC)

    # === Keep-alive: prevent oncofiles Railway cold start ===
    scheduler.add_job(_keepalive_ping, IntervalTrigger(minutes=5), id="keepalive_ping")

    # === Data pipeline — run first (populate labs, documents) ===

    # File scan (new oncofiles documents): every 2 hours
    scheduler.add_job(
        run_file_scan,
        IntervalTrigger(hours=2),
        id="file_scan",
        next_run_time=now + timedelta(minutes=2),
        misfire_grace_time=7200,
        coalesce=True,
    )

    # Lab sync: every 6 hours (extract lab values from documents)
    scheduler.add_job(
        run_lab_sync,
        IntervalTrigger(hours=6),
        id="lab_sync",
        next_run_time=now + timedelta(minutes=3),
        misfire_grace_time=21600,
        coalesce=True,
    )

    # Toxicity extraction: daily at 08:00 UTC
    scheduler.add_job(
        run_toxicity_extraction,
        CronTrigger(hour=8, minute=0),
        id="toxicity_extraction",
        next_run_time=now + timedelta(minutes=4),
        misfire_grace_time=86400,
        coalesce=True,
    )

    # Weight extraction: daily at 09:00 UTC
    scheduler.add_job(
        run_weight_extraction,
        CronTrigger(hour=9, minute=0),
        id="weight_extraction",
        next_run_time=now + timedelta(minutes=5),
        misfire_grace_time=86400,
        coalesce=True,
    )

    # === Research — after data pipeline ===

    # Daily research scan: 7:00 UTC (8:00 CET)
    scheduler.add_job(
        run_daily_research,
        CronTrigger(hour=7, minute=0),
        id="daily_research",
        next_run_time=now + timedelta(minutes=7),
        misfire_grace_time=86400,
        coalesce=True,
    )

    # Trial monitor: every 6 hours
    scheduler.add_job(
        run_trial_monitor,
        IntervalTrigger(hours=6),
        id="trial_monitor",
        next_run_time=now + timedelta(minutes=8),
        misfire_grace_time=21600,
        coalesce=True,
    )

    # === Clinical — after research ===

    # Pre-cycle check: every 13 days (1 day before each 14-day FOLFOX cycle)
    scheduler.add_job(
        run_pre_cycle_check,
        IntervalTrigger(days=13),
        id="pre_cycle_check",
        next_run_time=now + timedelta(minutes=9),
        misfire_grace_time=86400 * 2,
        coalesce=True,
    )

    # Tumor marker review: every 4 weeks
    scheduler.add_job(
        run_tumor_marker_review,
        IntervalTrigger(weeks=4),
        id="tumor_marker_review",
        next_run_time=now + timedelta(minutes=10),
        misfire_grace_time=86400 * 7,
        coalesce=True,
    )

    # Response assessment prep: every 8 weeks
    scheduler.add_job(
        run_response_assessment,
        IntervalTrigger(weeks=8),
        id="response_assessment",
        next_run_time=now + timedelta(minutes=11),
        misfire_grace_time=86400 * 14,
        coalesce=True,
    )

    # === Reporting — last (depends on data from above) ===

    # Weekly briefing: Monday 6:00 UTC (7:00 CET)
    scheduler.add_job(
        run_weekly_briefing,
        CronTrigger(day_of_week="mon", hour=6),
        id="weekly_briefing",
        next_run_time=now + timedelta(minutes=12),
        misfire_grace_time=86400 * 2,
        coalesce=True,
    )

    # MTB preparation: Friday 14:00 UTC (prepare for Monday MTB)
    scheduler.add_job(
        run_mtb_preparation,
        CronTrigger(day_of_week="fri", hour=14),
        id="mtb_preparation",
        next_run_time=now + timedelta(minutes=13),
        misfire_grace_time=86400 * 2,
        coalesce=True,
    )

    # Family update: Sunday 18:00 UTC (weekly family summary in Slovak)
    scheduler.add_job(
        run_family_update,
        CronTrigger(day_of_week="sun", hour=18),
        id="family_update",
        next_run_time=now + timedelta(minutes=14),
        misfire_grace_time=86400 * 2,
        coalesce=True,
    )

    # Medication adherence check: daily 20:00 UTC
    scheduler.add_job(
        run_medication_adherence_check,
        CronTrigger(hour=20, minute=0),
        id="medication_adherence_check",
        next_run_time=now + timedelta(minutes=15),
        misfire_grace_time=86400,
        coalesce=True,
    )

    return scheduler


@asynccontextmanager
async def autonomous_lifespan(server):
    """FastMCP lifespan: start/stop the autonomous scheduler.

    NOTE: In FastMCP 3.x HTTP transport, lifespans are double-wrapped and the
    second entry hits an early-exit guard, so this may not fire. As a fallback,
    start_scheduler() is called explicitly from main() for HTTP mode.
    """
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


# ── Standalone scheduler for HTTP transport workaround ──

_standalone_scheduler = None


def start_scheduler() -> None:
    """Start the autonomous scheduler (AsyncIOScheduler).

    Called from async main_async() for HTTP transport where FastMCP lifespan
    is broken. Must be called from within a running asyncio event loop.
    Safe to call multiple times — only starts once.
    """
    global _standalone_scheduler
    if _standalone_scheduler is not None:
        return
    if not AUTONOMOUS_ENABLED:
        logger.info("Autonomous agent disabled (AUTONOMOUS_ENABLED=false)")
        return

    _standalone_scheduler = _create_scheduler()
    _standalone_scheduler.start()
    logger.info(
        "Autonomous scheduler started (standalone) with %d jobs",
        len(_standalone_scheduler.get_jobs()),
    )
