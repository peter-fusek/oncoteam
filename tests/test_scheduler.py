"""Tests for autonomous scheduler."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from oncoteam.scheduler import start_scheduler, stop_scheduler


class TestSchedulerStandalone:
    @pytest.mark.asyncio
    async def test_disabled_does_not_start(self):
        with (
            patch("oncoteam.scheduler.AUTONOMOUS_ENABLED", False),
            patch("oncoteam.scheduler._standalone_scheduler", None),
        ):
            start_scheduler()
            from oncoteam.scheduler import _standalone_scheduler

            assert _standalone_scheduler is None

    @pytest.mark.asyncio
    async def test_enabled_creates_scheduler(self):
        with (
            patch("oncoteam.scheduler.AUTONOMOUS_ENABLED", True),
            patch("oncoteam.scheduler._standalone_scheduler", None),
        ):
            start_scheduler()
            from oncoteam.scheduler import _standalone_scheduler

            assert _standalone_scheduler is not None
            jobs = _standalone_scheduler.get_jobs()
            assert len(jobs) == 18  # 17 tasks + 1 keepalive ping

            job_ids = {j.id for j in jobs}
            assert "keepalive_ping" in job_ids
            assert "pre_cycle_check" in job_ids
            assert "daily_research" in job_ids
            assert "trial_monitor" in job_ids
            assert "weekly_briefing" in job_ids
            assert "mtb_preparation" in job_ids
            assert "file_scan" in job_ids
            assert "tumor_marker_review" in job_ids
            assert "response_assessment" in job_ids
            assert "lab_sync" in job_ids
            assert "toxicity_extraction" in job_ids
            assert "weight_extraction" in job_ids
            assert "family_update" in job_ids
            assert "medication_adherence_check" in job_ids

            # Clean up
            _standalone_scheduler.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        """start_scheduler() is safe to call multiple times."""
        with (
            patch("oncoteam.scheduler.AUTONOMOUS_ENABLED", True),
            patch("oncoteam.scheduler._standalone_scheduler", None),
        ):
            start_scheduler()
            from oncoteam import scheduler

            first = scheduler._standalone_scheduler
            start_scheduler()
            assert scheduler._standalone_scheduler is first
            first.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_stop_scheduler(self):
        with (
            patch("oncoteam.scheduler.AUTONOMOUS_ENABLED", True),
            patch("oncoteam.scheduler._standalone_scheduler", None),
        ):
            start_scheduler()
            from oncoteam import scheduler

            assert scheduler._standalone_scheduler is not None
            stop_scheduler()
            assert scheduler._standalone_scheduler is None

    @pytest.mark.asyncio
    async def test_multi_patient_job_creation(self):
        """Multi-patient scheduling creates one job per (agent, patient) + keepalive."""
        from oncoteam.scheduler import _create_scheduler

        with patch("oncoteam.scheduler.list_patient_ids", return_value=["erika", "jan"]):
            scheduler = _create_scheduler()
            jobs = scheduler.get_jobs()
            job_ids = {j.id for j in jobs}

            # 17 agents × 2 patients + 1 keepalive = 35
            assert len(jobs) > 18, f"Expected >18 jobs for 2 patients, got {len(jobs)}"

            # Per-patient job IDs use "agent:patient" format
            assert "pre_cycle_check:erika" in job_ids
            assert "pre_cycle_check:jan" in job_ids

            # Keepalive is system-level, not per-patient
            assert "keepalive_ping" in job_ids

            if scheduler.running:
                scheduler.shutdown(wait=False)
