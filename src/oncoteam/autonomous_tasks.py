"""Autonomous task wrappers: clinical protocol + research + reporting."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime

from . import oncofiles_client
from .activity_logger import get_session_id, record_suppressed_error
from .agent_registry import get_cooldown
from .autonomous import run_autonomous_task
from .clinical_protocol import WATCHED_TRIALS, format_pre_cycle_checklist, get_milestones_for_cycle
from .config import AUTONOMOUS_MODEL, AUTONOMOUS_MODEL_LIGHT
from .patient_context import (
    format_whatsapp_header,
    get_patient,
    get_patient_research_terms,
    get_patient_token,
)


def _patient_display_name(patient_id: str) -> str:
    """Get patient display name for WhatsApp headers. Returns '' if unknown."""
    try:
        return get_patient(patient_id).name
    except (KeyError, AttributeError):
        return patient_id


async def _should_skip(
    task_name: str, patient_id: str = "q1b", *, token: str | None = None
) -> bool:
    """Check if task ran recently enough to skip this execution."""
    cooldown_hours = get_cooldown(task_name)
    if cooldown_hours <= 0:
        return False
    state = await _get_state(f"last_{task_name}:{patient_id}", token=token)
    ts = _extract_timestamp(state)
    if not ts:
        return False  # Never ran — let it run
    try:
        last_run = datetime.fromisoformat(ts)
        elapsed = (datetime.now(UTC) - last_run).total_seconds() / 3600
        if elapsed < cooldown_hours:
            logger.info(
                "Skipping %s: ran %.1fh ago (cooldown: %.1fh)",
                task_name,
                elapsed,
                cooldown_hours,
            )
            return True
    except (ValueError, TypeError) as e:
        logger.debug("_should_skip(%s): could not parse timestamp %r: %s", task_name, ts, e)
    return False


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


async def _get_state(key: str, *, token: str | None = None) -> dict:
    try:
        return await oncofiles_client.get_agent_state(key, token=token)
    except Exception as e:
        record_suppressed_error("autonomous_tasks", f"get_state:{key}", e)
        return {}


async def _set_state(key: str, value: dict, *, token: str | None = None) -> None:
    try:
        await oncofiles_client.set_agent_state(key, value, token=token)
    except Exception as e:
        record_suppressed_error("autonomous_tasks", f"set_state:{key}", e)


# ── #403 notification hygiene ───────────────────
# Idempotency + freshness helpers for WhatsApp push. Keep the implementation
# surgical — the full NotificationGate redesign in #403 Phase 2 is a separate
# multi-session arc; right now we just kill the two reported regressions:
# stale ANC alerts re-emitted on every lab_sync run, and paused-patient bleed.

# Window during which an identical notification signature will not re-fire.
_NOTIF_DEDUP_TTL_HOURS = 24


async def _already_notified(patient_id: str, signature: str, *, token: str | None = None) -> bool:
    """Return True if the same signature was already pushed within the TTL.

    `signature` should encode the event uniquely — e.g. for a lab safety
    alert: `lab_alert:2026-04-22:ANC=1150:PLT=75000`. If the same signature
    fired inside `_NOTIF_DEDUP_TTL_HOURS`, we skip the re-push. The agent
    run itself still executes and still logs to oncofiles; only the
    user-facing WhatsApp push is suppressed.
    """
    key = f"notif_dedup:{patient_id}:{signature}"
    state = await _get_state(key, token=token)
    ts = _extract_timestamp(state)
    if not ts:
        return False
    try:
        last = datetime.fromisoformat(ts)
        elapsed_h = (datetime.now(UTC) - last).total_seconds() / 3600
        return elapsed_h < _NOTIF_DEDUP_TTL_HOURS
    except (ValueError, TypeError):
        return False


async def _mark_notified(patient_id: str, signature: str, *, token: str | None = None) -> None:
    """Record that a signature was pushed so future runs within TTL skip it."""
    key = f"notif_dedup:{patient_id}:{signature}"
    await _set_state(
        key,
        {"timestamp": datetime.now(UTC).isoformat(), "signature": signature},
        token=token,
    )


def _event_is_stale(event_date_str: str, *, freshness_days: int = 7) -> bool:
    """Return True if the event is older than `freshness_days`.

    Used to gate "new alert" pushes — an alert for ANC <1500 on a lab taken
    35 days ago is not news, it's a re-emission. The alerts the user
    actually wants are threshold-crossing events discovered in fresh data.
    Parse is tolerant: if the string doesn't parse we assume fresh
    (fail-open), since suppressing on parse failure would silently eat real
    alerts.
    """
    if not event_date_str:
        return False
    try:
        event_date = datetime.fromisoformat(event_date_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        try:
            # Fallback for bare YYYY-MM-DD strings
            event_date = datetime.strptime(event_date_str[:10], "%Y-%m-%d").replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return False
    if event_date.tzinfo is None:
        event_date = event_date.replace(tzinfo=UTC)
    age_days = (datetime.now(UTC) - event_date).total_seconds() / 86400
    return age_days > freshness_days


async def _log_task(task_name: str, result: dict, *, token: str | None = None) -> None:
    """Log task completion to activity log, diary, and store full run trace."""
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
            tags=["sys:autonomous"],
            token=token,
        )
    except Exception as e:
        record_suppressed_error(task_name, "log_activity", e)

    # Store full run trace for dashboard observability (#92)
    try:
        cost = result.get("cost", 0)
        n_tools = len(result.get("tool_calls", []))
        model = result.get("model", "")
        dur = result.get("duration_ms", 0)
        err = result.get("error")
        title_suffix = f" | ${cost:.4f} | {n_tools} tools | {dur}ms"
        if err:
            title_suffix += " | ERROR"
        tags = (
            f"task:{task_name},sys:agent-run,"
            f"cost:{cost:.4f},tools:{n_tools},model:{model},dur:{dur}"
        )
        await oncofiles_client.log_conversation(
            title=f"Agent run: {task_name}{title_suffix}",
            content=json.dumps(
                {
                    "task_name": task_name,
                    "model": model,
                    "prompt": result.get("prompt", ""),
                    "thinking": result.get("thinking", []),
                    "tool_calls": result.get("tool_calls", []),
                    "messages": result.get("messages", []),
                    "response": result.get("response", ""),
                    "cost": cost,
                    "duration_ms": dur,
                    "input_tokens": result.get("input_tokens", 0),
                    "output_tokens": result.get("output_tokens", 0),
                    "turns": result.get("turns", 0),
                    "started_at": result.get("started_at"),
                    "completed_at": result.get("completed_at"),
                    "error": err,
                },
                ensure_ascii=False,
            ),
            entry_type="agent_run",
            tags=tags,
            token=token,
        )
    except Exception as e:
        record_suppressed_error(task_name, "store_trace", e)


# ── Clinical Protocol Tasks ───────────────────


async def run_pre_cycle_check(patient_id: str = "q1b") -> dict:
    """Pre-cycle safety check before each chemo infusion."""
    token = get_patient_token(patient_id)
    if await _should_skip("pre_cycle_check", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: pre_cycle_check (patient=%s)", patient_id)
    patient = get_patient(patient_id)
    cycle = patient.current_cycle or 2
    milestones = get_milestones_for_cycle(cycle)
    milestone_text = (
        "\n".join(f"- Cycle {m['cycle']}: {m['description']}" for m in milestones)
        or "None upcoming"
    )
    checklist = format_pre_cycle_checklist(cycle, milestones=milestone_text)

    prompt = f"""\
Run a pre-cycle safety check for {patient.treatment_regimen} cycle {cycle}.

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
        result = await run_autonomous_task(
            prompt, max_turns=10, task_name="pre_cycle_check", patient_id=patient_id
        )
    except Exception as e:
        logger.error("!!! Failed task: pre_cycle_check — %s", e)
        raise
    logger.info(
        "<<< Completed task: pre_cycle_check (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("pre_cycle_check", result, token=token)
    await _set_state(
        f"last_pre_cycle_check:{patient_id}",
        {
            "cycle": cycle,
            "timestamp": datetime.now(UTC).isoformat(),
            "tool_calls": len(result.get("tool_calls", [])),
            "cost": result.get("cost", 0),
        },
        token=token,
    )

    # Send WhatsApp summary
    try:
        response_text = result.get("response", "")
        if response_text and not result.get("error"):
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            header = format_whatsapp_header(
                f"Kontrola pred cyklom {cycle}",
                date_str=today,
                patient_name=_patient_display_name(patient_id),
            )
            summary = response_text[:1400]
            if len(response_text) > 1400:
                summary += "\n\n... (plná správa na dashboarde)"
            await _send_whatsapp(
                header + summary,
                recipient="caregiver",
                template_key="pre_cycle",
                patient_id=patient_id,
            )
    except Exception as e:
        record_suppressed_error("pre_cycle_check", "whatsapp_notify", e)

    return result


async def run_tumor_marker_review(patient_id: str = "q1b") -> dict:
    """Review CEA and CA 19-9 tumor marker trends."""
    token = get_patient_token(patient_id)
    if await _should_skip("tumor_marker_review", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: tumor_marker_review (patient=%s)", patient_id)
    prompt = """\
Review tumor marker trends (CEA, CA 19-9).

Instructions:
1. Search oncofiles for tumor marker data (search "CEA", "CA 19-9", "tumor marker")
2. Search oncofiles for lab results that may contain marker values
3. Analyze trend: rising/falling/stable
4. Compare to expected response on current regimen
5. If markers rising: flag possible progression, recommend imaging
6. Store findings as a briefing

Reference ESMO/NCCN guidelines for marker interpretation.
"""
    try:
        result = await run_autonomous_task(
            prompt, max_turns=8, task_name="tumor_marker_review", patient_id=patient_id
        )
    except Exception as e:
        logger.error("!!! Failed task: tumor_marker_review — %s", e)
        raise
    logger.info(
        "<<< Completed task: tumor_marker_review (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("tumor_marker_review", result, token=token)
    await _set_state(
        f"last_tumor_marker_review:{patient_id}",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
        token=token,
    )
    return result


async def run_response_assessment(patient_id: str = "q1b") -> dict:
    """Check if response imaging is due and prepare assessment template."""
    token = get_patient_token(patient_id)
    if await _should_skip("response_assessment", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: response_assessment (patient=%s)", patient_id)
    patient = get_patient(patient_id)
    cycle = patient.current_cycle or 2
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
        result = await run_autonomous_task(
            prompt, max_turns=8, task_name="response_assessment", patient_id=patient_id
        )
    except Exception as e:
        logger.error("!!! Failed task: response_assessment — %s", e)
        raise
    logger.info(
        "<<< Completed task: response_assessment (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("response_assessment", result, token=token)
    await _set_state(
        f"last_response_assessment:{patient_id}",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
        token=token,
    )
    return result


# ── Research Tasks ─────────────────────────────


async def run_daily_research(patient_id: str = "q1b") -> dict:
    """Daily PubMed research scan with all curated search terms."""
    token = get_patient_token(patient_id)
    if await _should_skip("daily_research", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: daily_research (patient=%s)", patient_id)
    research_terms = get_patient_research_terms(patient_id)
    terms_text = "\n".join(f"- {t}" for t in research_terms)
    prompt = f"""\
Run daily research scan for relevant new literature.

Search terms:
{terms_text}

Instructions:
1. Search PubMed for each term (use max_results=5 per query)
2. For high-relevance articles, note: PMID, title, key findings
3. Assess relevance to this specific patient (use get_patient_context for biomarkers and regimen)
4. Identify any practice-changing findings
5. Store a summary briefing with the most relevant findings

Focus on: treatment advances relevant to this patient's cancer type,
regimen optimization, novel targets, clinical trial results.
"""
    try:
        result = await run_autonomous_task(
            prompt, max_turns=12, task_name="daily_research", patient_id=patient_id
        )
    except Exception as e:
        logger.error("!!! Failed task: daily_research — %s", e)
        raise
    logger.info(
        "<<< Completed task: daily_research (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("daily_research", result, token=token)
    await _set_state(
        f"last_daily_research:{patient_id}",
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "tool_calls": len(result.get("tool_calls", [])),
            "cost": result.get("cost", 0),
        },
        token=token,
    )
    return result


async def run_trial_monitor(patient_id: str = "q1b") -> dict:
    """Monitor clinical trials across EU (14 countries incl. major CRC centers)."""
    token = get_patient_token(patient_id)
    if await _should_skip("trial_monitor", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: trial_monitor (patient=%s)", patient_id)
    watched = "\n".join(f"- {t}" for t in WATCHED_TRIALS)

    # Load previously seen NCT IDs to detect new trials
    prev_state = await _get_state("trial_monitor_seen_ncts", token=token)
    prev_ncts_raw = prev_state.get("value", prev_state) if isinstance(prev_state, dict) else {}
    if isinstance(prev_ncts_raw, str):
        try:
            prev_ncts_raw = json.loads(prev_ncts_raw)
        except (json.JSONDecodeError, TypeError):
            prev_ncts_raw = {}
    prev_ncts = prev_ncts_raw.get("nct_ids", []) if isinstance(prev_ncts_raw, dict) else []

    prompt = f"""\
Monitor clinical trials for new eligible options across the EU.

Watched trials:
{watched}

Previously seen NCT IDs (skip these unless status changed):
{json.dumps(prev_ncts[:50]) if prev_ncts else "None — first scan"}

Major EU cancer centers to check (NCCN-affiliated / OECI-accredited):
Charite Berlin, NCT Heidelberg, LMU Munich, Gustave Roussy, Institut Curie,
Vall d'Hebron Barcelona, NKI-AVL Amsterdam, Erasmus MC, KU Leuven,
Karolinska Stockholm, Rigshospitalet Copenhagen, INT Milan, AKH Wien,
Masaryk Brno, NOÚ Bratislava

Instructions:
1. Use search_trials_eu (covers SK, CZ, AT, HU, DE, PL, IT, NL, BE, FR, DK, SE, ES, CH):
   - Search terms based on patient's cancer type and biomarkers (use get_patient_context)
2. Use search_trials for targeted center searches if relevant
3. For each NEW trial not in previously seen list, check eligibility via check_trial_eligibility
4. Look specifically for watched trials and report any status changes
5. Flag newly eligible or newly opened trials — note the country and center
6. Store findings as a briefing, clearly marking NEW vs KNOWN trials
7. Use set_agent_state to save "trial_monitor_seen_ncts" with all current NCT IDs

Prioritize trials at centers within practical travel distance from Bratislava:
- Tier 1 (< 2h): Vienna, Brno, Budapest, Bratislava
- Tier 2 (< 4h): Prague, Munich, Krakow
- Tier 3 (rest of EU): flag but note travel burden
"""
    try:
        result = await run_autonomous_task(
            prompt, max_turns=12, task_name="trial_monitor", patient_id=patient_id
        )
    except Exception as e:
        logger.error("!!! Failed task: trial_monitor — %s", e)
        raise
    logger.info(
        "<<< Completed task: trial_monitor (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("trial_monitor", result, token=token)
    await _set_state(
        f"last_trial_monitor:{patient_id}",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
        token=token,
    )

    # Send WhatsApp digest if there are findings
    try:
        response_text = result.get("response", "")
        if response_text and not result.get("error"):
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            header = format_whatsapp_header(
                "Klinické štúdie — EU sken",
                date_str=today,
                patient_name=_patient_display_name(patient_id),
            )
            summary = response_text[:1400]
            if len(response_text) > 1400:
                summary += "\n\n... (plná správa na dashboarde)"
            await _send_whatsapp(
                header + summary,
                recipient="caregiver",
                template_key="trial_match",
                patient_id=patient_id,
            )
    except Exception as e:
        record_suppressed_error("trial_monitor", "whatsapp_notify", e)

    return result


# Seeded NCT watchlist for DDR-deficient mCRC patients (#392).
# Combines ATM-biallelic-responsive trials (PARPi/ATRi) with pan-RAS inhibitors
# that are class-agnostic to the underlying KRAS allele. Refreshed quarterly;
# update when new trials open or existing ones close.
_DDR_SEED_WATCHLIST = [
    # Pan-RAS / RMC family (valid for KRAS G12S, not just G12C)
    "NCT05379985",  # Daraxonrasib / RMC-6236 (Revolution Medicines)
    # PARPi + bevacizumab / chemo maintenance in DDR-deficient CRC
    "NCT04456699",  # Olaparib + bevacizumab maintenance (Lancet Oncol)
    # ATRi + PARPi combinations targeting DDR-deficient solid tumors
    "NCT03188965",  # Ceralasertib + olaparib (AstraZeneca)
    "NCT04170153",  # Rucaparib maintenance in BRCA/PALB2/ATM mCRC
    "NCT04673448",  # Niraparib + atezolizumab in DDR-deficient GI
    "NCT04589845",  # Talazoparib + TAS-102 (AstraZeneca / Taiho)
    "NCT04657068",  # BAY 1895344 (elimusertib, ATR inhibitor, DDR defects)
    "NCT04497116",  # Camonsertib / RP-3500 (Repare Therapeutics)
]


async def run_ddr_monitor(patient_id: str = "q1b") -> dict:
    """Scan for DDR-targeted trials (PARPi/ATRi/pan-RAS) relevant to the patient.

    Guarded by is_ddr_deficient(patient) — returns {"skipped": "not_ddr"}
    for non-DDR-deficient patients so the scheduler stays cheap. Posts
    findings to the research funnel proposals lane only; no WhatsApp push
    per #395 "AI proposes, humans dispose". Physicians review via /research
    cockpit (#399) before anything enters the clinical funnel.
    """
    from .eligibility import get_latest_oncopanel, is_ddr_deficient

    patient = get_patient(patient_id)
    token = get_patient_token(patient_id)

    if not is_ddr_deficient(patient):
        return {"skipped": "not_ddr_deficient", "patient_id": patient_id}
    if await _should_skip("ddr_monitor", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: ddr_monitor (patient=%s)", patient_id)

    # Summarize the DDR findings so the prompt is concrete, not boilerplate.
    latest = get_latest_oncopanel(patient)
    ddr_summary_lines = []
    if latest is not None:
        for v in latest.variants:
            if v.gene.upper() in {"ATM", "BRCA1", "BRCA2", "PALB2"} and v.significance in {
                "pathogenic",
                "likely_pathogenic",
            }:
                ddr_summary_lines.append(
                    f"- {v.gene} {v.protein_short or v.hgvs_protein or v.hgvs_cdna}"
                    f" ({v.variant_type}, VAF {v.vaf:.2%}, tier {v.tier})"
                )
    ddr_summary = "\n".join(ddr_summary_lines) or "- (no variants extracted — check oncopanel)"
    seed_list = "\n".join(f"- {nct}" for nct in _DDR_SEED_WATCHLIST)

    prev_state = await _get_state("ddr_monitor_seen_ncts", token=token)
    prev_ncts_raw = prev_state.get("value", prev_state) if isinstance(prev_state, dict) else {}
    if isinstance(prev_ncts_raw, str):
        try:
            prev_ncts_raw = json.loads(prev_ncts_raw)
        except (json.JSONDecodeError, TypeError):
            prev_ncts_raw = {}
    prev_ncts = prev_ncts_raw.get("nct_ids", []) if isinstance(prev_ncts_raw, dict) else []
    first_run = not prev_ncts

    prompt = f"""\
Scan PubMed + ClinicalTrials for PARPi, ATRi, and pan-RAS combinations relevant
to this DDR-deficient patient. Findings go to the research funnel PROPOSALS
lane — NEVER post directly to the clinical lane. Physician triages.

DDR variants detected in the most recent oncopanel:
{ddr_summary}

Eligibility implications:
- PARPi (olaparib, rucaparib, niraparib, talazoparib) — ATM biallelic → eligible
- ATRi (ceralasertib, elimusertib, camonsertib) — DDR pathway synergy
- Platinum synergy (FOLFOX alignment) from ATM/BRCA deficiency
- Pan-RAS (RMC-6236 / daraxonrasib) — class-agnostic to KRAS allele (valid
  for G12S; G12C-specific sotorasib/adagrasib are NOT applicable)

Seeded NCT watchlist (first run — include all; later runs — status refresh
only, skip those in previously seen list unless status changed):
{seed_list}

Previously seen NCT IDs (skip these unless status changed):
{json.dumps(prev_ncts[:50]) if prev_ncts else "None — first scan, include every seeded NCT"}

First run: {first_run}

Instructions:
1. {"SEED" if first_run else "SCAN"}: call fetch_trial_details for each seeded NCT
   {"on first run" if first_run else "only when refreshing"}; skip already-seen NCTs.
2. Use search_clinical_trials with intervention="olaparib" / "rucaparib" / "ATR
   inhibitor" / "PARP" / "daraxonrasib" to catch new postings.
3. Use search_pubmed for "ATM biallelic colorectal" / "PARPi MSS CRC" /
   "pan-RAS inhibitor colorectal" to surface recent evidence.
4. For each NEW trial, call check_trial_eligibility to confirm no biomarker
   contraindications (anti-EGFR still excluded; checkpoint mono still excluded
   for MSS).
5. For each trial that passes checks, call funnel_propose_trial with:
     nct_id (required), title, rationale (cite DDR variant + geography fit),
     source_agent="ddr_monitor", biomarker_match (e.g. "ATM"->"biallelic"),
     geographic_score (0.0-1.0 from the proximity pass). This is the ONLY
     agent-writable path into the clinical funnel (#395). It handles
     re-surfacing of previously-seen NCTs automatically. Never call
     log_research_decision for trial proposals.
6. Use log_research_decision ONLY for meta decisions (e.g., "skipping N trials
   because pre-seen") — not for individual proposals.
7. Store a briefing summarizing what went to the proposals lane. Be brief.
8. Use set_agent_state to save "ddr_monitor_seen_ncts" with all current NCT IDs.

Output format:
- Proposed (N trials): list with NCT | title | rationale | tier.
- Already-known status changes (if any).
- PubMed highlights (max 3).
- End with "Questions for Oncologist" section.
"""
    try:
        result = await run_autonomous_task(
            prompt,
            max_turns=10,
            task_name="ddr_monitor",
            model=AUTONOMOUS_MODEL,  # Sonnet for reasoning-heavy eligibility decisions
            patient_id=patient_id,
        )
    except Exception as e:
        logger.error("!!! Failed task: ddr_monitor — %s", e)
        raise
    logger.info(
        "<<< Completed task: ddr_monitor (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("ddr_monitor", result, token=token)
    await _set_state(
        f"last_ddr_monitor:{patient_id}",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
        token=token,
    )
    return result


async def run_file_scan(patient_id: str = "q1b") -> dict:
    """Scan oncofiles for new document uploads."""
    token = get_patient_token(patient_id)
    if await _should_skip("file_scan", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: file_scan (patient=%s)", patient_id)
    state = await _get_state(f"last_file_scan:{patient_id}", token=token)
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
        result = await run_autonomous_task(
            prompt,
            max_turns=8,
            task_name="file_scan",
            model=AUTONOMOUS_MODEL_LIGHT,
            patient_id=patient_id,
        )
    except Exception as e:
        logger.error("!!! Failed task: file_scan — %s", e)
        raise
    logger.info(
        "<<< Completed task: file_scan (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("file_scan", result, token=token)
    await _set_state(
        f"last_file_scan:{patient_id}",
        {
            "timestamp": datetime.now(UTC).isoformat(),
        },
        token=token,
    )
    return result


# ── Reporting Tasks ────────────────────────────


async def run_weekly_briefing(patient_id: str = "q1b") -> dict:
    """Compile weekly briefing: research, trials, labs, treatment progress."""
    token = get_patient_token(patient_id)
    if await _should_skip("weekly_briefing", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: weekly_briefing (patient=%s)", patient_id)
    patient = get_patient(patient_id)
    cycle = patient.current_cycle or 2
    milestones = get_milestones_for_cycle(cycle)
    milestone_text = (
        "\n".join(f"- Cycle {m['cycle']}: {m['description']}" for m in milestones)
        or "None upcoming"
    )

    prompt = f"""\
Compile the weekly briefing for physician review.

Current status: {patient.treatment_regimen} cycle {cycle}, current milestones: {milestone_text}

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
        result = await run_autonomous_task(
            prompt, max_turns=12, task_name="weekly_briefing", patient_id=patient_id
        )
    except Exception as e:
        logger.error("!!! Failed task: weekly_briefing — %s", e)
        raise
    logger.info(
        "<<< Completed task: weekly_briefing (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("weekly_briefing", result, token=token)
    await _set_state(
        f"last_weekly_briefing:{patient_id}",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
        token=token,
    )

    # Send WhatsApp summary
    try:
        response_text = result.get("response", "")
        if response_text and not result.get("error"):
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            header = format_whatsapp_header(
                "Týždenný briefing", date_str=today, patient_name=_patient_display_name(patient_id)
            )
            summary = response_text[:1400]
            if len(response_text) > 1400:
                summary += "\n\n... (plná správa na dashboarde)"
            await _send_whatsapp(
                header + summary,
                recipient="caregiver",
                template_key="briefing",
                patient_id=patient_id,
            )
    except Exception as e:
        record_suppressed_error("weekly_briefing", "whatsapp_notify", e)

    return result


async def run_lab_sync(patient_id: str = "q1b") -> dict:
    """Extract lab values from oncofiles documents and store as structured lab data."""
    token = get_patient_token(patient_id)
    if await _should_skip("lab_sync", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: lab_sync (patient=%s)", patient_id)
    prompt = """\
Extract structured lab data from uploaded documents and store as lab values.

Instructions:
1. Search documents for lab results (search "lab", "krvny obraz", "biochemia", "odber")
2. For each document found, use view_document to read its full content
3. Extract numeric lab values: WBC, ANC, PLT, hemoglobin, creatinine,
   ALT, AST, bilirubin, CEA, CA_19_9, ABS_LYMPH
4. Use get_treatment_timeline to check if data already exists for that date
5. For EACH NEW date, you MUST call BOTH tools in the SAME turn:
   a) store_lab_values(document_id=..., lab_date="YYYY-MM-DD", values={...})
   b) add_treatment_event(event_date="YYYY-MM-DD", event_type="lab_result",
      title="Lab results YYYY-MM-DD", notes="...",
      metadata={"WBC": 3.51, "ANC": 1150, "PLT": 269000, "hemoglobin": 118,
                "CEA": 732.9, "CA_19_9": 22294})
6. Store a briefing summarizing what was extracted and stored

CRITICAL: The metadata dict in add_treatment_event MUST contain the SAME numeric
values you pass to store_lab_values. Do NOT omit metadata or pass it as empty —
the dashboard charts read from metadata, not from notes text.
Parameter names must match exactly: WBC, ANC, PLT, hemoglobin,
creatinine, ALT, AST, bilirubin, CEA, CA_19_9, ABS_LYMPH.
"""
    try:
        result = await run_autonomous_task(
            prompt,
            max_turns=8,
            task_name="lab_sync",
            model=AUTONOMOUS_MODEL_LIGHT,
            patient_id=patient_id,
        )
    except Exception as e:
        logger.error("!!! Failed task: lab_sync — %s", e)
        raise
    logger.info(
        "<<< Completed task: lab_sync (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("lab_sync", result, token=token)
    await _set_state(
        f"last_lab_sync:{patient_id}",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
        token=token,
    )

    # Check latest labs for safety alerts and send WhatsApp if breached
    try:
        if not result.get("error"):
            trends = await oncofiles_client.get_lab_trends_data(limit=200, token=token)
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
                    # Normalize units: G/L → /µL (same logic as dashboard_api)
                    anc = vals.get("ABS_NEUT", vals.get("ANC"))
                    if anc is not None and isinstance(anc, (int, float)) and anc < 30:
                        anc = round(anc * 1000)
                    plt = vals.get("PLT")
                    if plt is not None and isinstance(plt, (int, float)) and plt < 1000:
                        plt = round(plt * 1000)
                    alerts: list[str] = []
                    if anc is not None and anc < 1500:
                        alerts.append(f"ANC = {anc} (< 1500) — hold chemo")
                    if plt is not None and plt < 75000:
                        alerts.append(f"PLT = {plt:.0f} (< 75000) — hold chemo")
                    if alerts:
                        # #403 freshness gate — don't fire "lab safety alert"
                        # push for a lab date that is already >7 days old.
                        # The original bug report flagged a 35-day-old ANC
                        # alert re-emitting as "New" on every lab_sync run
                        # because this branch fired purely on latest_date
                        # having ANC<1500, with no age check. The data still
                        # persists and renders on the dashboard; only the
                        # user-facing push is suppressed.
                        if _event_is_stale(latest_date, freshness_days=7):
                            logger.info(
                                "Lab safety alert suppressed for %s (lab_date=%s is stale, %s)",
                                patient_id,
                                latest_date,
                                ", ".join(alerts),
                            )
                        else:
                            # #403 signature dedup — even within the fresh
                            # window, the same (date, ANC, PLT) combo should
                            # only push once per 24h to absorb multiple
                            # scheduled runs of lab_sync landing on the same
                            # data.
                            anc_sig = round(anc) if isinstance(anc, (int, float)) else "na"
                            plt_sig = round(plt) if isinstance(plt, (int, float)) else "na"
                            signature = f"lab_alert:{latest_date}:ANC={anc_sig}:PLT={plt_sig}"
                            if await _already_notified(patient_id, signature, token=token):
                                logger.info(
                                    "Lab safety alert suppressed for %s "
                                    "(signature %s already notified within TTL)",
                                    patient_id,
                                    signature,
                                )
                            else:
                                header = format_whatsapp_header(
                                    f"Lab Safety Alert ({latest_date})",
                                    date_str=latest_date,
                                    patient_name=_patient_display_name(patient_id),
                                )
                                body = "\n".join(f"- {a}" for a in alerts)
                                push_result = await _send_whatsapp(
                                    header + body,
                                    recipient="caregiver",
                                    template_key="lab_alert",
                                    patient_id=patient_id,
                                )
                                # Only mark the signature notified if the push
                                # actually went out — policy/paused suppressions
                                # shouldn't block a later legitimate push once
                                # the patient becomes active again.
                                if isinstance(push_result, dict) and not push_result.get(
                                    "suppressed"
                                ):
                                    await _mark_notified(patient_id, signature, token=token)
    except Exception as e:
        record_suppressed_error("lab_sync", "whatsapp_safety_alert", e)

    return result


async def run_toxicity_extraction(patient_id: str = "q1b") -> dict:
    """Extract toxicity grades from doctor visit notes/reports."""
    token = get_patient_token(patient_id)
    if await _should_skip("toxicity_extraction", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: toxicity_extraction (patient=%s)", patient_id)
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
        result = await run_autonomous_task(
            prompt,
            max_turns=8,
            task_name="toxicity_extraction",
            model=AUTONOMOUS_MODEL_LIGHT,
            patient_id=patient_id,
        )
    except Exception as e:
        logger.error("!!! Failed task: toxicity_extraction — %s", e)
        raise
    logger.info(
        "<<< Completed task: toxicity_extraction (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("toxicity_extraction", result, token=token)
    await _set_state(
        f"last_toxicity_extraction:{patient_id}",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
        token=token,
    )
    return result


async def run_weight_extraction(patient_id: str = "q1b") -> dict:
    """Extract weight/BMI from doctor visit notes and store as weight_measurement events."""
    token = get_patient_token(patient_id)
    if await _should_skip("weight_extraction", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: weight_extraction (patient=%s)", patient_id)
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
        result = await run_autonomous_task(
            prompt,
            max_turns=8,
            task_name="weight_extraction",
            model=AUTONOMOUS_MODEL_LIGHT,
            patient_id=patient_id,
        )
    except Exception as e:
        logger.error("!!! Failed task: weight_extraction — %s", e)
        raise
    logger.info(
        "<<< Completed task: weight_extraction (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("weight_extraction", result, token=token)
    await _set_state(
        f"last_weight_extraction:{patient_id}",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
        token=token,
    )
    return result


async def _resolve_file_id(document_id: int, patient_id: str = "q1b") -> str | None:
    """Resolve a document_id to its file_id via oncofiles."""
    try:
        token = get_patient_token(patient_id)
        doc = await oncofiles_client.get_document(document_id, token=token)
        return doc.get("file_id") if isinstance(doc, dict) else None
    except Exception as e:
        logger.warning("Could not resolve file_id for doc %d: %s", document_id, e)
        return None


async def _run_single_doc_task(
    task_name: str,
    document_id: int,
    prompt: str,
    patient_id: str = "q1b",
    *,
    token: str | None = None,
    model: str | None = None,
) -> dict:
    """Run a single-document autonomous task with standard logging."""
    logger.info(">>> Starting task: %s (doc %d, patient=%s)", task_name, document_id, patient_id)
    try:
        result = await run_autonomous_task(
            prompt,
            max_turns=6,
            task_name=task_name,
            model=model or AUTONOMOUS_MODEL_LIGHT,
            patient_id=patient_id,
        )
    except Exception as e:
        logger.error("!!! Failed task: %s (doc %d) — %s", task_name, document_id, e)
        raise
    logger.info(
        "<<< Completed task: %s (doc %d, cost=$%.4f, tools=%d)",
        task_name,
        document_id,
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    return result


async def run_file_scan_single(
    document_id: int, *, patient_id: str = "q1b", file_id: str | None = None
) -> dict:
    """Classify a single document by ID (no broad search)."""
    if not file_id:
        file_id = await _resolve_file_id(document_id, patient_id)
    view_arg = file_id or str(document_id)
    return await _run_single_doc_task(
        "file_scan_single",
        document_id,
        f"""\
Read the document using view_document(file_id="{view_arg}"), then classify it.

IMPORTANT: The view_document tool parameter is called "file_id" (a string).
Call it exactly as: view_document(file_id="{view_arg}")

Instructions:
1. Call view_document with file_id="{view_arg}" to read the document
2. Classify the document type: lab_report, visit_note, discharge_summary,
   pathology, genetics, imaging, or other
3. For pathology/genetics docs: check if biomarker data matches known profile
4. For lab docs: check values against safety thresholds
5. Flag any new information or discrepancies
6. Report the classification and key findings

This is a single-document scan triggered by a new upload webhook.
""",
        patient_id=patient_id,
    )


async def run_lab_sync_single(
    document_id: int, *, patient_id: str = "q1b", file_id: str | None = None
) -> dict:
    """Extract lab values from a single document by ID.

    Triggered by document_pipeline for lab_report PLUS visit_note /
    discharge_summary / chemo_sheet documents (#426) — Slovak oncology
    practice routinely quotes pre-visit bloods inline on consultation
    notes and chemo administration forms rather than as standalone lab
    sheets. The prompt tolerates the zero-labs case cleanly so we don't
    hallucinate values when a document has no lab content.
    """
    view_arg = file_id or str(document_id)
    return await _run_single_doc_task(
        "lab_sync_single",
        document_id,
        f"""\
Scan this document (oncofiles ID {document_id}) for any structured lab values.

IMPORTANT: The view_document tool parameter is called "file_id" (a string).
Call it exactly as: view_document(file_id="{view_arg}")

Context: this document may be a standalone lab report, OR a consultation
note / chemo administration form / discharge summary that quotes lab
values inline. Your job is to find any numeric lab values present,
regardless of the document's primary category.

Instructions:
1. Call view_document(file_id="{view_arg}") to read the document.
2. Scan for numeric lab values: WBC, ANC, PLT, hemoglobin, creatinine,
   ALT, AST, bilirubin, CEA, CA_19_9, ABS_LYMPH. Slovak labels to watch
   for: "neutrofily" (ANC), "leukocyty" (WBC), "trombocyty" (PLT),
   "hemoglobin" (HGB), "kreatinín" (creatinine), "bilirubín" (bilirubin).
3. **Zero-labs exit**: if the document contains no numeric lab values,
   report "no lab values found" and EXIT — do not fabricate, do not guess.
4. If values found, extract the measurement date. The measurement date
   may differ from the document date (a consultation dated 2026-04-17
   may quote bloods drawn 2026-04-16) — pull the measurement date
   explicitly if shown; else use the document date with a note.
5. Use get_treatment_timeline to check if data already exists for that date.
6. For NEW data only, call store_lab_values(document_id={document_id},
   lab_date="YYYY-MM-DD", values={{...}}) AND add_treatment_event
   (event_type="lab_result", event_date="YYYY-MM-DD", metadata with the
   same numeric values).
7. Report what was extracted, the source document category, and whether
   values were stored or skipped as duplicate.

IMPORTANT: Parameter names must match exactly: WBC, ANC, PLT, hemoglobin,
creatinine, ALT, AST, bilirubin, CEA, CA_19_9, ABS_LYMPH.
""",
        patient_id=patient_id,
    )


async def run_toxicity_extraction_single(
    document_id: int, *, patient_id: str = "q1b", file_id: str | None = None
) -> dict:
    """Extract toxicity grades from a single document by ID."""
    view_arg = file_id or str(document_id)
    return await _run_single_doc_task(
        "toxicity_extraction_single",
        document_id,
        f"""\
Extract NCI-CTCAE toxicity assessments from this document (oncofiles ID {document_id}).

IMPORTANT: The view_document tool parameter is called "file_id" (a string).
Call it exactly as: view_document(file_id="{view_arg}")

Instructions:
1. Call view_document(file_id="{view_arg}") to read the document
2. Extract toxicity grades for:
   - Peripheral neuropathy, diarrhea, mucositis, fatigue, HFS, nausea/vomiting
3. Note ECOG and weight if mentioned
4. Report extracted toxicity data with dates

This is a single-document extraction triggered by a new upload webhook.
""",
        patient_id=patient_id,
    )


async def run_weight_extraction_single(
    document_id: int, *, patient_id: str = "q1b", file_id: str | None = None
) -> dict:
    """Extract weight/BMI from a single document by ID."""
    view_arg = file_id or str(document_id)
    return await _run_single_doc_task(
        "weight_extraction_single",
        document_id,
        f"""\
Extract weight/BMI data from this document (oncofiles ID {document_id}).

IMPORTANT: The view_document tool parameter is called "file_id" (a string).
Call it exactly as: view_document(file_id="{view_arg}")

Instructions:
1. Call view_document(file_id="{view_arg}") to read the document
2. Extract weight in kg and BMI if mentioned
3. Extract date of measurement
4. Check if a weight_measurement event already exists for that date
5. If not, store as a treatment event with event_type="weight_measurement"
6. Report what was extracted

This is a single-document extraction triggered by a new upload webhook.
""",
    )


async def run_dose_extraction_single(
    document_id: int, *, patient_id: str = "q1b", file_id: str | None = None
) -> dict:
    """Extract chemotherapy administration data from a single chemo sheet."""
    from .patient_context import get_patient, is_general_health_patient

    pt = get_patient(patient_id)
    if is_general_health_patient(pt):
        return {"skipped": True, "reason": "non_oncology_patient"}

    view_arg = file_id or str(document_id)
    return await _run_single_doc_task(
        "dose_extraction_single",
        document_id,
        f"""\
Extract structured chemotherapy administration data from this document (oncofiles ID {document_id}).

IMPORTANT: The view_document tool parameter is called "file_id" (a string).
Call it exactly as: view_document(file_id="{view_arg}")

Instructions:
1. Call view_document(file_id="{view_arg}") to read the document
2. Identify this as a chemo sheet / chemotherapy administration record
3. Extract the following fields:
   - Cycle number (číslo cyklu)
   - Treatment regimen name (e.g. mFOLFOX6, FOLFOX, CAPOX)
   - Infusion/administration date
   - Body surface area (BSA in m²)
   - For EACH drug listed on the sheet:
     * Drug name (oxaliplatin, leucovorin, fluorouracil_bolus, fluorouracil_infusion)
     * Prescribed dose in mg/m² (if shown)
     * Absolute dose in mg (dose actually administered)
     * Any dose reduction percentage (if noted)
     * Reason for dose reduction (neuropathy, neutropenia, etc.)
   - Administration institution/site name
4. Use get_treatment_timeline to check if a "chemotherapy" event already exists
   for this cycle number and date — skip if duplicate found
5. If NEW data, call add_treatment_event with:
   - event_type: "chemotherapy"
   - event_date: the infusion date (YYYY-MM-DD format)
   - title: "Chemotherapy Cycle {{cycle}} — {{regimen}}"
   - notes: brief human-readable summary of doses administered
   - metadata: JSON with cycle, regimen, drugs (list of name/dose_mg_m2/dose_mg_absolute/
     dose_reduction_pct/reduction_reason), bsa_m2, infusion_date, document_id
6. Report what was extracted and whether it was stored or skipped as duplicate

Drug name mapping for Slovak documents:
- "Oxaliplatina"/"Oxaliplatin" → "oxaliplatin"
- "Leukovorín"/"Kyselina listová" → "leucovorin"
- "5-FU bolus"/"5-Fluorouracil bolus" → "fluorouracil_bolus"
- "5-FU kontinuálna infúzia"/"5-FU pump" → "fluorouracil_infusion"
- If dose percentage reduction noted (e.g. "90% dávka"), dose_reduction_pct = 10
- BSA (telesný povrch) typically 1.4–2.5 m²
- If any field is illegible or missing, set to null rather than guessing

Handwritten document handling:
- Documents may be handwritten or partially handwritten (common in Slovak hospitals)
- Common OCR ambiguities in handwritten text: 1↔7, 5↔6, 0↔O, 3↔8, comma↔period
- If a dose value seems implausible (e.g. oxaliplatin >200 mg/m² or <20 mg/m²), flag as uncertain
- Report confidence for each value: "high" (printed/clear),
  "medium" (readable handwriting), "low" (partially illegible)
- Include a "ocr_notes" field in metadata listing any values you're uncertain about
""",
        patient_id=patient_id,
        model=AUTONOMOUS_MODEL,
    )


async def run_oncopanel_extraction_single(
    document_id: int, *, patient_id: str = "q1b", file_id: str | None = None
) -> dict:
    """Extract structured oncopanel (variants + CNVs + MSI/MMR/TMB) from a
    pathology or genetics document (#398 Phase 3b).

    Honors the "AI proposes, humans dispose" principle from #395: extracted
    panel is persisted as a PENDING proposal under
    `pending_oncopanel:{patient_id}:{document_id}` in oncofiles agent_state.
    It is NOT auto-merged into `PatientProfile.oncopanel_history` — that
    requires physician verification. The dashboard's MUDr. Mináriková review
    surface (#395 + #399) picks up these pending entries.

    Skipped for non-oncology patients (general-health Z00.0 etc.) since they
    don't have an oncopanel clinical context.

    Uses Sonnet (not Haiku) — structured variant extraction from handwritten
    OR OCR-ambiguous Slovak pathology reports benefits from stronger
    reasoning. Cost per run is bounded by AUTONOMOUS_COST_LIMIT.
    """
    from .patient_context import get_patient, is_general_health_patient

    pt = get_patient(patient_id)
    if is_general_health_patient(pt):
        return {"skipped": True, "reason": "non_oncology_patient"}

    view_arg = file_id or str(document_id)
    result = await _run_single_doc_task(
        "oncopanel_extraction_single",
        document_id,
        f"""\
Extract a structured oncopanel (somatic NGS report) from this pathology or
genetics document (oncofiles ID {document_id}).

IMPORTANT: The view_document tool parameter is called "file_id" (a string).
Call it exactly as: view_document(file_id="{view_arg}")

Instructions:
1. Call view_document(file_id="{view_arg}") to read the document
2. Determine whether this is a somatic oncopanel / NGS / molecular pathology
   report. If it is NOT (e.g. it's a routine H&E histology without any
   variant table), report "not an oncopanel report" and EXIT — do not
   fabricate variants.
3. If it IS an oncopanel, extract structured data. Return a JSON block with
   these top-level fields:
   - panel_id: lab+date identifier (e.g. "q1b_oncopanel_2026-04-18")
   - sample_date: YYYY-MM-DD or null
   - report_date: YYYY-MM-DD (required)
   - lab: laboratory name (e.g. "OUSA — Ústav sv. Alžbety")
   - methodology: NGS panel name (e.g. "TruSight-500", "OncoDNA OncoDEEP")
   - sample_type: one of "tumor_tissue", "ctDNA", "germline", "mixed"
   - variants: array of variant objects
   - cnvs: array of copy-number variant objects
   - msi_status: one of "MSS", "MSI-L", "MSI-H", "unknown"
   - mmr_status: one of "pMMR", "dMMR", "unknown"
   - tmb_score: numeric Mut/Mb or null
   - tmb_category: one of "low", "intermediate", "high", "unknown"
   - source_document_id: "{document_id}"

4. For each variant, extract:
   - gene: HUGO symbol uppercase (e.g. "KRAS", "ATM", "TP53")
   - ref_seq: RefSeq transcript (e.g. "NM_033360.4")
   - hgvs_cdna: coding change (e.g. "c.34G>A")
   - hgvs_protein: protein change with parens (e.g. "p.(Gly12Ser)")
   - protein_short: short form (e.g. "G12S", "L2760Pfs*9")
   - vaf: variant allele frequency 0.0-1.0 (e.g. 0.1281 for 12.81%)
   - variant_type: one of "SNV", "indel", "splice", "frameshift", "CNV",
     "fusion", "other"
   - tier: AMP/ASCO/CAP tier like "IA", "IB", "IIC", "IID", "III"
   - classification: "somatic", "germline", or "unknown"
   - significance: "pathogenic", "likely_pathogenic", "vus",
     "likely_benign", "benign", or "unknown"
   - source_document_id: "{document_id}"
   - source_page: page number if shown, else null
   - notes: any relevant annotation from the report
5. For each CNV, extract gene, alteration (amplification/deletion/loss/
   gain), copies (int or null).
6. Slovak terms: "patogénna" → "pathogenic"; "pravdepodobne patogénna" →
   "likely_pathogenic"; "VUS" stays "vus"; "nejasný význam" → "vus".
7. Tier mapping from Slovak: "I.A/I.B/II.C/II.D/III" → "IA/IB/IIC/IID/III"

Output format: wrap the structured JSON in a ```json fenced code block so
the agent runner can parse it cleanly. If the report is unreadable or
partial, include a "extraction_quality" field ("high"/"medium"/"low") and
a "notes" field explaining gaps.

This is a PROPOSAL only. It will NOT be auto-merged into the patient
profile. A physician reviews it before it becomes clinical truth.
""",
        patient_id=patient_id,
        model=AUTONOMOUS_MODEL,  # Sonnet — handwritten OCR / tier reasoning
    )

    # Persist the extracted panel as a pending proposal. Physician review via
    # #395 audit path promotes it into PatientProfile.oncopanel_history.
    response_text = result.get("response", "")
    if response_text and not result.get("error"):
        token = get_patient_token(patient_id)
        try:
            await _set_state(
                f"pending_oncopanel:{patient_id}:{document_id}",
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "document_id": document_id,
                    "patient_id": patient_id,
                    "raw_response": response_text[:50_000],  # truncate paranoia
                    "status": "pending_physician_review",
                    "extraction_cost_usd": result.get("cost", 0),
                    "extraction_model": result.get("model", "sonnet"),
                },
                token=token,
            )
        except Exception as e:
            record_suppressed_error("oncopanel_extraction_single", "persist_pending", e)

    return result


async def run_document_pipeline(
    document_id: int, metadata: dict | None = None, *, patient_id: str = "q1b"
) -> dict:
    """Process a single document through the data pipeline.

    Steps:
    1. Cost cap check (via run_autonomous_task)
    2. Dedup check via agent_state
    3. file_scan_single → classify document type
    4. Dispatch downstream based on classification
    5. Log combined pipeline result for dashboard observability
    """
    metadata = metadata or {}
    token = get_patient_token(patient_id)
    logger.info(">>> Starting document_pipeline for doc %d (meta=%s)", document_id, metadata)
    start = time.monotonic()

    # Dedup: check if we already processed this document
    state_key = f"pipeline:{document_id}"
    existing = await _get_state(state_key, token=token)
    if _extract_timestamp(existing):
        logger.info("Skipping document_pipeline for doc %d: already processed", document_id)
        return {"skipped": True, "reason": "already_processed", "document_id": document_id}

    steps: list[dict] = []
    total_cost = 0.0
    pipeline_error = None

    # Step 1: file_scan_single — classify the document
    try:
        scan_result = await run_file_scan_single(document_id, patient_id=patient_id)
        scan_cost = scan_result.get("cost", 0)
        total_cost += scan_cost
        steps.append(
            {
                "step": "file_scan",
                "cost": scan_cost,
                "error": scan_result.get("error"),
            }
        )
        await _log_task("file_scan_single", scan_result, token=token)
    except Exception as e:
        pipeline_error = f"file_scan_single failed: {e}"
        logger.error("document_pipeline: %s", pipeline_error)
        steps.append({"step": "file_scan", "error": str(e)})
        # If scan fails, we can't classify → skip downstream
        scan_result = {"response": "", "error": str(e)}

    # Step 2: Classify document type from scan response
    doc_type = _classify_doc_type(scan_result.get("response", ""), metadata)
    logger.info("document_pipeline doc %d classified as: %s", document_id, doc_type)

    # Resolve file_id for downstream agents (view_document MCP tool needs file_id, not doc int)
    file_id = await _resolve_file_id(document_id, patient_id)

    # Step 3: Dispatch downstream agents based on classification. #426:
    # lab_sync_single also runs for visit_note / discharge_summary /
    # chemo_sheet because Slovak oncology docs routinely quote inline
    # bloods (e.g. "WBC 12.11, neutr. 77.9%") on consultation + chemo
    # administration forms rather than as standalone lab sheets. The
    # prompt tolerates zero-lab documents without hallucinating.
    if not pipeline_error:
        downstream_tasks = []
        lab_extraction_doc_types = (
            "lab_report",
            "visit_note",
            "discharge_summary",
            "chemo_sheet",
        )
        if doc_type in lab_extraction_doc_types:
            downstream_tasks.append(
                (
                    "lab_sync",
                    lambda did: run_lab_sync_single(did, patient_id=patient_id, file_id=file_id),
                )
            )
        if doc_type in ("visit_note", "discharge_summary"):
            downstream_tasks.append(
                (
                    "toxicity_extraction",
                    lambda did: run_toxicity_extraction_single(
                        did, patient_id=patient_id, file_id=file_id
                    ),
                )
            )
            downstream_tasks.append(
                (
                    "weight_extraction",
                    lambda did: run_weight_extraction_single(
                        did, patient_id=patient_id, file_id=file_id
                    ),
                )
            )
        if doc_type == "chemo_sheet":
            downstream_tasks.append(
                (
                    "dose_extraction",
                    lambda did: run_dose_extraction_single(
                        did, patient_id=patient_id, file_id=file_id
                    ),
                )
            )
        # #398 Phase 3b: pathology / genetics docs → structured oncopanel
        # extraction → pending_oncopanel:* agent_state for physician review.
        # file_scan does a coarse biomarker sanity-check; this step pulls the
        # full variant / CNV / MSI / MMR / TMB structure for the research
        # cockpit (#399) and eligibility helpers (#398 Phase 1+2).
        if doc_type in ("pathology", "genetics"):
            downstream_tasks.append(
                (
                    "oncopanel_extraction",
                    lambda did: run_oncopanel_extraction_single(
                        did, patient_id=patient_id, file_id=file_id
                    ),
                )
            )
        # imaging/other: no downstream processing needed

        for step_name, step_fn in downstream_tasks:
            try:
                step_result = await step_fn(document_id)
                step_cost = step_result.get("cost", 0)
                total_cost += step_cost
                steps.append(
                    {
                        "step": step_name,
                        "cost": step_cost,
                        "error": step_result.get("error"),
                    }
                )
                await _log_task(f"{step_name}_single", step_result, token=token)
            except Exception as e:
                logger.error("document_pipeline step %s failed: %s", step_name, e)
                steps.append({"step": step_name, "error": str(e)})

    duration_ms = int((time.monotonic() - start) * 1000)

    # Build combined pipeline result
    combined = {
        "task_name": "document_pipeline",
        "document_id": document_id,
        "doc_type": doc_type,
        "steps": steps,
        "cost": total_cost,
        "duration_ms": duration_ms,
        "error": pipeline_error,
        "metadata": metadata,
        "model": "haiku",
        "prompt": f"[Document pipeline for doc {document_id}]",
        "response": (
            f"Processed document {document_id} as {doc_type}. "
            f"Steps: {', '.join(s['step'] for s in steps)}. "
            f"Total cost: ${total_cost:.4f}."
        ),
        "tool_calls": [],
        "thinking": [],
        "input_tokens": 0,
        "output_tokens": 0,
        "turns": len(steps),
        "started_at": datetime.now(UTC).isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
    }
    await _log_task("document_pipeline", combined, token=token)

    # Store dedup state
    await _set_state(
        state_key,
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "doc_type": doc_type,
            "steps": [s["step"] for s in steps],
            "cost": total_cost,
        },
        token=token,
    )

    # WhatsApp notification for safety-critical findings
    if not pipeline_error and doc_type in ("lab_report", "pathology", "genetics", "chemo_sheet"):
        try:
            scan_response = scan_result.get("response", "")
            _alert_kw = ("safety", "alert", "hold", "critical", "dose reduction", "dávka")
            if any(kw in scan_response.lower() for kw in _alert_kw):
                today = datetime.now(UTC).strftime("%Y-%m-%d")
                header = format_whatsapp_header(
                    "Nový dokument — bezpečnostné upozornenie",
                    date_str=today,
                    patient_name=_patient_display_name(patient_id),
                )
                await _send_whatsapp(
                    header
                    + f"Dokument {document_id} ({doc_type}) — nájdené bezpečnostné upozornenie.\n"
                    f"Pozrite dashboard pre detaily.",
                    recipient="caregiver",
                    template_key="lab_alert",
                    patient_id=patient_id,
                )
        except Exception as e:
            record_suppressed_error("document_pipeline", "whatsapp_notify", e)

    logger.info(
        "<<< Completed document_pipeline for doc %d (type=%s, cost=$%.4f, %dms)",
        document_id,
        doc_type,
        total_cost,
        duration_ms,
    )
    return combined


async def run_document_pipeline_drain(patient_id: str = "q1b") -> dict:
    """Drain doc uploads queued by api_document_webhook outside CEE-night window.

    Runs once daily at 02:00 UTC. The webhook enqueues under agent_state key
    `pending_docs_queue`; this task resets the queue then processes each entry
    via run_document_pipeline (which has its own dedup guard).
    """
    patient = get_patient(patient_id)
    if patient.paused:
        return {"drained": 0, "patient_id": patient_id, "skipped": "patient_paused"}

    token = get_patient_token(patient_id)
    queue_key = "pending_docs_queue"
    state = await _get_state(queue_key, token=token)
    # State may arrive flat, nested under "value", or as a raw string.
    docs: list[dict] = []
    if isinstance(state, dict):
        if isinstance(state.get("docs"), list):
            docs = state["docs"]
        else:
            raw = state.get("value")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    raw = None
            if isinstance(raw, dict) and isinstance(raw.get("docs"), list):
                docs = raw["docs"]

    if not docs:
        return {"drained": 0, "patient_id": patient_id}

    # Reset queue BEFORE processing so an error mid-drain doesn't re-trigger
    # identical work next night (dedup keys still guard against reruns).
    await _set_state(queue_key, {"docs": []}, token=token)

    results: list[dict] = []
    total_cost = 0.0
    for entry in docs:
        doc_id = entry.get("doc_id") if isinstance(entry, dict) else None
        if not isinstance(doc_id, int) or doc_id <= 0:
            continue
        metadata = entry.get("metadata") if isinstance(entry, dict) else None
        try:
            r = await run_document_pipeline(doc_id, metadata, patient_id=patient_id)
            cost = r.get("cost", 0) or 0
            total_cost += cost
            results.append({"doc_id": doc_id, "ok": True, "cost": cost})
        except Exception as e:
            record_suppressed_error("document_pipeline_drain", f"doc_{doc_id}", e)
            results.append({"doc_id": doc_id, "ok": False, "error": str(e)})

    await _log_task(
        "document_pipeline_drain",
        {
            "cost": total_cost,
            "tool_calls": [{"doc_id": r["doc_id"]} for r in results],
            "response": json.dumps(results, ensure_ascii=False),
            "model": AUTONOMOUS_MODEL_LIGHT,
            "started_at": datetime.now(UTC).isoformat(),
        },
        token=token,
    )
    logger.info(
        "document_pipeline_drain: patient=%s drained=%d cost=$%.4f",
        patient_id,
        len(results),
        total_cost,
    )
    return {"drained": len(results), "patient_id": patient_id, "cost": total_cost}


def _classify_doc_type(response_text: str, metadata: dict) -> str:
    """Classify document type from file_scan response and webhook metadata.

    Returns one of: lab_report, visit_note, discharge_summary, pathology,
    genetics, imaging, chemo_sheet, or other.
    """
    # Check webhook metadata first (oncofiles may provide category)
    category = (metadata.get("category") or "").lower()
    category_map = {
        "lab": "lab_report",
        "labs": "lab_report",
        "pathology": "pathology",
        "genetics": "genetics",
        "imaging": "imaging",
        "chemo_sheet": "chemo_sheet",
        "chemo": "chemo_sheet",
    }
    if category in category_map:
        return category_map[category]

    # Fall back to parsing the AI response
    text = response_text.lower()
    if any(kw in text for kw in ("lab report", "lab_report", "krvný obraz", "biochemia", "odber")):
        return "lab_report"
    if any(kw in text for kw in ("visit note", "visit_note", "vizita", "konzultacia", "kontrola")):
        return "visit_note"
    if any(kw in text for kw in ("discharge", "prepustenie")):
        return "discharge_summary"
    if "pathology" in text or "patológia" in text:
        return "pathology"
    if "genetics" in text or "genetik" in text:
        return "genetics"
    if "imaging" in text or "ct scan" in text or "mri" in text:
        return "imaging"
    _chemo_kw = ("chemo_sheet", "chemo sheet", "chemoterapia", "oxaliplatina", "mfolfox", "folfox")
    if any(kw in text for kw in _chemo_kw):
        return "chemo_sheet"
    return "other"


async def run_family_update(patient_id: str = "q1b") -> dict:
    """Generate weekly family update in Slovak from current clinical data."""
    token = get_patient_token(patient_id)
    if await _should_skip("family_update", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: family_update (patient=%s)", patient_id)
    patient = get_patient(patient_id)
    cycle = patient.current_cycle or 2
    prompt = f"""\
Napíš týždennú správu pre rodinu pacientky v slovenčine.

Pokyny:
1. Získaj najnovšie laboratórne výsledky (search "lab", "krvny obraz")
2. Získaj najnovšie údaje o toxicite
3. Zhrň aktuálny stav liečby (cyklus {cycle}, {patient.treatment_regimen})
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
        result = await run_autonomous_task(
            prompt, max_turns=10, task_name="family_update", patient_id=patient_id
        )
    except Exception as e:
        logger.error("!!! Failed task: family_update — %s", e)
        raise
    logger.info(
        "<<< Completed task: family_update (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("family_update", result, token=token)
    await _set_state(
        f"last_family_update:{patient_id}",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
        token=token,
    )

    # Send family update via WhatsApp (already in Slovak)
    try:
        response_text = result.get("response", "")
        if response_text and not result.get("error"):
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            header = format_whatsapp_header(
                "Týždenná správa pre rodinu",
                date_str=today,
                patient_name=_patient_display_name(patient_id),
            )
            summary = response_text[:1400]
            if len(response_text) > 1400:
                summary += "\n\n... (plná správa na dashboarde)"
            await _send_whatsapp(
                header + summary,
                recipient="caregiver",
                template_key="family_update",
                patient_id=patient_id,
            )
    except Exception as e:
        record_suppressed_error("family_update", "whatsapp_notify", e)

    return result


async def run_medication_adherence_check(patient_id: str = "q1b") -> dict:
    """Check if today's medication adherence was logged. Flag missing critical meds."""
    token = get_patient_token(patient_id)
    if await _should_skip("medication_adherence_check", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: medication_adherence_check (patient=%s)", patient_id)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    prompt = f"""\
Check medication adherence for today ({today}).

Instructions:
1. Use get_treatment_timeline to find today's medication_adherence events
2. If no adherence logged for today, create a reminder briefing
3. Specifically flag any critical medication non-adherence (check patient's active therapies)
4. Store a briefing noting adherence status

This is a safety check: non-compliance with critical medications is dangerous.
"""
    try:
        result = await run_autonomous_task(
            prompt,
            max_turns=6,
            task_name="medication_adherence_check",
            model=AUTONOMOUS_MODEL_LIGHT,
            patient_id=patient_id,
        )
    except Exception as e:
        logger.error("!!! Failed task: medication_adherence_check — %s", e)
        raise
    logger.info(
        "<<< Completed task: medication_adherence_check (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("medication_adherence_check", result, token=token)
    await _set_state(
        f"last_medication_adherence_check:{patient_id}",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
        token=token,
    )

    # Send WhatsApp notification
    try:
        response_text = result.get("response", "")
        if response_text and not result.get("error"):
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            header = format_whatsapp_header(
                "Kontrola liekov", date_str=today, patient_name=_patient_display_name(patient_id)
            )
            await _send_whatsapp(
                header + response_text[:1400],
                recipient="caregiver",
                template_key="briefing",
                patient_id=patient_id,
            )
    except Exception as e:
        record_suppressed_error("medication_adherence_check", "whatsapp_notify", e)

    return result


async def run_mtb_preparation(patient_id: str = "q1b") -> dict:
    """Prepare tumor board (MTB) presentation summary."""
    token = get_patient_token(patient_id)
    if await _should_skip("mtb_preparation", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: mtb_preparation (patient=%s)", patient_id)
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
        result = await run_autonomous_task(
            prompt, max_turns=10, task_name="mtb_preparation", patient_id=patient_id
        )
    except Exception as e:
        logger.error("!!! Failed task: mtb_preparation — %s", e)
        raise
    logger.info(
        "<<< Completed task: mtb_preparation (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("mtb_preparation", result, token=token)
    await _set_state(
        f"last_mtb_preparation:{patient_id}",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
        token=token,
    )
    return result


async def _send_whatsapp(
    msg: str,
    recipient: str | None = None,
    template_key: str | None = None,
    template_vars: dict[str, str] | None = None,
    *,
    patient_id: str | None = None,
) -> dict:
    """Send a WhatsApp message via dashboard internal endpoint.

    Args:
        msg: Message body (used for free-form within 24h session window).
        recipient: Optional recipient key (logged for audit).
        template_key: Template name for out-of-window messages (e.g. 'lab_alert').
        template_vars: Variables to substitute into the template.
        patient_id: When set, the patient's `notification_policy` gates delivery.
            `silent` policy → skip send, log reason. `admin` or `patient+admin` →
            proceed. None = system-level alert (health_monitor, daily_cost) which
            always reaches admin. Default for newly-onboarded patients is
            `silent` so parity/read-only patients don't spam the admin inbox
            with agent-run push (#391).
    """
    # #403 defense-in-depth paused gate. The scheduler (#389) and webhook
    # (#404) already skip agent runs for paused patients, but manual triggers
    # (/api/trigger-agent, direct run_* calls from tests or one-offs) bypass
    # those gates. Checking `patient.paused` here guarantees NO push lands on
    # the admin inbox for a paused patient regardless of call path. The agent
    # run itself can still execute — only the push is suppressed.
    if patient_id:
        try:
            patient = get_patient(patient_id)
            if getattr(patient, "paused", False):
                logger.info(
                    "WA push suppressed for patient=%s (paused=True, recipient=%s)",
                    patient_id,
                    recipient,
                )
                return {"ok": True, "sent": 0, "suppressed": "patient:paused"}
        except KeyError:
            pass  # unknown patient_id — fall through to policy check

    # #391 gate — suppress push for patients whose notification policy says so.
    # The agent run itself still executes and its data still persists to
    # oncofiles; only the push is suppressed. Log the skip so it's visible in
    # the dashboard agent-runs view.
    if patient_id:
        try:
            patient = get_patient(patient_id)
            policy = getattr(patient, "notification_policy", "silent")
            if policy == "silent":
                logger.info(
                    "WA push suppressed for patient=%s (policy=silent, recipient=%s)",
                    patient_id,
                    recipient,
                )
                return {"ok": True, "sent": 0, "suppressed": "policy:silent"}
        except KeyError:
            logger.warning(
                "WA push proceeding for unknown patient_id=%s (no policy lookup)",
                patient_id,
            )

    import httpx

    from .config import DASHBOARD_API_KEY

    dashboard_url = "https://dashboard.oncoteam.cloud"
    payload: dict = {"message": msg}
    if recipient:
        payload["recipient"] = recipient
    if template_key:
        payload["template_key"] = template_key
    if template_vars:
        payload["template_vars"] = template_vars
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{dashboard_url}/api/internal/whatsapp-notify",
            json=payload,
            headers={"Authorization": f"Bearer {DASHBOARD_API_KEY}"},
        )
        resp.raise_for_status()
        return resp.json()


async def run_self_improvement(patient_id: str = "q1b") -> dict:
    """Analyze recent conversations and activity to suggest improvements."""
    token = get_patient_token(patient_id)
    if await _should_skip("self_improvement", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: self_improvement (patient=%s)", patient_id)
    prompt = """\
Analyze recent oncoteam activity and conversations to identify improvement opportunities.

Instructions:
1. Search for recent conversation entries (search "session", "briefing", "error")
2. Search for recent activity log entries to find error patterns
3. Look for:
   - Frequently occurring errors or suppressed errors
   - Data gaps (parameters with no values, missing documents)
   - Repeated queries that could be automated
   - Tool calls that consistently fail or timeout
4. For each finding, suggest a concrete improvement:
   - New autonomous task or modified schedule
   - New dashboard feature or alert
   - Data quality fix needed
5. Store findings as a briefing with actionable recommendations
6. If any finding is critical (patient safety), flag it prominently

Focus on patterns, not individual events. Be specific and actionable.
"""
    try:
        result = await run_autonomous_task(
            prompt,
            max_turns=8,
            task_name="self_improvement",
            model=AUTONOMOUS_MODEL_LIGHT,
            patient_id=patient_id,
        )
    except Exception as e:
        logger.error("!!! Failed task: self_improvement — %s", e)
        raise
    logger.info(
        "<<< Completed task: self_improvement (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("self_improvement", result, token=token)
    await _set_state(
        f"last_self_improvement:{patient_id}",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
        token=token,
    )
    return result


async def run_protocol_review(patient_id: str = "q1b") -> dict:
    """Review clinical protocol against latest evidence from oncofiles research."""
    token = get_patient_token(patient_id)
    if await _should_skip("protocol_review", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: protocol_review (patient=%s)", patient_id)
    prompt = """\
Review the current clinical protocol against latest evidence stored in oncofiles.

Instructions:
1. Search documents for recent ESMO, NCCN guidelines and research entries
   (search "ESMO", "NCCN", "guideline", "protocol", "recommendation")
2. Compare key thresholds against current protocol:
   - ANC threshold for chemo hold (current: 1500/µL)
   - PLT threshold for chemo hold (current: 75000/µL)
   - Oxaliplatin cumulative dose thresholds (current: 850 mg/m²)
   - Neuropathy dose modification rules
   - 2nd line options ranking
3. Flag any discrepancies between current protocol and latest evidence
4. Note any new treatment options or trials relevant to this patient's cancer type and biomarkers
5. Store findings as a briefing with recommendations

Focus on actionable changes that would affect current patient management.
"""
    try:
        result = await run_autonomous_task(
            prompt,
            max_turns=8,
            task_name="protocol_review",
            model=AUTONOMOUS_MODEL_LIGHT,
            patient_id=patient_id,
        )
    except Exception as e:
        logger.error("!!! Failed task: protocol_review — %s", e)
        raise
    logger.info(
        "<<< Completed task: protocol_review (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("protocol_review", result, token=token)
    await _set_state(
        f"last_protocol_review:{patient_id}",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
        token=token,
    )
    return result


async def run_daily_cost_report(patient_id: str = "q1b") -> dict:
    """Send morning clinical summary + cost via WhatsApp (no Claude API call)."""
    from .autonomous import get_daily_cost
    from .config import ANTHROPIC_CREDIT_BALANCE, AUTONOMOUS_COST_LIMIT

    logger.info(">>> Starting task: daily_cost_report")
    token = get_patient_token(patient_id)
    try:
        now = datetime.now(UTC)
        month_key = now.strftime("%Y-%m")
        today = now.strftime("%Y-%m-%d")
        header = format_whatsapp_header(
            "Oncoteam Ranný prehľad", date_str=today, patient_name=_patient_display_name(patient_id)
        )
        lines = [header]

        # --- Labs section ---
        try:
            trends = await oncofiles_client.get_lab_trends_data(limit=200, token=token)
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
                    # Normalize ABS_NEUT → ANC and G/L → /µL
                    if "ABS_NEUT" in vals and "ANC" not in vals:
                        vals["ANC"] = vals.pop("ABS_NEUT")
                    anc = vals.get("ANC")
                    if anc is not None and isinstance(anc, (int, float)) and anc < 30:
                        anc = round(anc * 1000)
                    plt = vals.get("PLT")
                    if plt is not None and isinstance(plt, (int, float)) and plt < 1000:
                        plt = round(plt * 1000)
                    wbc = vals.get("WBC")
                    hgb = vals.get("HGB")
                    lines.append(f"*Labky ({latest_date})*")
                    if anc is not None:
                        flag = " ⚠️" if anc < 1500 else ""
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
        patient = get_patient(patient_id)
        lines.append(f"*Cyklus {patient.current_cycle or 3}* — {patient.treatment_regimen}")
        lines.append("")

        # --- Cost section ---
        today_spend = get_daily_cost()
        mtd_spend = 0.0
        try:
            raw = await oncofiles_client.get_agent_state("autonomous_mtd_cost", token=token)
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
        result_data = await _send_whatsapp(msg, recipient="caregiver")

        sent = result_data.get("sent", 0)
        logger.info("<<< Completed task: daily_cost_report — sent to %d", sent)
        return {"ok": True, "message": msg, "sent": sent}

    except Exception as e:
        logger.error("!!! Failed task: daily_cost_report — %s", e)
        record_suppressed_error("daily_cost_report", "send", e)
        return {"ok": False, "error": str(e)}


async def run_health_monitor(patient_id: str = "q1b") -> dict:
    """Check oncofiles health, circuit breaker, RSS — alert on degradation.

    No Claude API call. Direct HTTP + circuit breaker check.
    Sends WhatsApp only if something is wrong.
    """
    logger.info(">>> Starting task: health_monitor")
    alerts: list[str] = []

    # 1. Circuit breaker status
    cb = oncofiles_client.get_circuit_breaker_status()
    cb_state = cb.get("state", "unknown")
    if cb_state != "closed":
        alerts.append(f"🔴 Circuit breaker: {cb_state}")

    # 2. RSS memory
    rss_mb = cb.get("oncofiles_rss_mb", 0)
    if rss_mb >= 400:
        alerts.append(f"⚠️ Oncofiles RSS: {rss_mb}MB (threshold: 400MB)")

    # 3. Folder 404 suspension
    if cb.get("folder_404_suspended"):
        alerts.append("🔴 GDrive folder sync suspended (404)")

    # 4. Oncofiles health endpoint
    import httpx

    from .config import ONCOFILES_MCP_URL

    try:
        base = (
            ONCOFILES_MCP_URL.rsplit("/", 1)[0] if "/" in ONCOFILES_MCP_URL else ONCOFILES_MCP_URL
        )
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base}/health")
            if resp.status_code != 200:
                alerts.append(f"⚠️ Oncofiles /health: HTTP {resp.status_code}")
            else:
                health = resp.json()
                of_rss = health.get("rss_mb", 0)
                if of_rss >= 400:
                    alerts.append(f"⚠️ Oncofiles self-reported RSS: {of_rss}MB")
                if health.get("folder_404_suspended"):
                    alerts.append("🔴 Oncofiles: folder_404_suspended")
    except Exception as e:
        alerts.append(f"🔴 Oncofiles unreachable: {e}")

    if alerts:
        msg = format_whatsapp_header(
            "Health Alert", date_str=datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        )
        msg += "\n".join(alerts)
        msg += "\n\nAuto-check — review at dashboard.oncoteam.cloud/agents"
        await _send_whatsapp(msg, recipient="caregiver")
        logger.warning("<<< health_monitor: %d alerts sent", len(alerts))
    else:
        logger.info("<<< health_monitor: all clear")

    return {"ok": True, "alerts": alerts, "alert_count": len(alerts)}


async def run_patient_registry_sync(patient_id: str | None = None) -> dict:
    """Detect Gate-1-only patients in oncofiles + notify admin (#422).

    Two-gate visibility rule: a patient appears in the clinical dropdown only
    when they exist in oncofiles (Gate 1) AND have a PatientProfile +
    ROLE_MAP entry in oncoteam (Gate 2). Gate-2-missing patients need manual
    onboarding — this agent NEVER calls register_patient().

    The `patient_id` argument is ignored (system-scope); kept for scheduler
    signature parity.

    Behavior on each run:
      1. list_patients() from oncofiles admin.
      2. Load previous snapshot from agent_state `patient_registry:last_snapshot`.
      3. For each oncofiles patient classify as:
         - gate1_only  — in oncofiles, not in oncoteam registry → queue for
           manual onboarding + system-level WhatsApp push (once per patient;
           dedup via signature).
         - gate2_ok    — in both layers → no-op.
         - archived    — was in oncofiles before but is not anymore → log
           session note; never delete local data (soft-only per deletion
           policy).
      4. Persist the fresh snapshot so /api/internal/onboarding-queue and
         the dashboard banner can read it without re-hitting oncofiles.

    Returns a diff summary; error-tolerant — transient oncofiles outage
    simply means the next run retries.
    """
    del patient_id  # system-scope — ignore per-patient invocations
    from .patient_context import list_patient_ids

    logger.info(">>> Starting task: patient_registry_sync")
    started_at = time.time()

    try:
        resp = await oncofiles_client.list_patients(token=None)
    except Exception as e:
        logger.warning("patient_registry_sync: list_patients failed: %s", e)
        record_suppressed_error("patient_registry_sync", "list_patients", e)
        return {"ok": False, "error": str(e)}

    oncofiles_patients: list[dict] = []
    if isinstance(resp, dict):
        oncofiles_patients = resp.get("patients") or resp.get("items") or []
    elif isinstance(resp, list):
        oncofiles_patients = resp

    gate2_ids = set(list_patient_ids())
    now_iso = datetime.now(UTC).isoformat()

    prior_snapshot_raw = await _get_state("patient_registry:last_snapshot", token=None)
    prior_snapshot: dict = {}
    raw_val = (
        prior_snapshot_raw.get("value")
        if isinstance(prior_snapshot_raw, dict)
        else prior_snapshot_raw
    )
    if isinstance(raw_val, str):
        try:
            prior_snapshot = json.loads(raw_val)
        except (json.JSONDecodeError, TypeError):
            prior_snapshot = {}
    elif isinstance(raw_val, dict):
        prior_snapshot = raw_val
    prior_patients = prior_snapshot.get("patients") or []
    prior_slugs = {p.get("slug") for p in prior_patients if isinstance(p, dict)}
    prior_gate1_only = {
        p.get("slug")
        for p in prior_patients
        if isinstance(p, dict) and p.get("classification") == "gate1_only"
    }

    gate1_only: list[dict] = []
    gate2_ok: list[dict] = []
    new_gate1_arrivals: list[dict] = []

    current_slugs: set[str] = set()
    for p in oncofiles_patients:
        if not isinstance(p, dict):
            continue
        slug = p.get("slug") or p.get("patient_id") or p.get("id")
        if not slug:
            continue
        current_slugs.add(slug)
        entry = {
            "slug": slug,
            "name": p.get("name", ""),
            "patient_type": p.get("patient_type", ""),
            "documents": p.get("documents") or p.get("doc_count") or 0,
            "first_seen_in_oncofiles": p.get("created_at") or p.get("first_seen", ""),
            "flagged_at": now_iso,
        }
        if slug in gate2_ids:
            entry["classification"] = "gate2_ok"
            gate2_ok.append(entry)
        else:
            entry["classification"] = "gate1_only"
            gate1_only.append(entry)
            if slug not in prior_gate1_only:
                new_gate1_arrivals.append(entry)

    archived_slugs = prior_slugs - current_slugs

    # WhatsApp push once per newly-detected Gate-1-only patient (dedup via
    # _already_notified). System-scope message — patient_id=None bypasses
    # per-patient notification_policy.
    for entry in new_gate1_arrivals:
        signature = f"gate1_only:{entry['slug']}"
        if await _already_notified("system", signature, token=None):
            continue
        msg = format_whatsapp_header(
            "Nový pacient v oncofiles",
            date_str=datetime.now(UTC).strftime("%Y-%m-%d"),
        )
        msg += (
            f"🆕 **{entry.get('name') or entry['slug']}** "
            f"({entry['slug']}, {entry.get('patient_type') or 'unknown'}, "
            f"{entry.get('documents', 0)} dok.)\n\n"
            "Čaká na oncoteam onboarding — priradiť profil + rolu v "
            "dashboarde.\n\nhttps://dashboard.oncoteam.cloud/admin/onboarding"
        )
        try:
            await _send_whatsapp(msg, recipient="caregiver", patient_id=None)
            await _mark_notified("system", signature, token=None)
        except Exception as e:
            record_suppressed_error("patient_registry_sync", "whatsapp_push", e)

    # Session note for archived-in-oncofiles patients — local data is not
    # deleted (soft-only), but the physician needs to know.
    for slug in archived_slugs:
        try:
            await oncofiles_client.add_activity_log(
                session_id=get_session_id(),
                agent_id="patient_registry_sync",
                tool_name="list_patients",
                input_summary=f"patient archived in oncofiles: {slug}",
                output_summary="local oncoteam data preserved (soft-only deletion policy)",
                status="warning",
                tags=["sys:registry", "task:archive-review", f"patient:{slug}"],
                token=None,
            )
        except Exception as e:
            record_suppressed_error("patient_registry_sync", "archive_log", e)

    snapshot = {
        "timestamp": now_iso,
        "patients": gate1_only + gate2_ok,
        "gate1_only_count": len(gate1_only),
        "gate2_ok_count": len(gate2_ok),
        "archived_count": len(archived_slugs),
    }
    await _set_state("patient_registry:last_snapshot", snapshot, token=None)

    duration_ms = int((time.time() - started_at) * 1000)
    result = {
        "ok": True,
        "gate1_only": [e["slug"] for e in gate1_only],
        "gate1_new_arrivals": [e["slug"] for e in new_gate1_arrivals],
        "gate2_ok": [e["slug"] for e in gate2_ok],
        "archived": sorted(archived_slugs),
        "duration_ms": duration_ms,
    }
    logger.info(
        "<<< patient_registry_sync: gate1=%d gate2=%d archived=%d new=%d (%dms)",
        len(gate1_only),
        len(gate2_ok),
        len(archived_slugs),
        len(new_gate1_arrivals),
        duration_ms,
    )
    await _log_task("patient_registry_sync", result, token=None)
    return result


async def run_funnel_assess(patient_id: str = "q1b") -> dict:
    """Auto-classify new clinical trials into funnel stages."""
    token = get_patient_token(patient_id)
    if await _should_skip("funnel_assess", patient_id, token=token):
        return {"skipped": True, "reason": "cooldown"}
    logger.info(">>> Starting task: funnel_assess (patient=%s)", patient_id)
    prompt = """\
Classify recently discovered clinical trials into funnel stages for the patient.

Instructions:
1. Use search_clinical_trials to find recent trials matching patient profile
2. For each trial, determine the funnel stage:
   - Excluded: biomarker contraindication or eligibility hard-stop
   - Later Line: trial is for 2L/3L+ and patient is on earlier line
   - Watching: relevant but not actionable yet
   - Eligible Now: patient meets criteria, trial recruiting nearby
   - Action Needed: eligible AND enrollment closing soon
3. Use get_patient_context to check patient's biomarkers and excluded therapies.
   Apply exclusion rules from the patient's profile (excluded_therapies dict).
4. Log a briefing with the classification results and any new findings
5. Flag any trials that moved from Watching to Eligible Now

Focus on NEW trials not previously classified. Be concise.\
"""
    try:
        result = await run_autonomous_task(
            prompt,
            max_turns=8,
            task_name="funnel_assess",
            model=AUTONOMOUS_MODEL_LIGHT,
            patient_id=patient_id,
        )
    except Exception as e:
        logger.error("!!! Failed task: funnel_assess — %s", e)
        raise
    logger.info(
        "<<< Completed task: funnel_assess (cost=$%.4f, tools=%d)",
        result.get("cost", 0),
        len(result.get("tool_calls", [])),
    )
    await _log_task("funnel_assess", result, token=token)
    await _set_state(
        f"last_funnel_assess:{patient_id}",
        {"timestamp": datetime.now(UTC).isoformat(), "cost": result.get("cost", 0)},
        token=token,
    )
    return result
