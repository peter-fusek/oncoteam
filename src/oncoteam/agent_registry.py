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
    prompt_template: str = ""


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
        prompt_template="[No prompt — direct HTTP ping, no Claude API call]",
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
        prompt_template="[No prompt — direct data aggregation, no Claude API call]",
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
        prompt_template="""\
Scan for new document uploads since last check ({last_scan}).

Instructions:
1. Search documents for recent pathology, genetics, and lab reports
2. For pathology/genetics docs: check if biomarker data matches known profile
3. For lab docs: check values against safety thresholds
4. Flag any discrepancies or new information
5. If new biomarker data found, note for physician review

Search categories: "pathology", "genetics", "labs", "imaging"\
""",
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
        prompt_template="""\
Extract structured lab data from uploaded documents and store as lab values.

Instructions:
1. Search documents for lab results (search "lab", "krvny obraz", "biochemia", "odber")
2. For each document found, use view_document to read its full content
3. Extract numeric lab values: WBC, ANC, PLT, hemoglobin, creatinine,
   ALT, AST, bilirubin, CEA, CA_19_9, ABS_LYMPH
4. Use get_treatment_timeline to check if data already exists for that date
5. For NEW data only, use store_lab_values with the document_id, lab_date, and extracted values
6. Also create a lab_result treatment event via add_treatment_event with the values in metadata
7. Store a briefing summarizing what was extracted and stored

IMPORTANT: Use store_lab_values for structured persistence (enables trends/charts).
Use add_treatment_event for timeline visibility.
Parameter names must match exactly: WBC, ANC, PLT, hemoglobin,
creatinine, ALT, AST, bilirubin, CEA, CA_19_9, ABS_LYMPH.\
""",
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
        prompt_template="""\
Search for doctor visit notes and extract NCI-CTCAE toxicity assessments.

Instructions:
1. Search documents for visit reports, discharge summaries, consultation notes
   (search "konzultacia", "vizita", "prepustenie", "kontrola")
2. For each document with toxicity data, extract grades for:
   - Peripheral neuropathy, diarrhea, mucositis, fatigue, HFS, nausea/vomiting
3. Note ECOG and weight if mentioned
4. Store a briefing summarizing extracted toxicity data with dates

This creates the baseline toxicity history from existing medical documents.\
""",
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
        prompt_template="""\
Search for doctor visit notes and extract weight/BMI data.

Instructions:
1. Search documents for visit reports, consultation notes, discharge summaries
   (search "hmotnost", "vaha", "BMI", "hmotnost", "vizita", "kontrola")
2. For each document with weight data, extract:
   - Weight in kg
   - BMI if mentioned
   - Date of measurement
3. Check if a weight_measurement event already exists for that date
4. If not, store as a treatment event with event_type="weight_measurement"
5. Store a briefing summarizing what was extracted

Focus on creating structured weight history from existing medical documents.\
""",
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
        prompt_template=(
            "[Dynamic -- built at runtime from curated research terms "
            "(RESEARCH_TERMS list with {terms} injected)]"
        ),
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
        prompt_template=(
            "[Dynamic -- built at runtime from watched trials list, "
            "previously seen NCT IDs, and EU center list]"
        ),
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
        prompt_template=(
            "[Dynamic -- built at runtime from current cycle number, "
            "milestones, and formatted pre-cycle checklist]"
        ),
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
        prompt_template="""\
Review tumor marker trends (CEA, CA 19-9).

Instructions:
1. Search oncofiles for tumor marker data (search "CEA", "CA 19-9", "tumor marker")
2. Search oncofiles for lab results that may contain marker values
3. Analyze trend: rising/falling/stable
4. Compare to expected response on mFOLFOX6
5. If markers rising: flag possible progression, recommend imaging
6. Store findings as a briefing

Reference ESMO guidelines for marker interpretation in mCRC monitoring.\
""",
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
        prompt_template=(
            "[Dynamic -- built at runtime from current cycle number "
            "for RECIST 1.1 response evaluation timing]"
        ),
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
        prompt_template=(
            "[Dynamic -- built at runtime from current cycle number and treatment milestones]"
        ),
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
        prompt_template="""\
Prepare a multidisciplinary tumor board (MTB) summary.

Instructions:
1. Get the full treatment timeline
2. Search for recent lab results and imaging findings
3. Compile the molecular profile summary
4. List discussion points: dose modifications, trial eligibility, 2L planning
5. Include recent research findings relevant to the case
6. Store the MTB summary as a briefing

Structure for MDT presentation:
- Patient Summary (one paragraph)
- Molecular Profile
- Treatment History & Response
- Current Status & Toxicities
- Discussion Points
- Trial Eligibility Summary
- Recommendations\
""",
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
        prompt_template=(
            "[Dynamic -- built at runtime from current cycle number, "
            "injected into Slovak-language family update template]"
        ),
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
        prompt_template="""\
Check medication adherence for today ({today}).

Instructions:
1. Use get_treatment_timeline to find today's medication_adherence events
2. If no adherence logged for today, create a reminder briefing
3. Specifically flag if Clexane (anticoagulant) adherence is missing -- critical for VTE
4. Store a briefing noting adherence status

This is a safety check: Clexane non-compliance with active VJI thrombosis is dangerous.\
""",
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
