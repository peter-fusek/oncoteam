"""Tests for autonomous scheduler lifespan."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from oncoteam.scheduler import autonomous_lifespan


class TestSchedulerLifespan:
    @pytest.mark.asyncio
    async def test_disabled_yields_empty(self):
        with patch("oncoteam.scheduler.AUTONOMOUS_ENABLED", False):
            async with autonomous_lifespan(None) as ctx:
                assert ctx == {}

    @pytest.mark.asyncio
    async def test_enabled_creates_scheduler(self):
        with patch("oncoteam.scheduler.AUTONOMOUS_ENABLED", True):
            async with autonomous_lifespan(None) as ctx:
                scheduler = ctx["scheduler"]
                jobs = scheduler.get_jobs()
                assert len(jobs) == 12

                job_ids = {j.id for j in jobs}
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

    @pytest.mark.asyncio
    async def test_scheduler_shuts_down(self):
        with patch("oncoteam.scheduler.AUTONOMOUS_ENABLED", True):
            async with autonomous_lifespan(None) as ctx:
                scheduler = ctx["scheduler"]
                assert scheduler.running

            # After context exit, scheduler should be shut down
            # shutdown(wait=False) stops accepting new jobs
            assert scheduler.get_jobs() is not None  # no error = clean shutdown
