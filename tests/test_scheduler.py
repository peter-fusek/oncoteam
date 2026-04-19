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
            # Sprint 92: e5g and sgu paused. Registry has 22 agents but
            # document_pipeline and dose_extraction are event-driven only
            # (no scheduler function registered → skipped). Remaining 20
            # agents − 2 system (keepalive_ping, health_monitor) = 18
            # per-patient × 1 patient (q1b) + 2 system = 20 jobs.
            assert len(jobs) == 20

            job_ids = {j.id for j in jobs}
            # System-level agents are not per-patient.
            assert "keepalive_ping" in job_ids
            assert "health_monitor" in job_ids
            # q1b is active; all per-patient agents scheduled (agent:patient format).
            assert "pre_cycle_check:q1b" in job_ids
            assert "daily_research:q1b" in job_ids
            assert "trial_monitor:q1b" in job_ids
            assert "weekly_briefing:q1b" in job_ids
            assert "lab_sync:q1b" in job_ids
            assert "document_pipeline_drain:q1b" in job_ids
            # Paused patients contribute zero jobs.
            assert not any(jid.endswith(":e5g") for jid in job_ids)
            assert not any(jid.endswith(":sgu") for jid in job_ids)

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
        from oncoteam.models import PatientProfile
        from oncoteam.scheduler import _create_scheduler

        jan = PatientProfile(
            name="Jan N.",
            diagnosis_code="C18.0",
            diagnosis_description="mCRC",
            tumor_site="colon",
            treatment_regimen="FOLFOX",
            agent_whitelist=[],  # empty = all agents
        )

        def _mock_get(pid):
            from oncoteam.patient_context import PATIENT

            return PATIENT if pid == "q1b" else jan

        with (
            patch("oncoteam.scheduler.list_patient_ids", return_value=["q1b", "jan"]),
            patch("oncoteam.scheduler.get_patient", side_effect=_mock_get),
        ):
            scheduler = _create_scheduler()
            jobs = scheduler.get_jobs()
            job_ids = {j.id for j in jobs}

            # Both patients get all agents (jan has empty whitelist = all)
            # 17 agents × 2 patients + 1 keepalive = 35
            assert len(jobs) > 18, f"Expected >18 jobs for 2 patients, got {len(jobs)}"

            # Per-patient job IDs use "agent:patient" format
            assert "pre_cycle_check:q1b" in job_ids
            assert "pre_cycle_check:jan" in job_ids

            # Keepalive is system-level, not per-patient
            assert "keepalive_ping" in job_ids

            if scheduler.running:
                scheduler.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_agent_whitelist_filtering(self):
        """Patients with agent_whitelist only get whitelisted agents."""
        from oncoteam.models import PatientProfile
        from oncoteam.scheduler import _create_scheduler

        limited = PatientProfile(
            name="Limited P.",
            diagnosis_code="Z00.0",
            diagnosis_description="General health",
            tumor_site="",
            treatment_regimen="",
            agent_whitelist=["lab_sync", "weekly_briefing"],
        )

        def _mock_get(pid):
            from oncoteam.patient_context import PATIENT

            return PATIENT if pid == "q1b" else limited

        with (
            patch("oncoteam.scheduler.list_patient_ids", return_value=["q1b", "limited"]),
            patch("oncoteam.scheduler.get_patient", side_effect=_mock_get),
        ):
            scheduler = _create_scheduler()
            jobs = scheduler.get_jobs()
            job_ids = {j.id for j in jobs}

            # Erika gets all agents, limited gets only 2
            assert "pre_cycle_check:q1b" in job_ids
            assert "lab_sync:limited" in job_ids
            assert "weekly_briefing:limited" in job_ids
            assert "pre_cycle_check:limited" not in job_ids
            assert "trial_monitor:limited" not in job_ids

            if scheduler.running:
                scheduler.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_paused_patient_skipped(self):
        """Paused patients produce zero per-patient jobs (Sprint 92)."""
        from oncoteam.models import PatientProfile
        from oncoteam.scheduler import _create_scheduler

        paused_patient = PatientProfile(
            name="Paused P.",
            diagnosis_code="C18.7",
            diagnosis_description="mCRC (paused)",
            tumor_site="colon",
            treatment_regimen="FOLFOX",
            paused=True,  # non-destructive pause
        )

        def _mock_get(pid):
            from oncoteam.patient_context import PATIENT

            return PATIENT if pid == "q1b" else paused_patient

        with (
            patch("oncoteam.scheduler.list_patient_ids", return_value=["q1b", "paused"]),
            patch("oncoteam.scheduler.get_patient", side_effect=_mock_get),
        ):
            scheduler = _create_scheduler()
            job_ids = {j.id for j in scheduler.get_jobs()}

            # Paused patient contributes zero per-patient jobs.
            assert not any(jid.endswith(":paused") for jid in job_ids)
            # Active patient still gets full coverage.
            assert "pre_cycle_check:q1b" in job_ids
            assert "lab_sync:q1b" in job_ids
            assert "document_pipeline_drain:q1b" in job_ids

            if scheduler.running:
                scheduler.shutdown(wait=False)
