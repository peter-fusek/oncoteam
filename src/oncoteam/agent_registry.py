"""Agent registry: single source of truth for all autonomous task configurations.

Replaces hardcoded task definitions scattered across scheduler.py,
dashboard_api.py, and autonomous_tasks.py. Each agent is a data object
with schedule, model, cooldown, prompt, and display metadata.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .locale import BiStr, L


class ScheduleType(StrEnum):
    INTERVAL = "interval"
    CRON = "cron"


class AgentCategory(StrEnum):
    DATA_PIPELINE = "data_pipeline"
    RESEARCH = "research"
    CLINICAL = "clinical"
    REPORTING = "reporting"
    SYSTEM = "system"


class AgentConfig(BaseModel):
    """Configuration for a single autonomous agent/task."""

    id: str
    name: BiStr
    description: BiStr
    schedule_display: BiStr
    category: AgentCategory
    model: str | None = None  # None = Sonnet, "light" = Haiku
    schedule_type: ScheduleType
    schedule_params: dict = Field(default_factory=dict)
    misfire_grace_time: int = 86400
    cooldown_hours: float = 0.0
    max_turns: int = 8
    whatsapp_enabled: bool = False
    assigned_tool: str = ""
    enabled: bool = True


# ── Agent Definitions ──────────────────────────

_AGENTS: list[AgentConfig] = [
    # === System ===
    AgentConfig(
        id="keepalive_ping",
        name=L("Keep-alive ping", "Keep-alive ping"),
        description=L(
            "Ping oncofiles pre zabránenie cold startu", "Ping oncofiles to prevent cold start"
        ),
        schedule_display=L("každých 5 minút", "every 5 minutes"),
        category=AgentCategory.SYSTEM,
        schedule_type=ScheduleType.INTERVAL,
        schedule_params={"minutes": 5},
        misfire_grace_time=600,
        max_turns=0,
    ),
    AgentConfig(
        id="daily_cost_report",
        name=L("Denný prehľad nákladov", "Daily cost report"),
        description=L(
            "Ranný klinický súhrn + náklady cez WhatsApp",
            "Morning clinical summary + cost via WhatsApp",
        ),
        schedule_display=L("denne 06:30 UTC", "daily 06:30 UTC"),
        category=AgentCategory.SYSTEM,
        schedule_type=ScheduleType.CRON,
        schedule_params={"hour": 6, "minute": 30},
        whatsapp_enabled=True,
        assigned_tool="analyze_labs",
        max_turns=0,
    ),
    # === Data Pipeline (Haiku) ===
    AgentConfig(
        id="file_scan",
        name=L("Skenovanie dokumentov", "Document scan"),
        description=L(
            "Skenovanie nových dokumentov v oncofiles", "Scan for new documents in oncofiles"
        ),
        schedule_display=L("každé 4 hodiny", "every 4 hours"),
        category=AgentCategory.DATA_PIPELINE,
        model="light",
        schedule_type=ScheduleType.INTERVAL,
        schedule_params={"hours": 4},
        misfire_grace_time=14400,
        cooldown_hours=1.5,
        assigned_tool="search_documents",
    ),
    AgentConfig(
        id="lab_sync",
        name=L("Synchronizácia labov", "Lab sync"),
        description=L("Extrakcia lab. hodnôt z dokumentov", "Extract lab values from documents"),
        schedule_display=L("každých 12 hodín", "every 12 hours"),
        category=AgentCategory.DATA_PIPELINE,
        model="light",
        schedule_type=ScheduleType.INTERVAL,
        schedule_params={"hours": 12},
        misfire_grace_time=43200,
        cooldown_hours=5.0,
        whatsapp_enabled=True,
        assigned_tool="analyze_labs",
    ),
    AgentConfig(
        id="toxicity_extraction",
        name=L("Extrakcia toxicity", "Toxicity extraction"),
        description=L(
            "Extrakcia NCI-CTCAE stupňov z dokumentov", "Extract NCI-CTCAE grades from documents"
        ),
        schedule_display=L("každé 2 dni 08:00 UTC", "every 2 days 08:00 UTC"),
        category=AgentCategory.DATA_PIPELINE,
        model="light",
        schedule_type=ScheduleType.CRON,
        schedule_params={"hour": 8, "minute": 0, "day": "*/2"},
        cooldown_hours=20.0,
        assigned_tool="search_documents",
    ),
    AgentConfig(
        id="weight_extraction",
        name=L("Extrakcia hmotnosti", "Weight extraction"),
        description=L("Extrakcia hmotnosti/BMI z dokumentov", "Extract weight/BMI from documents"),
        schedule_display=L("každé 3 dni 09:00 UTC", "every 3 days 09:00 UTC"),
        category=AgentCategory.DATA_PIPELINE,
        model="light",
        schedule_type=ScheduleType.CRON,
        schedule_params={"hour": 9, "minute": 0, "day": "*/3"},
        cooldown_hours=20.0,
        assigned_tool="search_documents",
    ),
    # === Research (Sonnet) ===
    AgentConfig(
        id="daily_research",
        name=L("Prehľad výskumu PubMed", "PubMed research scan"),
        description=L("Prehľad výskumu PubMed", "PubMed research scan"),
        schedule_display=L("každé 2 dni 07:00 UTC", "every 2 days 07:00 UTC"),
        category=AgentCategory.RESEARCH,
        schedule_type=ScheduleType.CRON,
        schedule_params={"hour": 7, "minute": 0, "day": "*/2"},
        cooldown_hours=20.0,
        max_turns=12,
        assigned_tool="search_pubmed",
    ),
    AgentConfig(
        id="trial_monitor",
        name=L("Monitorovanie klinických štúdií", "Clinical trial monitor"),
        description=L("Monitorovanie klinických štúdií v EÚ", "Monitor clinical trials across EU"),
        schedule_display=L("každých 6 hodín", "every 6 hours"),
        category=AgentCategory.RESEARCH,
        schedule_type=ScheduleType.INTERVAL,
        schedule_params={"hours": 6},
        misfire_grace_time=21600,
        cooldown_hours=5.0,
        max_turns=12,
        whatsapp_enabled=True,
        assigned_tool="search_clinical_trials",
    ),
    # === Clinical (Sonnet) ===
    AgentConfig(
        id="pre_cycle_check",
        name=L("Kontrola bezpečnosti pred cyklom", "Pre-cycle safety check"),
        description=L("Kontrola bezpečnosti pred cyklom FOLFOX", "Pre-cycle FOLFOX safety check"),
        schedule_display=L("každých 13 dní", "every 13 days"),
        category=AgentCategory.CLINICAL,
        schedule_type=ScheduleType.INTERVAL,
        schedule_params={"days": 13},
        misfire_grace_time=86400 * 2,
        cooldown_hours=288.0,
        max_turns=10,
        whatsapp_enabled=True,
        assigned_tool="pre_cycle_check",
    ),
    AgentConfig(
        id="tumor_marker_review",
        name=L("Analýza trendu CEA/CA 19-9", "CEA/CA 19-9 trend analysis"),
        description=L("Analýza trendu CEA/CA 19-9", "CEA/CA 19-9 trend analysis"),
        schedule_display=L("každé 4 týždne", "every 4 weeks"),
        category=AgentCategory.CLINICAL,
        schedule_type=ScheduleType.INTERVAL,
        schedule_params={"weeks": 4},
        misfire_grace_time=86400 * 7,
        cooldown_hours=600.0,
        assigned_tool="get_lab_trends",
    ),
    AgentConfig(
        id="response_assessment",
        name=L("Hodnotenie odpovede RECIST", "RECIST response assessment"),
        description=L("Hodnotenie odpovede RECIST", "RECIST response assessment"),
        schedule_display=L("každých 8 týždňov", "every 8 weeks"),
        category=AgentCategory.CLINICAL,
        schedule_type=ScheduleType.INTERVAL,
        schedule_params={"weeks": 8},
        misfire_grace_time=86400 * 14,
        cooldown_hours=1200.0,
        assigned_tool="search_documents",
    ),
    # === Reporting (Sonnet) ===
    AgentConfig(
        id="weekly_briefing",
        name=L("Týždenný briefing pre lekára", "Weekly physician briefing"),
        description=L("Týždenný briefing pre lekára", "Weekly physician briefing"),
        schedule_display=L("pondelok 06:00 UTC", "Monday 06:00 UTC"),
        category=AgentCategory.REPORTING,
        schedule_type=ScheduleType.CRON,
        schedule_params={"day_of_week": "mon", "hour": 6},
        misfire_grace_time=86400 * 2,
        cooldown_hours=144.0,
        max_turns=12,
        whatsapp_enabled=True,
        assigned_tool="daily_briefing",
    ),
    AgentConfig(
        id="mtb_preparation",
        name=L("Príprava na tumor board", "Tumor board preparation"),
        description=L("Príprava na tumor board", "Tumor board preparation"),
        schedule_display=L("piatok 14:00 UTC", "Friday 14:00 UTC"),
        category=AgentCategory.REPORTING,
        schedule_type=ScheduleType.CRON,
        schedule_params={"day_of_week": "fri", "hour": 14},
        misfire_grace_time=86400 * 2,
        cooldown_hours=144.0,
        max_turns=10,
        assigned_tool="review_session",
    ),
    AgentConfig(
        id="family_update",
        name=L("Týždenná správa pre rodinu", "Weekly family update"),
        description=L("Týždenná správa pre rodinu v slovenčine", "Weekly family update in Slovak"),
        schedule_display=L("nedeľa 18:00 UTC", "Sunday 18:00 UTC"),
        category=AgentCategory.REPORTING,
        schedule_type=ScheduleType.CRON,
        schedule_params={"day_of_week": "sun", "hour": 18},
        misfire_grace_time=86400 * 2,
        cooldown_hours=144.0,
        max_turns=10,
        whatsapp_enabled=True,
        assigned_tool="daily_briefing",
    ),
    AgentConfig(
        id="medication_adherence_check",
        name=L("Kontrola adherencie liekov", "Medication adherence check"),
        description=L(
            "Kontrola adherencie liekov (Clexane)", "Medication adherence check (Clexane)"
        ),
        schedule_display=L("denne 20:00 UTC", "daily 20:00 UTC"),
        category=AgentCategory.REPORTING,
        schedule_type=ScheduleType.CRON,
        schedule_params={"hour": 20, "minute": 0},
        cooldown_hours=20.0,
        max_turns=6,
        whatsapp_enabled=True,
        assigned_tool="search_documents",
    ),
]

# ── Registry ───────────────────────────────────

AGENT_REGISTRY: dict[str, AgentConfig] = {a.id: a for a in _AGENTS}


def get_agent(agent_id: str) -> AgentConfig:
    """Get agent config by ID. Raises KeyError if not found."""
    return AGENT_REGISTRY[agent_id]


def get_enabled_agents(*, exclude_system: bool = False) -> list[AgentConfig]:
    """Return enabled agents, sorted by category then ID."""
    return sorted(
        (
            a
            for a in AGENT_REGISTRY.values()
            if a.enabled and (not exclude_system or a.category != AgentCategory.SYSTEM)
        ),
        key=lambda a: (a.category, a.id),
    )


def get_cooldown(agent_id: str) -> float:
    """Get cooldown hours for an agent. Returns 0 if not found."""
    agent = AGENT_REGISTRY.get(agent_id)
    return agent.cooldown_hours if agent else 0.0


def get_dashboard_jobs(lang: str = "sk") -> list[dict]:
    """Generate job list for /api/autonomous endpoint."""
    from .locale import resolve

    jobs = []
    for agent in get_enabled_agents(exclude_system=True):
        jobs.append(
            resolve(
                {
                    "id": agent.id,
                    "assigned_tool": agent.assigned_tool,
                    "schedule": agent.schedule_display,
                    "description": agent.description,
                },
                lang,
            )
        )
    return jobs
