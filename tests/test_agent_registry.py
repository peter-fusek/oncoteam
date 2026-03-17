"""Tests for agent_registry — single source of truth for all autonomous agents."""

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from oncoteam.agent_registry import (
    AGENT_REGISTRY,
    AgentCategory,
    ScheduleType,
    get_agent,
    get_cooldown,
    get_dashboard_jobs,
    get_enabled_agents,
)


class TestAgentRegistry:
    def test_all_agents_loaded(self):
        assert len(AGENT_REGISTRY) == 17

    def test_no_duplicate_ids(self):
        ids = list(AGENT_REGISTRY.keys())
        assert len(ids) == len(set(ids))

    def test_all_agents_have_required_fields(self):
        for agent in AGENT_REGISTRY.values():
            assert agent.id
            assert agent.name.get("sk")
            assert agent.name.get("en")
            assert agent.description.get("sk")
            assert agent.description.get("en")
            assert agent.schedule_display.get("sk")
            assert agent.schedule_display.get("en")

    def test_schedule_params_valid_for_interval(self):
        for agent in AGENT_REGISTRY.values():
            if agent.schedule_type == ScheduleType.INTERVAL:
                trigger = IntervalTrigger(**agent.schedule_params)
                assert trigger is not None

    def test_schedule_params_valid_for_cron(self):
        for agent in AGENT_REGISTRY.values():
            if agent.schedule_type == ScheduleType.CRON:
                trigger = CronTrigger(**agent.schedule_params)
                assert trigger is not None

    def test_categories_assigned(self):
        categories = {a.category for a in AGENT_REGISTRY.values()}
        assert AgentCategory.SYSTEM in categories
        assert AgentCategory.DATA_PIPELINE in categories
        assert AgentCategory.RESEARCH in categories
        assert AgentCategory.CLINICAL in categories
        assert AgentCategory.REPORTING in categories

    def test_haiku_agents_have_light_model(self):
        light_agents = {
            "file_scan",
            "lab_sync",
            "toxicity_extraction",
            "weight_extraction",
            "protocol_review",
            "self_improvement",
        }
        for agent_id in light_agents:
            assert AGENT_REGISTRY[agent_id].model == "light"

    def test_sonnet_agents_have_no_model_override(self):
        sonnet_agents = {"pre_cycle_check", "trial_monitor", "daily_research", "weekly_briefing"}
        for agent_id in sonnet_agents:
            assert AGENT_REGISTRY[agent_id].model is None


class TestGetAgent:
    def test_get_existing(self):
        agent = get_agent("file_scan")
        assert agent.id == "file_scan"

    def test_get_nonexistent_raises(self):
        with pytest.raises(KeyError):
            get_agent("nonexistent")


class TestGetCooldown:
    def test_known_agent(self):
        assert get_cooldown("file_scan") == 1.5
        assert get_cooldown("pre_cycle_check") == 288.0

    def test_unknown_agent(self):
        assert get_cooldown("nonexistent") == 0.0

    def test_system_agents_no_cooldown(self):
        assert get_cooldown("keepalive_ping") == 0.0
        assert get_cooldown("daily_cost_report") == 0.0


class TestGetEnabledAgents:
    def test_returns_all_enabled(self):
        agents = get_enabled_agents()
        assert len(agents) == 17

    def test_exclude_system(self):
        agents = get_enabled_agents(exclude_system=True)
        for a in agents:
            assert a.category != AgentCategory.SYSTEM
        assert len(agents) == 14


class TestGetDashboardJobs:
    def test_returns_jobs(self):
        jobs = get_dashboard_jobs("en")
        assert len(jobs) == 14  # excludes system agents

    def test_jobs_have_required_fields(self):
        for job in get_dashboard_jobs("en"):
            assert "id" in job
            assert "description" in job
            assert "schedule" in job

    def test_bilingual(self):
        sk_jobs = get_dashboard_jobs("sk")
        en_jobs = get_dashboard_jobs("en")
        assert sk_jobs[0]["description"] != en_jobs[0]["description"]
