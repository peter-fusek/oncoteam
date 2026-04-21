"""APScheduler lifespan for autonomous task scheduling.

Reads agent configurations from agent_registry.py — no hardcoded schedules.
"""

from __future__ import annotations

import logging

import httpx
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED

from .agent_registry import AGENT_REGISTRY, ScheduleType
from .config import AUTONOMOUS_ENABLED, ONCOFILES_MCP_URL
from .patient_context import get_patient, list_patient_ids

logger = logging.getLogger("oncoteam.scheduler")


def _job_listener(event):
    """Log job execution results for observability."""
    if hasattr(event, "exception") and event.exception:
        logger.error("Job %s FAILED: %s", event.job_id, event.exception)
    elif hasattr(event, "job_id"):
        logger.info("Job %s completed successfully", event.job_id)


async def _keepalive_ping():
    """Ping oncofiles /health to prevent Railway cold start."""
    base = ONCOFILES_MCP_URL.rsplit("/", 1)[0] if "/" in ONCOFILES_MCP_URL else ONCOFILES_MCP_URL
    health_url = f"{base}/health"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(health_url)
            logger.debug("Keep-alive ping %s -> %d", health_url, resp.status_code)
    except Exception as e:
        logger.warning("Keep-alive ping failed: %s", e)


def _get_task_functions() -> dict:
    """Map agent IDs to their callable functions."""
    from .autonomous_tasks import (
        run_daily_cost_report,
        run_daily_research,
        run_ddr_monitor,
        run_document_pipeline_drain,
        run_family_update,
        run_file_scan,
        run_funnel_assess,
        run_health_monitor,
        run_lab_sync,
        run_medication_adherence_check,
        run_mtb_preparation,
        run_pre_cycle_check,
        run_protocol_review,
        run_response_assessment,
        run_self_improvement,
        run_toxicity_extraction,
        run_trial_monitor,
        run_tumor_marker_review,
        run_weekly_briefing,
        run_weight_extraction,
    )

    return {
        "keepalive_ping": _keepalive_ping,
        "health_monitor": run_health_monitor,
        "file_scan": run_file_scan,
        "lab_sync": run_lab_sync,
        "toxicity_extraction": run_toxicity_extraction,
        "weight_extraction": run_weight_extraction,
        "daily_research": run_daily_research,
        "trial_monitor": run_trial_monitor,
        "ddr_monitor": run_ddr_monitor,
        "pre_cycle_check": run_pre_cycle_check,
        "tumor_marker_review": run_tumor_marker_review,
        "response_assessment": run_response_assessment,
        "protocol_review": run_protocol_review,
        "weekly_briefing": run_weekly_briefing,
        "mtb_preparation": run_mtb_preparation,
        "family_update": run_family_update,
        "medication_adherence_check": run_medication_adherence_check,
        "daily_cost_report": run_daily_cost_report,
        "self_improvement": run_self_improvement,
        "funnel_assess": run_funnel_assess,
        "document_pipeline_drain": run_document_pipeline_drain,
    }


def _create_scheduler():
    """Create scheduler with jobs from agent registry."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = AsyncIOScheduler()
    scheduler.add_listener(_job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED | EVENT_JOB_MISSED)

    task_functions = _get_task_functions()

    patient_ids = list_patient_ids()

    for agent_id, config in AGENT_REGISTRY.items():
        if not config.enabled:
            continue
        func = task_functions.get(agent_id)
        if func is None:
            logger.warning("No function for agent %s, skipping", agent_id)
            continue

        trigger_cls = (
            IntervalTrigger if config.schedule_type == ScheduleType.INTERVAL else CronTrigger
        )

        # System agents run once, not per-patient
        if agent_id in ("keepalive_ping", "health_monitor"):
            trigger = trigger_cls(**config.schedule_params)
            scheduler.add_job(
                func,
                trigger,
                id=agent_id,
                misfire_grace_time=config.misfire_grace_time,
                coalesce=True,
            )
            continue

        # Create a job per patient to ensure all patients get agent coverage
        for i, pid in enumerate(patient_ids):
            patient = get_patient(pid)
            # Paused patient: no scheduled agents. Profile data intact.
            if patient.paused:
                continue
            # Skip agents not in patient's whitelist (empty = all agents)
            if patient.agent_whitelist and agent_id not in patient.agent_whitelist:
                continue

            def _make_runner(_fn=func, _pid=pid):
                async def _run():
                    return await _fn(patient_id=_pid)

                return _run

            trigger_params = dict(config.schedule_params)
            # Stagger multi-patient jobs by 2 minutes to avoid pile-on
            if i > 0 and config.schedule_type == ScheduleType.CRON:
                minute = trigger_params.get("minute", 0)
                if isinstance(minute, int):
                    trigger_params["minute"] = (minute + i * 2) % 60

            trigger = trigger_cls(**trigger_params)
            job_id = f"{agent_id}:{pid}" if len(patient_ids) > 1 else agent_id

            scheduler.add_job(
                _make_runner(),
                trigger,
                id=job_id,
                misfire_grace_time=config.misfire_grace_time,
                coalesce=True,
            )

    logger.info(
        "Scheduler configured for %d patients × %d agents",
        len(patient_ids),
        len([a for a in AGENT_REGISTRY.values() if a.enabled]),
    )

    return scheduler


# ── Standalone scheduler (single instance for all transports) ──

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


def stop_scheduler() -> None:
    """Stop the autonomous scheduler if running."""
    global _standalone_scheduler
    if _standalone_scheduler is None:
        return
    _standalone_scheduler.shutdown(wait=False)
    logger.info("Autonomous scheduler stopped")
    _standalone_scheduler = None


def get_scheduler_status() -> dict:
    """Return scheduler status for health endpoints."""
    if _standalone_scheduler is None:
        return {"running": False, "jobs": 0}
    jobs = _standalone_scheduler.get_jobs()
    return {
        "running": _standalone_scheduler.running,
        "jobs": len(jobs),
        "job_ids": [j.id for j in jobs],
    }
