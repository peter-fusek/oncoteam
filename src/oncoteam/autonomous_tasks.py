"""Autonomous task wrappers: clinical protocol + research + reporting."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from . import oncofiles_client
from .activity_logger import get_session_id, record_suppressed_error
from .autonomous import run_autonomous_task
from .clinical_protocol import WATCHED_TRIALS, format_pre_cycle_checklist, get_milestones_for_cycle
from .patient_context import PATIENT, RESEARCH_TERMS

logger = logging.getLogger("oncoteam.autonomous_tasks")

# ── State helpers ──────────────────────────────


async def _get_state(key: str) -> dict:
    try:
        return await oncofiles_client.get_agent_state(key)
    except Exception:
        return {}


async def _set_state(key: str, value: dict) -> None:
    try:
        await oncofiles_client.set_agent_state(key, value)
    except Exception as e:
        record_suppressed_error("autonomous_tasks", f"set_state:{key}", e)


async def _log_task(task_name: str, result: dict) -> None:
    """Log task completion to activity log and diary."""
    try:
        await oncofiles_client.add_activity_log(
            session_id=get_session_id(),
            agent_id="oncoteam-autonomous",
            tool_name=task_name,
            input_summary=f"autonomous task: {task_name}",
            output_summary=(
                f"{len(result.get('tool_calls', []))} tool calls, ${result.get('cost', 0):.4f}"
            ),
            duration_ms=result.get("duration_ms", 0),
            status="error" if result.get("error") else "ok",
            error_message=result.get("error"),
            tags=["autonomous"],
        )
    except Exception as e:
        record_suppressed_error(task_name, "log_activity", e)


# ── Clinical Protocol Tasks ───────────────────


async def run_pre_cycle_check() -> dict:
    """Pre-cycle safety check before each FOLFOX infusion."""
    cycle = PATIENT.current_cycle or 2
    milestones = get_milestones_for_cycle(cycle)
    milestone_text = (
        "\n".join(f"- Cycle {m['cycle']}: {m['description']}" for m in milestones)
        or "None upcoming"
    )
    checklist = format_pre_cycle_checklist(cycle, milestones=milestone_text)

    prompt = f"""\
Run a pre-cycle safety check for FOLFOX cycle {cycle}.

{checklist}

Instructions:
1. Use search_documents to find the latest lab results (search "lab" or "krvny obraz")
2. Use get_treatment_timeline to check treatment history
3. Check lab values against safety thresholds
4. Assess toxicity trends from available data
5. Generate specific questions for the oncologist
6. Store the completed checklist as a briefing

Focus on: ANC, PLT (chemo + anticoag safety), liver enzymes, creatinine, neuropathy grade.
"""
    result = await run_autonomous_task(prompt, max_turns=10, task_name="pre_cycle_check")
    await _log_task("pre_cycle_check", result)
    await _set_state(
        "last_pre_cycle_check",
        {
            "cycle": cycle,
            "timestamp": datetime.now(UTC).isoformat(),
            "tool_calls": len(result.get("tool_calls", [])),
            "cost": result.get("cost", 0),
        },
    )
    return result


async def run_tumor_marker_review() -> dict:
    """Review CEA and CA 19-9 tumor marker trends."""
    prompt = """\
Review tumor marker trends (CEA, CA 19-9).

Instructions:
1. Search oncofiles for tumor marker data (search "CEA", "CA 19-9", "tumor marker")
2. Search oncofiles for lab results that may contain marker values
3. Analyze trend: rising/falling/stable
4. Compare to expected response on mFOLFOX6
5. If markers rising: flag possible progression, recommend imaging
6. Store findings as a briefing

Reference ESMO guidelines for marker interpretation in mCRC monitoring.
"""
    result = await run_autonomous_task(prompt, max_turns=8, task_name="tumor_marker_review")
    await _log_task("tumor_marker_review", result)
    return result


async def run_response_assessment() -> dict:
    """Check if response imaging is due and prepare assessment template."""
    cycle = PATIENT.current_cycle or 2
    prompt = f"""\
Response assessment check for cycle {cycle}.

Instructions:
1. Use get_treatment_timeline to find imaging events and cycle history
2. Determine if CT response evaluation is due (first at cycle 3-4, then every 8 weeks)
3. If imaging is available, review findings against RECIST 1.1 criteria
4. If imaging is due but not scheduled, flag for scheduling
5. If progressive disease detected: trigger urgent flag, list 2L options
6. Store assessment as a briefing with appropriate urgency tags

RECIST categories: CR, PR (partial response), SD (stable disease), PD (progressive disease)
"""
    result = await run_autonomous_task(prompt, max_turns=8, task_name="response_assessment")
    await _log_task("response_assessment", result)
    return result


# ── Research Tasks ─────────────────────────────


async def run_daily_research() -> dict:
    """Daily PubMed research scan with all curated search terms."""
    terms_text = "\n".join(f"- {t}" for t in RESEARCH_TERMS)
    prompt = f"""\
Run daily research scan for relevant new literature.

Search terms:
{terms_text}

Instructions:
1. Search PubMed for each term (use max_results=5 per query)
2. For high-relevance articles, note: PMID, title, key findings
3. Assess relevance to this specific patient case (KRAS G12S, mFOLFOX6, mCRC)
4. Identify any practice-changing findings
5. Store a summary briefing with the most relevant findings

Focus on: treatment advances for KRAS G12S mCRC, FOLFOX optimization,
novel targets, clinical trial results.
"""
    result = await run_autonomous_task(prompt, max_turns=12, task_name="daily_research")
    await _log_task("daily_research", result)
    await _set_state(
        "last_daily_research",
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "tool_calls": len(result.get("tool_calls", [])),
            "cost": result.get("cost", 0),
        },
    )
    return result


async def run_trial_monitor() -> dict:
    """Monitor clinical trials across SK, CZ, AT, HU."""
    watched = "\n".join(f"- {t}" for t in WATCHED_TRIALS)
    prompt = f"""\
Monitor clinical trials for new eligible options.

Watched trials:
{watched}

Instructions:
1. Search ClinicalTrials.gov for mCRC trials across SK, CZ, AT, HU
2. For each new trial found, check eligibility (KRAS G12S, active VTE, ECOG)
3. Look specifically for watched trials and report any status changes
4. Flag newly eligible or newly opened trials
5. Store findings as a briefing

Search terms: "KRAS mutant colorectal cancer", "pan-KRAS inhibitor", "MSS colorectal immunotherapy"
"""
    result = await run_autonomous_task(prompt, max_turns=10, task_name="trial_monitor")
    await _log_task("trial_monitor", result)
    return result


async def run_file_scan() -> dict:
    """Scan oncofiles for new document uploads."""
    state = await _get_state("last_file_scan")
    last_scan = state.get("value", {}).get("timestamp", "") if isinstance(state, dict) else ""

    prompt = f"""\
Scan for new document uploads since last check ({last_scan or "first run"}).

Instructions:
1. Search documents for recent pathology, genetics, and lab reports
2. For pathology/genetics docs: check if biomarker data matches known profile
3. For lab docs: check values against safety thresholds
4. Flag any discrepancies or new information
5. If new biomarker data found, note for physician review

Search categories: "pathology", "genetics", "labs", "imaging"
"""
    result = await run_autonomous_task(prompt, max_turns=8, task_name="file_scan")
    await _log_task("file_scan", result)
    await _set_state(
        "last_file_scan",
        {
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
    return result


# ── Reporting Tasks ────────────────────────────


async def run_weekly_briefing() -> dict:
    """Compile weekly briefing: research, trials, labs, treatment progress."""
    cycle = PATIENT.current_cycle or 2
    milestones = get_milestones_for_cycle(cycle)
    milestone_text = (
        "\n".join(f"- Cycle {m['cycle']}: {m['description']}" for m in milestones)
        or "None upcoming"
    )

    prompt = f"""\
Compile the weekly briefing for physician review.

Current status: mFOLFOX6 cycle {cycle}, current milestones: {milestone_text}

Instructions:
1. Get treatment timeline to understand current progress
2. Search for this week's research findings in oncofiles
3. Check for any new trial updates
4. Summarize lab trends if available
5. List upcoming milestones from treatment protocol
6. Generate 3-5 specific questions for the oncologist
7. Include any treatment recommendations with ESMO/NCCN references
8. Store the complete weekly briefing

Structure the briefing with clear sections:
- Treatment Status
- Research Highlights
- Clinical Trial Updates
- Lab Trends
- Upcoming Milestones
- Recommendations
- Questions for Oncologist
"""
    result = await run_autonomous_task(prompt, max_turns=12, task_name="weekly_briefing")
    await _log_task("weekly_briefing", result)
    return result


async def run_mtb_preparation() -> dict:
    """Prepare tumor board (MTB) presentation summary."""
    prompt = """\
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
- Recommendations
"""
    result = await run_autonomous_task(prompt, max_turns=10, task_name="mtb_preparation")
    await _log_task("mtb_preparation", result)
    return result
