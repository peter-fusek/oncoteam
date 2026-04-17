"""Autonomous agent loop: Claude API with extended thinking for medical reasoning."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime

from . import clinicaltrials_client, oncofiles_client, pubmed_client
from .activity_logger import log_to_diary, record_suppressed_error
from .breast_protocol import (
    BREAST_DOSE_MODIFICATION_RULES,
    BREAST_LAB_SAFETY_THRESHOLDS,
    BREAST_REGIMENS,
    BREAST_SAFETY_FLAGS,
    BREAST_SECOND_LINE_OPTIONS,
    BREAST_TREATMENT_MILESTONES,
    BREAST_WATCHED_TRIALS,
)
from .clinical_protocol import (
    DOSE_MODIFICATION_RULES,
    LAB_SAFETY_THRESHOLDS,
    MONITORING_SCHEDULE,
    SAFETY_FLAGS,
    SECOND_LINE_OPTIONS,
    TREATMENT_MILESTONES,
    WATCHED_TRIALS,
)
from .config import ANTHROPIC_API_KEY, AUTONOMOUS_COST_LIMIT, AUTONOMOUS_MODEL
from .eligibility import check_eligibility
from .general_health_protocol import GENERAL_HEALTH_SYSTEM_PROMPT
from .models import PatientProfile
from .patient_context import (
    build_biomarker_rules,
    build_patient_profile_text,
    get_patient,
    get_patient_research_terms,
    is_general_health_patient,
)

logger = logging.getLogger("oncoteam.autonomous")

# Cost per million tokens by model
_MODEL_COSTS: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0 / 1_000_000, 15.0 / 1_000_000),
    "claude-haiku-4-5-20251001": (0.80 / 1_000_000, 4.0 / 1_000_000),
}
_DEFAULT_COST = (3.0 / 1_000_000, 15.0 / 1_000_000)  # fallback

# Daily cost accumulator (reset by scheduler at midnight).
# Thread-safe: _track_cost is sync, runs atomically in asyncio's single-threaded loop.
# Per-patient keyed dict; "global" key tracks total across all patients.
_daily_cost: dict[str, float] = {}
_daily_cost_reset_date: str = ""


def _get_client():
    """Lazy import and create AsyncAnthropic client."""
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


def build_system_prompt(patient_id: str = "q1b") -> str:
    """Build a patient-specific system prompt for autonomous agents.

    Oncology patients get the full mFOLFOX6 clinical protocol (ESMO/NCCN).
    General health patients (ICD-10 Z-codes, no treatment regimen) get
    EU/WHO/ESC preventive care protocol instead.
    """
    patient = get_patient(patient_id)
    research_terms = get_patient_research_terms(patient_id)

    if is_general_health_patient(patient):
        return _build_general_health_prompt(patient, patient_id, research_terms)

    if patient.diagnosis_code.upper().startswith("C50"):
        return _build_breast_prompt(patient, patient_id, research_terms)

    return f"""\
You are an autonomous medical research agent for cancer treatment management.
ALL findings are for physician review only. You do NOT communicate with patients.

{build_patient_profile_text(patient)}

{build_biomarker_rules(patient)}

# Clinical Protocol (ESMO 2022, NCCN, ASCO)
## Lab Safety Thresholds
{json.dumps(LAB_SAFETY_THRESHOLDS, indent=2)}

## Dose Modification Rules
{json.dumps(DOSE_MODIFICATION_RULES, indent=2)}

## Treatment Milestones
{json.dumps(TREATMENT_MILESTONES, indent=2)}

## Monitoring Schedule
{json.dumps(MONITORING_SCHEDULE, indent=2)}

## Safety Flags
{json.dumps(SAFETY_FLAGS, indent=2)}

## Second-Line Options (if progression)
{json.dumps(SECOND_LINE_OPTIONS, indent=2)}

## Watched Trials
{json.dumps(WATCHED_TRIALS, indent=2)}

# Research Terms
{json.dumps(research_terms, indent=2)}

{_common_instructions(patient_id, closing="Questions for Oncologist")}
"""


def _build_breast_prompt(
    patient: PatientProfile,
    patient_id: str,
    research_terms: list[str],
) -> str:
    """Build system prompt for breast-cancer patients (C50.*).

    Stub scaffolding — placeholder thresholds pending oncologist review.
    Prevents mFOLFOX6/colorectal assumptions from leaking into breast-patient output.
    """
    return f"""\
You are an autonomous medical research agent for breast cancer management.
ALL findings are for physician review only. You do NOT communicate with patients.

{build_patient_profile_text(patient)}

{build_biomarker_rules(patient)}

# Clinical Protocol — Breast (ESMO 2023, NCCN Breast Cancer)
# NOTE: These thresholds are placeholder scaffolding pending oncologist review.
# Apply breast-specific reasoning — do NOT reference colorectal regimens, CEA/CA 19-9
# trending, or colorectal staging logic in breast-patient output.

## Lab Safety Thresholds (placeholder)
{json.dumps(BREAST_LAB_SAFETY_THRESHOLDS, indent=2)}

## Dose Modification Rules (CDK4/6 focus)
{json.dumps(BREAST_DOSE_MODIFICATION_RULES, indent=2)}

## Treatment Milestones
{json.dumps(BREAST_TREATMENT_MILESTONES, indent=2)}

## Safety Flags
{json.dumps(BREAST_SAFETY_FLAGS, indent=2)}

## Regimen Reference
{json.dumps(BREAST_REGIMENS, indent=2)}

## Second-Line Options (if progression on CDK4/6 + AI)
{json.dumps(BREAST_SECOND_LINE_OPTIONS, indent=2)}

## Watched Trials
{json.dumps(BREAST_WATCHED_TRIALS, indent=2)}

# Research Terms
{json.dumps(research_terms, indent=2)}

# Tumor Markers (breast)
- Primary: CA 15-3 (ESMO ULN ~30 U/mL), CA 27-29 (~38 U/mL), CEA
- NEVER report CA 19-9 as a primary marker for breast cancer

{_common_instructions(patient_id, closing="Questions for Oncologist")}
"""


def _common_instructions(patient_id: str, *, closing: str) -> str:
    """Shared instruction block for all patient types."""
    return f"""\
# Instructions
- Only use data from PubMed (NCBI) and ClinicalTrials.gov.
- If uncertain about a finding, flag as NEEDS_PHYSICIAN_REVIEW.
- Structure output as markdown with clear sections.
- End every analysis with "{closing}" section.
- Patient ID: {patient_id} — all data queries must scope to this patient."""


def _build_general_health_prompt(
    patient: PatientProfile,
    patient_id: str,
    research_terms: list[str],
) -> str:
    """Build system prompt for general health / preventive care patients."""
    return f"""\
You are an autonomous health management agent for general preventive care.
ALL findings are for physician review only. You do NOT communicate with patients.

{build_patient_profile_text(patient)}

{GENERAL_HEALTH_SYSTEM_PROMPT}

# Research Terms
{json.dumps(research_terms, indent=2)}

{_common_instructions(patient_id, closing="Preventive care reminders")}
"""


# Tool definitions for Claude API
TOOLS = [
    {
        "name": "search_pubmed",
        "description": "Search PubMed for medical literature",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "PubMed search query"},
                "max_results": {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_trials",
        "description": "Search ClinicalTrials.gov across SK, CZ, AT, HU",
        "input_schema": {
            "type": "object",
            "properties": {
                "condition": {"type": "string", "description": "Medical condition"},
                "intervention": {"type": "string", "description": "Optional intervention filter"},
                "max_per_country": {
                    "type": "integer",
                    "description": "Max per country (default 5)",
                },
            },
            "required": ["condition"],
        },
    },
    {
        "name": "search_trials_eu",
        "description": (
            "Search ClinicalTrials.gov across EU countries with major CRC trial "
            "activity (SK, CZ, AT, HU, DE, PL, IT, NL, BE, FR, DK, SE, ES, CH)"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "condition": {"type": "string", "description": "Medical condition"},
                "intervention": {"type": "string", "description": "Optional intervention filter"},
                "max_per_country": {
                    "type": "integer",
                    "description": "Max per country (default 3)",
                },
            },
            "required": ["condition"],
        },
    },
    {
        "name": "check_trial_eligibility",
        "description": "Check if a trial is eligible for this patient",
        "input_schema": {
            "type": "object",
            "properties": {
                "nct_id": {"type": "string", "description": "ClinicalTrials.gov NCT ID"},
            },
            "required": ["nct_id"],
        },
    },
    {
        "name": "search_documents",
        "description": "Search medical documents in oncofiles",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Search text"},
                "category": {"type": "string", "description": "Optional category filter"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "get_treatment_timeline",
        "description": "Get treatment events timeline",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max events (default 20)"},
            },
        },
    },
    {
        "name": "store_briefing",
        "description": "Store an autonomous briefing result in oncofiles",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Briefing title"},
                "content": {"type": "string", "description": "Briefing content (markdown)"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization",
                },
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "get_agent_state",
        "description": "Get persistent agent state by key",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "State key"},
            },
            "required": ["key"],
        },
    },
    {
        "name": "set_agent_state",
        "description": "Set persistent agent state",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "State key"},
                "value": {"type": "object", "description": "State value (JSON object)"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "view_document",
        "description": "View full content of a document by ID (OCR text, metadata)",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer", "description": "Document ID"},
            },
            "required": ["document_id"],
        },
    },
    {
        "name": "store_lab_values",
        "description": "Store structured lab values for a specific date (ANC, PLT, WBC, CEA, etc.)",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "integer",
                    "description": "Source document ID (0 if manual entry)",
                },
                "lab_date": {"type": "string", "description": "Lab date (YYYY-MM-DD)"},
                "values": {
                    "type": "object",
                    "description": (
                        'Lab values as {parameter: value} e.g. {"ANC": 3200, "PLT": 180000}'
                    ),
                },
            },
            "required": ["document_id", "lab_date", "values"],
        },
    },
    {
        "name": "add_treatment_event",
        "description": "Add a treatment event (lab_result, toxicity, imaging, etc.)",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_date": {"type": "string", "description": "Event date (YYYY-MM-DD)"},
                "event_type": {
                    "type": "string",
                    "description": (
                        "Event type: lab_result, toxicity, imaging, weight_measurement, etc."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "Event title",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes",
                },
                "metadata": {
                    "type": "object",
                    "description": "Structured data (lab values, grades)",
                },
            },
            "required": ["event_date", "event_type", "title"],
        },
    },
]


async def execute_tool(name: str, inputs: dict, *, patient_id: str = "q1b") -> str:
    """Dispatch tool call to the appropriate async handler.

    All oncofiles calls pass token for patient-scoped data isolation (#201).
    """
    from .request_context import get_token_for_patient

    token = get_token_for_patient(patient_id)

    try:
        if name == "search_pubmed":
            articles = await pubmed_client.search_pubmed(
                inputs["query"], inputs.get("max_results", 5)
            )
            return json.dumps([a.model_dump() for a in articles])

        if name == "search_trials":
            trials = await clinicaltrials_client.search_trials_adjacent(
                condition=inputs["condition"],
                intervention=inputs.get("intervention"),
                max_per_country=inputs.get("max_per_country", 5),
            )
            return json.dumps([t.model_dump() for t in trials])

        if name == "search_trials_eu":
            trials = await clinicaltrials_client.search_trials_eu(
                condition=inputs["condition"],
                intervention=inputs.get("intervention"),
                max_per_country=inputs.get("max_per_country", 3),
            )
            return json.dumps([t.model_dump() for t in trials])

        if name == "check_trial_eligibility":
            trial = await clinicaltrials_client.fetch_trial(inputs["nct_id"])
            if trial is None:
                return json.dumps({"error": f"Trial {inputs['nct_id']} not found"})
            result = check_eligibility(trial, get_patient(patient_id))
            return json.dumps(result.model_dump())

        if name == "search_documents":
            result = await oncofiles_client.search_documents(
                text=inputs["text"], category=inputs.get("category"), token=token
            )
            docs = result.get("documents", []) if isinstance(result, dict) else result
            return json.dumps(docs)

        if name == "get_treatment_timeline":
            result = await oncofiles_client.list_treatment_events(
                limit=inputs.get("limit", 20), token=token
            )
            events = result.get("events", []) if isinstance(result, dict) else result
            return json.dumps(events)

        if name == "store_briefing":
            await log_to_diary(
                title=inputs["title"],
                content=inputs["content"],
                entry_type="autonomous_briefing",
                tags=inputs.get("tags", ["sys:autonomous"]),
                token=token,
            )
            return json.dumps({"stored": True})

        if name == "get_agent_state":
            result = await oncofiles_client.get_agent_state(inputs["key"], token=token)
            return json.dumps(result)

        if name == "set_agent_state":
            result = await oncofiles_client.set_agent_state(
                inputs["key"], inputs["value"], token=token
            )
            return json.dumps(result)

        if name == "view_document":
            result = await oncofiles_client.view_document(str(inputs["document_id"]), token=token)
            return json.dumps(result)

        if name == "store_lab_values":
            result = await oncofiles_client.store_lab_values(
                document_id=inputs["document_id"],
                lab_date=inputs["lab_date"],
                values_json=json.dumps(inputs["values"]),
                token=token,
            )
            return json.dumps(result)

        if name == "add_treatment_event":
            result = await oncofiles_client.add_treatment_event(
                event_date=inputs["event_date"],
                event_type=inputs["event_type"],
                title=inputs["title"],
                notes=inputs.get("notes", ""),
                metadata=inputs.get("metadata"),
                token=token,
            )
            return json.dumps(result)

        return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        record_suppressed_error(f"autonomous.{name}", "execute", e)
        return json.dumps({"error": str(e)})


def _track_cost(
    input_tokens: int, output_tokens: int, model: str = "", patient_id: str = "q1b"
) -> float:
    """Track cost and return the cost for this call."""
    global _daily_cost, _daily_cost_reset_date
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    if _daily_cost_reset_date != today:
        _daily_cost = {}
        _daily_cost_reset_date = today

    cost_in, cost_out = _MODEL_COSTS.get(model, _DEFAULT_COST)
    cost = (input_tokens * cost_in) + (output_tokens * cost_out)
    _daily_cost[patient_id] = _daily_cost.get(patient_id, 0.0) + cost
    _daily_cost["global"] = _daily_cost.get("global", 0.0) + cost
    return cost


def get_daily_cost(patient_id: str | None = None) -> float:
    """Return accumulated cost for today.

    If patient_id is given, return that patient's cost.
    Otherwise return total across all patients.
    """
    if patient_id:
        return _daily_cost.get(patient_id, 0.0)
    return _daily_cost.get("global", 0.0)


def _unwrap_agent_state(state: dict | None) -> dict:
    """Unwrap agent_state, handling nested {"value": ...} format from oncofiles."""
    if not isinstance(state, dict):
        return {}
    # Already flat: {"date": "...", "cost_usd": ...}
    if "value" not in state:
        return state
    # Nested: {"value": '{"date": "...", ...}' or {"date": "...", ...}}
    raw = state.get("value")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    if isinstance(raw, dict):
        return raw
    return {}


async def _persist_daily_cost() -> None:
    """Persist daily cost to oncofiles agent_state for cold-start resilience."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        await oncofiles_client.set_agent_state(
            "autonomous_daily_cost",
            {"date": today, "cost_usd": round(get_daily_cost(), 4)},
        )
    except Exception as e:
        logger.warning("Failed to persist daily cost: %s", e)


async def _persist_mtd_cost(task_cost: float) -> None:
    """Accumulate month-to-date cost in oncofiles agent_state."""
    now = datetime.now(UTC)
    month_key = now.strftime("%Y-%m")
    try:
        raw = await oncofiles_client.get_agent_state("autonomous_mtd_cost")
        state = _unwrap_agent_state(raw)
        prev = float(state.get("cost_usd", 0.0)) if state.get("month") == month_key else 0.0
        await oncofiles_client.set_agent_state(
            "autonomous_mtd_cost",
            {"month": month_key, "cost_usd": round(prev + task_cost, 4)},
        )
    except Exception as e:
        logger.warning("Failed to persist MTD cost: %s", e)


async def _restore_daily_cost() -> None:
    """Restore daily cost from oncofiles on startup / after cold start."""
    global _daily_cost, _daily_cost_reset_date
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        raw = await oncofiles_client.get_agent_state("autonomous_daily_cost")
        state = _unwrap_agent_state(raw)
        if state.get("date") == today:
            restored = float(state.get("cost_usd", 0.0))
            _daily_cost["global"] = restored
            _daily_cost_reset_date = today
            logger.info("Restored daily cost from DB: $%.4f", restored)
    except Exception as e:
        logger.debug("Failed to restore daily cost: %s", e)


async def _notify_cost_cap_reached() -> None:
    """Store a cost alert briefing so dashboard/WhatsApp can surface it."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    total = get_daily_cost()
    try:
        await log_to_diary(
            title=f"Cost cap reached — ${total:.2f} / ${AUTONOMOUS_COST_LIMIT:.2f}",
            content=(
                f"## Autonomous Agent Cost Alert\n\n"
                f"**Date**: {today}\n"
                f"**Daily spend**: ${total:.2f}\n"
                f"**Daily cap**: ${AUTONOMOUS_COST_LIMIT:.2f}\n\n"
                f"All remaining scheduled tasks for today have been **paused**.\n"
                f"Tasks will resume tomorrow at midnight UTC.\n\n"
                f"To increase the cap, set `AUTONOMOUS_COST_LIMIT` env var on Railway."
            ),
            entry_type="cost_alert",
            tags=["sys:cost-alert", f"date:{today}"],
        )
        logger.warning("Cost cap alert stored: $%.2f / $%.2f", total, AUTONOMOUS_COST_LIMIT)
    except Exception as e:
        logger.error("Failed to store cost alert: %s", e)


async def _check_budget_alert(task_cost: float) -> None:
    """Check if remaining Anthropic credit is below threshold and alert."""
    from .config import ANTHROPIC_BUDGET_ALERT_THRESHOLD, ANTHROPIC_CREDIT_BALANCE

    now = datetime.now(UTC)
    month_key = now.strftime("%Y-%m")

    # Get MTD spend
    mtd_spend = 0.0
    try:
        raw = await oncofiles_client.get_agent_state("autonomous_mtd_cost")
        state = _unwrap_agent_state(raw)
        if state.get("month") == month_key:
            mtd_spend = float(state.get("cost_usd", 0.0))
    except Exception:
        return

    remaining = ANTHROPIC_CREDIT_BALANCE - mtd_spend
    if remaining > ANTHROPIC_BUDGET_ALERT_THRESHOLD:
        return

    # Check if we already sent an alert this month
    try:
        raw_alert = await oncofiles_client.get_agent_state("budget_alert_sent")
        alert_state = _unwrap_agent_state(raw_alert)
        if isinstance(alert_state, dict) and alert_state.get("month") == month_key:
            return  # Already alerted this month
    except Exception:
        pass

    # Store budget alert
    days_left = round(remaining / (mtd_spend / now.day), 1) if mtd_spend > 0 and now.day > 0 else 0
    try:
        await log_to_diary(
            title=(f"Budget low — ${remaining:.2f} remaining (~{days_left} days)"),
            content=(
                f"## Anthropic API Budget Alert\n\n"
                f"**Remaining credit**: ${remaining:.2f}\n"
                f"**MTD spend**: ${mtd_spend:.2f}\n"
                f"**Alert threshold**: ${ANTHROPIC_BUDGET_ALERT_THRESHOLD:.2f}\n"
                f"**Estimated days remaining**: {days_left}\n\n"
                f"Please top up Anthropic credits to avoid service interruption.\n"
                f"Current balance: ${ANTHROPIC_CREDIT_BALANCE:.2f}\n"
            ),
            entry_type="cost_alert",
            tags=["sys:cost-alert", "sys:budget-low", f"month:{month_key}"],
        )
        await oncofiles_client.set_agent_state(
            "budget_alert_sent", {"month": month_key, "remaining": remaining}
        )
        logger.warning("Budget low alert stored: $%.2f remaining", remaining)
    except Exception as e:
        logger.error("Failed to store budget alert: %s", e)


def _serialize_messages(messages: list[dict]) -> list[dict]:
    """Convert messages to JSON-serializable format (strip SDK content blocks)."""
    serialized = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, str):
            serialized.append({"role": role, "content": content})
        elif isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(item)
                elif hasattr(item, "type"):
                    # Anthropic SDK content block
                    if item.type == "text":
                        parts.append({"type": "text", "text": item.text})
                    elif item.type == "tool_use":
                        parts.append({"type": "tool_use", "name": item.name, "input": item.input})
                    elif item.type == "tool_result":
                        parts.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": getattr(item, "tool_use_id", ""),
                                "content": str(getattr(item, "content", ""))[:2000],
                            }
                        )
                    elif item.type == "thinking":
                        parts.append({"type": "thinking", "text": item.thinking[:500]})
                else:
                    parts.append(str(item)[:500])
            serialized.append({"role": role, "content": parts})
        else:
            serialized.append({"role": role, "content": str(content)[:2000]})
    return serialized


async def run_autonomous_task(
    task_prompt: str,
    max_turns: int = 15,
    task_name: str = "autonomous",
    model: str | None = None,
    thinking_budget: int | None = None,
    patient_id: str = "q1b",
) -> dict:
    """Run an autonomous agent loop with extended thinking.

    Args:
        model: Override model (default: AUTONOMOUS_MODEL from config).
        thinking_budget: Extended thinking budget. None = auto (10000 for
            Sonnet, disabled for Haiku). Set to 0 to disable thinking.
        patient_id: Patient to run for (default: "q1b").

    Returns dict with thinking, tool_calls, response, token counts, cost.
    """
    # Restore persisted cost on first call (cold start recovery)
    if not _daily_cost_reset_date:
        await _restore_daily_cost()

    if get_daily_cost() >= AUTONOMOUS_COST_LIMIT:
        return {
            "error": (
                f"Daily cost limit ${AUTONOMOUS_COST_LIMIT:.2f} reached (${get_daily_cost():.2f})"
            ),
            "thinking": [],
            "tool_calls": [],
            "response": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "cost": 0.0,
        }

    effective_model = model or AUTONOMOUS_MODEL
    # Auto-detect thinking support: Haiku doesn't support extended thinking
    use_thinking = thinking_budget != 0 and "haiku" not in effective_model
    effective_thinking_budget = thinking_budget if thinking_budget else 10000

    client = _get_client()
    messages: list[dict] = [{"role": "user", "content": task_prompt}]
    result = {
        "thinking": [],
        "tool_calls": [],
        "citations": [],
        "response": "",
        "prompt": task_prompt,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost": 0.0,
        "task_name": task_name,
        "model": effective_model,
        "started_at": datetime.now(UTC).isoformat(),
    }

    start_time = time.monotonic()

    for turn in range(max_turns):
        try:
            create_kwargs: dict = {
                "model": effective_model,
                "max_tokens": 16000 if use_thinking else 8192,
                "system": build_system_prompt(patient_id),
                "tools": TOOLS,
                "messages": messages,
            }
            if use_thinking:
                create_kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": effective_thinking_budget,
                }
            response = await client.messages.create(**create_kwargs)
        except Exception as e:
            logger.error("Claude API error on turn %d: %s", turn, e)
            result["error"] = str(e)
            break

        result["input_tokens"] += response.usage.input_tokens
        result["output_tokens"] += response.usage.output_tokens
        call_cost = _track_cost(
            response.usage.input_tokens, response.usage.output_tokens, effective_model, patient_id
        )
        result["cost"] += call_cost

        # Extract content and citations
        for block in response.content:
            if block.type == "thinking":
                result["thinking"].append(block.thinking)
            elif block.type == "text":
                result["response"] += block.text
                # Collect citations from text blocks
                if hasattr(block, "citations") and block.citations:
                    for cite in block.citations:
                        result["citations"].append(
                            {
                                "text": block.text,
                                "cited_text": getattr(cite, "cited_text", ""),
                                "source": getattr(cite, "document_title", ""),
                            }
                        )

        if response.stop_reason != "tool_use":
            break

        # Execute tools, preserve thinking blocks in assistant message
        messages.append({"role": "assistant", "content": response.content})
        tool_results: list[dict] = []
        for block in response.content:
            if block.type == "tool_use":
                logger.info(
                    "Tool call: %s(%s)",
                    block.name,
                    json.dumps(block.input)[:200],
                )
                tool_output = await execute_tool(block.name, block.input, patient_id=patient_id)
                result["tool_calls"].append(
                    {"tool": block.name, "input": block.input, "output": tool_output}
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_output,
                    }
                )
        messages.append({"role": "user", "content": tool_results})

        # Check cost limit mid-run
        if get_daily_cost() >= AUTONOMOUS_COST_LIMIT:
            logger.warning("Daily cost limit reached mid-task: $%.2f", get_daily_cost())
            result["response"] += "\n\n[COST LIMIT REACHED — task stopped]"
            await _persist_daily_cost()
            await _notify_cost_cap_reached()
            break

    result["duration_ms"] = int((time.monotonic() - start_time) * 1000)
    result["completed_at"] = datetime.now(UTC).isoformat()
    # Turn count excludes the initial user prompt
    result["turns"] = len([m for m in messages if m["role"] == "user"]) - 1
    # Store serializable message history (strip non-JSON content blocks)
    result["messages"] = _serialize_messages(messages)

    # Persist cost after every task completion
    await _persist_daily_cost()
    await _persist_mtd_cost(result["cost"])
    await _check_budget_alert(result["cost"])

    logger.info(
        "Task %s completed: %d tool calls, %d input tokens, %d output tokens, $%.4f",
        task_name,
        len(result["tool_calls"]),
        result["input_tokens"],
        result["output_tokens"],
        result["cost"],
    )

    return result
