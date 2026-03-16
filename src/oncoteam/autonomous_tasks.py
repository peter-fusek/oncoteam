"""Autonomous task wrappers: clinical protocol + research + reporting."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from . import oncofiles_client
from .activity_logger import get_session_id, record_suppressed_error
from .autonomous import run_autonomous_task
from .clinical_protocol import WATCHED_TRIALS, format_pre_cycle_checklist, get_milestones_for_cycle
from .patient_context import PATIENT, RESEARCH_TERMS

logger = logging.getLogger("oncoteam.autonomous_tasks")


def _extract_timestamp(state: dict | None) -> str:
    """Safely extract timestamp from agent_state, handling all return formats."""
    if not isinstance(state, dict):
        return ""
    # Flat format: {"timestamp": "..."}
    if "timestamp" in state:
        return state["timestamp"]
    # Nested format: {"value": '{"timestamp": "..."}' or {"timestamp": "..."}}
    raw = state.get("value")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return ""
    if isinstance(raw, dict):
        return raw.get("timestamp", "")
    return ""


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
    logger.info(">>> Starting task: pre_cycle_check")
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
    try:
        result = await run_autonomous_task(prompt, max_turns=10, task_name="pre_cycle_check")
    except Exception as e:
        logger.error("!!! Failed task: pre_cycle_check — %s", e)
        raise
    logger.info(
        "<<< Completed task: pre_cycle_check (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
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
    logger.info(">>> Starting task: tumor_marker_review")
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
    try:
        result = await run_autonomous_task(prompt, max_turns=8, task_name="tumor_marker_review")
    except Exception as e:
        logger.error("!!! Failed task: tumor_marker_review — %s", e)
        raise
    logger.info(
        "<<< Completed task: tumor_marker_review (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("tumor_marker_review", result)
    await _set_state(
        "last_tumor_marker_review",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
    )
    return result


async def run_response_assessment() -> dict:
    """Check if response imaging is due and prepare assessment template."""
    logger.info(">>> Starting task: response_assessment")
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
    try:
        result = await run_autonomous_task(prompt, max_turns=8, task_name="response_assessment")
    except Exception as e:
        logger.error("!!! Failed task: response_assessment — %s", e)
        raise
    logger.info(
        "<<< Completed task: response_assessment (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("response_assessment", result)
    await _set_state(
        "last_response_assessment",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
    )
    return result


# ── Research Tasks ─────────────────────────────


async def run_daily_research() -> dict:
    """Daily PubMed research scan with all curated search terms."""
    logger.info(">>> Starting task: daily_research")
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
    try:
        result = await run_autonomous_task(prompt, max_turns=12, task_name="daily_research")
    except Exception as e:
        logger.error("!!! Failed task: daily_research — %s", e)
        raise
    logger.info(
        "<<< Completed task: daily_research (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
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
    logger.info(">>> Starting task: trial_monitor")
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
    try:
        result = await run_autonomous_task(prompt, max_turns=10, task_name="trial_monitor")
    except Exception as e:
        logger.error("!!! Failed task: trial_monitor — %s", e)
        raise
    logger.info(
        "<<< Completed task: trial_monitor (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("trial_monitor", result)
    await _set_state(
        "last_trial_monitor",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
    )
    return result


async def run_file_scan() -> dict:
    """Scan oncofiles for new document uploads."""
    logger.info(">>> Starting task: file_scan")
    state = await _get_state("last_file_scan")
    last_scan = _extract_timestamp(state)

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
    try:
        result = await run_autonomous_task(prompt, max_turns=8, task_name="file_scan")
    except Exception as e:
        logger.error("!!! Failed task: file_scan — %s", e)
        raise
    logger.info(
        "<<< Completed task: file_scan (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
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
    logger.info(">>> Starting task: weekly_briefing")
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
    try:
        result = await run_autonomous_task(prompt, max_turns=12, task_name="weekly_briefing")
    except Exception as e:
        logger.error("!!! Failed task: weekly_briefing — %s", e)
        raise
    logger.info(
        "<<< Completed task: weekly_briefing (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("weekly_briefing", result)
    await _set_state(
        "last_weekly_briefing",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
    )
    return result


async def run_lab_sync() -> dict:
    """Extract lab values from oncofiles documents and store as structured lab data."""
    logger.info(">>> Starting task: lab_sync")
    prompt = """\
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
creatinine, ALT, AST, bilirubin, CEA, CA_19_9, ABS_LYMPH.
"""
    try:
        result = await run_autonomous_task(prompt, max_turns=8, task_name="lab_sync")
    except Exception as e:
        logger.error("!!! Failed task: lab_sync — %s", e)
        raise
    logger.info(
        "<<< Completed task: lab_sync (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("lab_sync", result)
    await _set_state(
        "last_lab_sync",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
    )
    return result


async def run_toxicity_extraction() -> dict:
    """Extract toxicity grades from doctor visit notes/reports."""
    logger.info(">>> Starting task: toxicity_extraction")
    prompt = """\
Search for doctor visit notes and extract NCI-CTCAE toxicity assessments.

Instructions:
1. Search documents for visit reports, discharge summaries, consultation notes
   (search "konzultacia", "vizita", "prepustenie", "kontrola")
2. For each document with toxicity data, extract grades for:
   - Peripheral neuropathy, diarrhea, mucositis, fatigue, HFS, nausea/vomiting
3. Note ECOG and weight if mentioned
4. Store a briefing summarizing extracted toxicity data with dates

This creates the baseline toxicity history from existing medical documents.
"""
    try:
        result = await run_autonomous_task(prompt, max_turns=8, task_name="toxicity_extraction")
    except Exception as e:
        logger.error("!!! Failed task: toxicity_extraction — %s", e)
        raise
    logger.info(
        "<<< Completed task: toxicity_extraction (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("toxicity_extraction", result)
    await _set_state(
        "last_toxicity_extraction",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
    )
    return result


async def run_weight_extraction() -> dict:
    """Extract weight/BMI from doctor visit notes and store as weight_measurement events."""
    logger.info(">>> Starting task: weight_extraction")
    prompt = """\
Search for doctor visit notes and extract weight/BMI data.

Instructions:
1. Search documents for visit reports, consultation notes, discharge summaries
   (search "hmotnosť", "váha", "BMI", "hmotnost", "vizita", "kontrola")
2. For each document with weight data, extract:
   - Weight in kg
   - BMI if mentioned
   - Date of measurement
3. Check if a weight_measurement event already exists for that date
4. If not, store as a treatment event with event_type="weight_measurement"
5. Store a briefing summarizing what was extracted

Focus on creating structured weight history from existing medical documents.
"""
    try:
        result = await run_autonomous_task(prompt, max_turns=8, task_name="weight_extraction")
    except Exception as e:
        logger.error("!!! Failed task: weight_extraction — %s", e)
        raise
    logger.info(
        "<<< Completed task: weight_extraction (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("weight_extraction", result)
    await _set_state(
        "last_weight_extraction",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
    )
    return result


async def run_family_update() -> dict:
    """Generate weekly family update in Slovak from current clinical data."""
    logger.info(">>> Starting task: family_update")
    cycle = PATIENT.current_cycle or 2
    prompt = f"""\
Napíš týždennú správu pre rodinu pacientky v slovenčine.

Pokyny:
1. Získaj najnovšie laboratórne výsledky (search "lab", "krvny obraz")
2. Získaj najnovšie údaje o toxicite
3. Zhrň aktuálny stav liečby (cyklus {cycle}, mFOLFOX6)
4. Preložíš do jednoduchej, zrozumiteľnej slovenčiny:
   - ANC v norme → "Krvné hodnoty sú v bezpečnom rozsahu"
   - Neuropatia → "Mierne brnenie v prstoch"
   - ECOG 1 → "Zvláda väčšinu bežných aktivít, ale rýchlejšie sa unaví"
   - Hmotnosť stabilná → "Hmotnosť je stabilná"
5. Ulož ako konverzáciu s entry_type="family_update" a tag "lang:sk"

Píš v slovenčine, jednoducho a zrozumiteľne pre laikov.
Používaj správnu slovenskú lekársku terminológiu (onkológ, chemoterapia, cyklus).
Vyhni sa zbytočným odborným detailom.
"""
    try:
        result = await run_autonomous_task(prompt, max_turns=10, task_name="family_update")
    except Exception as e:
        logger.error("!!! Failed task: family_update — %s", e)
        raise
    logger.info(
        "<<< Completed task: family_update (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("family_update", result)
    await _set_state(
        "last_family_update",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
    )
    return result


async def run_medication_adherence_check() -> dict:
    """Check if today's medication adherence was logged. Flag missing Clexane."""
    logger.info(">>> Starting task: medication_adherence_check")
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    prompt = f"""\
Check medication adherence for today ({today}).

Instructions:
1. Use get_treatment_timeline to find today's medication_adherence events
2. If no adherence logged for today, create a reminder briefing
3. Specifically flag if Clexane (anticoagulant) adherence is missing — critical for VTE
4. Store a briefing noting adherence status

This is a safety check: Clexane non-compliance with active VJI thrombosis is dangerous.
"""
    try:
        result = await run_autonomous_task(
            prompt,
            max_turns=6,
            task_name="medication_adherence_check",
        )
    except Exception as e:
        logger.error("!!! Failed task: medication_adherence_check — %s", e)
        raise
    logger.info(
        "<<< Completed task: medication_adherence_check (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("medication_adherence_check", result)
    await _set_state(
        "last_medication_adherence_check",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
    )
    return result


async def run_mtb_preparation() -> dict:
    """Prepare tumor board (MTB) presentation summary."""
    logger.info(">>> Starting task: mtb_preparation")
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
    try:
        result = await run_autonomous_task(prompt, max_turns=10, task_name="mtb_preparation")
    except Exception as e:
        logger.error("!!! Failed task: mtb_preparation — %s", e)
        raise
    logger.info(
        "<<< Completed task: mtb_preparation (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("mtb_preparation", result)
    await _set_state(
        "last_mtb_preparation",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
    )
    return result


async def _send_whatsapp(msg: str) -> dict:
    """Send a WhatsApp message via dashboard internal endpoint."""
    import httpx

    from .config import DASHBOARD_API_KEY

    dashboard_url = "https://dashboard.oncoteam.cloud"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{dashboard_url}/api/internal/whatsapp-notify",
            json={"message": msg},
            headers={"Authorization": f"Bearer {DASHBOARD_API_KEY}"},
        )
        resp.raise_for_status()
        return resp.json()


async def run_daily_cost_report() -> dict:
    """Send morning clinical summary + cost via WhatsApp (no Claude API call)."""
    from .autonomous import get_daily_cost
    from .config import ANTHROPIC_CREDIT_BALANCE, AUTONOMOUS_COST_LIMIT

    logger.info(">>> Starting task: daily_cost_report")
    try:
        now = datetime.now(UTC)
        month_key = now.strftime("%Y-%m")
        lines = [f"*Oncoteam Ranný prehľad*\n{now.strftime('%Y-%m-%d')}\n"]

        # --- Labs section ---
        try:
            trends = await oncofiles_client.get_lab_trends_data(limit=200)
            values_list = trends.get("values", []) if isinstance(trends, dict) else []
            if values_list:
                from collections import defaultdict

                by_date: dict[str, dict] = defaultdict(dict)
                for v in values_list:
                    d = v.get("lab_date", "")
                    if d:
                        by_date[d][v.get("parameter", "")] = v.get("value")
                if by_date:
                    latest_date = max(by_date.keys())
                    vals = by_date[latest_date]
                    anc = vals.get("ABS_NEUT", vals.get("ANC"))
                    plt = vals.get("PLT")
                    wbc = vals.get("WBC")
                    hgb = vals.get("HGB")
                    lines.append(f"*Labky ({latest_date})*")
                    if anc is not None:
                        flag = " ⚠️" if anc < 1.5 else ""
                        lines.append(f"  ANC: {anc}{flag}")
                    if plt is not None:
                        lines.append(f"  PLT: {plt:.0f}")
                    if wbc is not None:
                        lines.append(f"  WBC: {wbc}")
                    if hgb is not None:
                        lines.append(f"  HGB: {hgb}")
                    lines.append("")
        except Exception:
            lines.append("Labky: nedostupné\n")

        # --- Cycle section ---
        lines.append(f"*Cyklus {PATIENT.get('current_cycle', 3)}* — mFOLFOX6")
        lines.append("")

        # --- Cost section ---
        today_spend = get_daily_cost()
        mtd_spend = 0.0
        try:
            raw = await oncofiles_client.get_agent_state("autonomous_mtd_cost")
            state = raw if isinstance(raw, dict) else {}
            if "value" in state:
                v = state["value"]
                if isinstance(v, str):
                    v = json.loads(v)
                state = v if isinstance(v, dict) else {}
            if state.get("month") == month_key:
                mtd_spend = float(state.get("cost_usd", 0.0))
        except Exception:
            pass

        remaining = max(0, ANTHROPIC_CREDIT_BALANCE - mtd_spend)
        lines.append(
            f"*Agent*: ${today_spend:.2f}/${AUTONOMOUS_COST_LIMIT:.2f} dnes"
            f" | ${mtd_spend:.2f} MTD | ${remaining:.2f} zostatok"
        )
        if remaining < 5:
            lines.append("⚠️ Nízky zostatok!")

        msg = "\n".join(lines)
        result_data = await _send_whatsapp(msg)

        sent = result_data.get("sent", 0)
        logger.info("<<< Completed task: daily_cost_report — sent to %d", sent)
        return {"ok": True, "message": msg, "sent": sent}

    except Exception as e:
        logger.error("!!! Failed task: daily_cost_report — %s", e)
        record_suppressed_error("daily_cost_report", "send", e)
        return {"ok": False, "error": str(e)}
