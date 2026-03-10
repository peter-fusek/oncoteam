"""Autonomous agent loop: Claude API with extended thinking for medical reasoning."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime

from . import clinicaltrials_client, oncofiles_client, pubmed_client
from .activity_logger import log_to_diary, record_suppressed_error
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
from .patient_context import PATIENT, RESEARCH_TERMS, get_patient_profile_text

logger = logging.getLogger("oncoteam.autonomous")

# Cost per million tokens (Sonnet 4.6 defaults)
_COST_INPUT = 3.0 / 1_000_000
_COST_OUTPUT = 15.0 / 1_000_000

# Daily cost accumulator (reset by scheduler at midnight)
_daily_cost: float = 0.0
_daily_cost_reset_date: str = ""


def _get_client():
    """Lazy import and create AsyncAnthropic client."""
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


AUTONOMOUS_SYSTEM_PROMPT = f"""\
You are an autonomous medical research agent for cancer treatment management.
ALL findings are for physician review only. You do NOT communicate with patients.

# Patient Profile
{get_patient_profile_text()}

# Biomarker Rules (NEVER violate)
- Patient has KRAS G12S (c.34G>A). This is NOT G12C.
- anti-EGFR (cetuximab, panitumumab) is PERMANENTLY CONTRAINDICATED (any RAS mutation).
- KRAS G12C-specific inhibitors (sotorasib, adagrasib) do NOT apply to G12S.
- Patient is pMMR/MSS — checkpoint inhibitor MONOTHERAPY not indicated.
- HER2 negative — HER2-targeted therapy not indicated.
- BRAF V600E wild-type — BRAF inhibitors alone not indicated.
- Active VJI thrombosis + Clexane — bevacizumab is HIGH RISK.

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
{json.dumps(RESEARCH_TERMS, indent=2)}

# Instructions
- Only use data from PubMed (NCBI) and ClinicalTrials.gov. Never reference unverified sources.
- If uncertain about a biomarker match or eligibility, flag as NEEDS_PHYSICIAN_REVIEW.
- Always reference ESMO/NCCN guideline version when making treatment-related statements.
- Structure output as markdown with clear sections.
- End every briefing with "Questions for Oncologist" section.
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
]


async def execute_tool(name: str, inputs: dict) -> str:
    """Dispatch tool call to the appropriate async handler."""
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

        if name == "check_trial_eligibility":
            trial = await clinicaltrials_client.fetch_trial(inputs["nct_id"])
            if trial is None:
                return json.dumps({"error": f"Trial {inputs['nct_id']} not found"})
            result = check_eligibility(trial, PATIENT)
            return json.dumps(result.model_dump())

        if name == "search_documents":
            result = await oncofiles_client.search_documents(
                text=inputs["text"], category=inputs.get("category")
            )
            docs = result.get("documents", []) if isinstance(result, dict) else result
            return json.dumps(docs)

        if name == "get_treatment_timeline":
            result = await oncofiles_client.list_treatment_events(limit=inputs.get("limit", 20))
            events = result.get("events", []) if isinstance(result, dict) else result
            return json.dumps(events)

        if name == "store_briefing":
            await log_to_diary(
                title=inputs["title"],
                content=inputs["content"],
                entry_type="autonomous_briefing",
                tags=inputs.get("tags", ["autonomous"]),
            )
            return json.dumps({"stored": True})

        if name == "get_agent_state":
            result = await oncofiles_client.get_agent_state(inputs["key"])
            return json.dumps(result)

        if name == "set_agent_state":
            result = await oncofiles_client.set_agent_state(inputs["key"], inputs["value"])
            return json.dumps(result)

        return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        record_suppressed_error(f"autonomous.{name}", "execute", e)
        return json.dumps({"error": str(e)})


def _track_cost(input_tokens: int, output_tokens: int) -> float:
    """Track cost and return the cost for this call."""
    global _daily_cost, _daily_cost_reset_date
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    if _daily_cost_reset_date != today:
        _daily_cost = 0.0
        _daily_cost_reset_date = today

    cost = (input_tokens * _COST_INPUT) + (output_tokens * _COST_OUTPUT)
    _daily_cost += cost
    return cost


def get_daily_cost() -> float:
    """Return accumulated cost for today."""
    return _daily_cost


async def _persist_daily_cost() -> None:
    """Persist daily cost to oncofiles agent_state for cold-start resilience."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        await oncofiles_client.set_agent_state(
            "autonomous_daily_cost",
            {"date": today, "cost_usd": round(_daily_cost, 4)},
        )
    except Exception as e:
        logger.debug("Failed to persist daily cost: %s", e)


async def _restore_daily_cost() -> None:
    """Restore daily cost from oncofiles on startup / after cold start."""
    global _daily_cost, _daily_cost_reset_date
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        state = await oncofiles_client.get_agent_state("autonomous_daily_cost")
        if isinstance(state, dict) and state.get("date") == today:
            _daily_cost = float(state.get("cost_usd", 0.0))
            _daily_cost_reset_date = today
            logger.info("Restored daily cost from DB: $%.4f", _daily_cost)
    except Exception as e:
        logger.debug("Failed to restore daily cost: %s", e)


async def _notify_cost_cap_reached() -> None:
    """Store a cost alert briefing so dashboard/WhatsApp can surface it."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        await log_to_diary(
            title=f"Cost cap reached — ${_daily_cost:.2f} / ${AUTONOMOUS_COST_LIMIT:.2f}",
            content=(
                f"## Autonomous Agent Cost Alert\n\n"
                f"**Date**: {today}\n"
                f"**Daily spend**: ${_daily_cost:.2f}\n"
                f"**Daily cap**: ${AUTONOMOUS_COST_LIMIT:.2f}\n\n"
                f"All remaining scheduled tasks for today have been **paused**.\n"
                f"Tasks will resume tomorrow at midnight UTC.\n\n"
                f"To increase the cap, set `AUTONOMOUS_COST_LIMIT` env var on Railway."
            ),
            entry_type="cost_alert",
            tags=["cost_alert", f"date:{today}"],
        )
        logger.warning("Cost cap alert stored: $%.2f / $%.2f", _daily_cost, AUTONOMOUS_COST_LIMIT)
    except Exception as e:
        logger.error("Failed to store cost alert: %s", e)


async def run_autonomous_task(
    task_prompt: str,
    max_turns: int = 15,
    task_name: str = "autonomous",
) -> dict:
    """Run an autonomous agent loop with extended thinking.

    Returns dict with thinking, tool_calls, response, token counts, cost.
    """
    global _daily_cost

    # Restore persisted cost on first call (cold start recovery)
    if not _daily_cost_reset_date:
        await _restore_daily_cost()

    if _daily_cost >= AUTONOMOUS_COST_LIMIT:
        return {
            "error": f"Daily cost limit ${AUTONOMOUS_COST_LIMIT:.2f} reached (${_daily_cost:.2f})",
            "thinking": [],
            "tool_calls": [],
            "response": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "cost": 0.0,
        }

    client = _get_client()
    messages: list[dict] = [{"role": "user", "content": task_prompt}]
    result = {
        "thinking": [],
        "tool_calls": [],
        "response": "",
        "input_tokens": 0,
        "output_tokens": 0,
        "cost": 0.0,
        "task_name": task_name,
        "started_at": datetime.now(UTC).isoformat(),
    }

    start_time = time.monotonic()

    for turn in range(max_turns):
        try:
            response = await client.messages.create(
                model=AUTONOMOUS_MODEL,
                max_tokens=16000,
                thinking={
                    "type": "enabled",
                    "budget_tokens": 10000,
                },
                system=AUTONOMOUS_SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
        except Exception as e:
            logger.error("Claude API error on turn %d: %s", turn, e)
            result["error"] = str(e)
            break

        result["input_tokens"] += response.usage.input_tokens
        result["output_tokens"] += response.usage.output_tokens
        call_cost = _track_cost(response.usage.input_tokens, response.usage.output_tokens)
        result["cost"] += call_cost

        # Extract content
        for block in response.content:
            if block.type == "thinking":
                result["thinking"].append(block.thinking)
            elif block.type == "text":
                result["response"] += block.text

        if response.stop_reason != "tool_use":
            break

        # Execute tools, preserve thinking blocks in assistant message
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                logger.info("Tool call: %s(%s)", block.name, json.dumps(block.input)[:200])
                result["tool_calls"].append({"tool": block.name, "input": block.input})
                tool_output = await execute_tool(block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_output,
                    }
                )
        messages.append({"role": "user", "content": tool_results})

        # Check cost limit mid-run
        if _daily_cost >= AUTONOMOUS_COST_LIMIT:
            logger.warning("Daily cost limit reached mid-task: $%.2f", _daily_cost)
            result["response"] += "\n\n[COST LIMIT REACHED — task stopped]"
            await _persist_daily_cost()
            await _notify_cost_cap_reached()
            break

    result["duration_ms"] = int((time.monotonic() - start_time) * 1000)
    result["completed_at"] = datetime.now(UTC).isoformat()

    # Persist cost after every task completion
    await _persist_daily_cost()

    logger.info(
        "Task %s completed: %d tool calls, %d input tokens, %d output tokens, $%.4f",
        task_name,
        len(result["tool_calls"]),
        result["input_tokens"],
        result["output_tokens"],
        result["cost"],
    )

    return result
