"""Dashboard API: JSON endpoints for the web dashboard and future channels."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import oncofiles_client
from .activity_logger import get_session_id, get_suppressed_errors, record_suppressed_error
from .clinical_protocol import (
    CUMULATIVE_DOSE_THRESHOLDS,
    DOSE_MODIFICATION_RULES,
    LAB_REFERENCE_RANGES,
    LAB_SAFETY_THRESHOLDS,
    MONITORING_SCHEDULE,
    NUTRITION_ESCALATION,
    SAFETY_FLAGS,
    SECOND_LINE_OPTIONS,
    TREATMENT_MILESTONES,
    WATCHED_TRIALS,
)
from .config import (
    ANTHROPIC_BUDGET_ALERT_THRESHOLD,
    ANTHROPIC_CREDIT_BALANCE,
    AUTONOMOUS_COST_LIMIT,
    AUTONOMOUS_ENABLED,
    ONCOFILES_MCP_URL,
)
from .locale import L, get_lang, resolve
from .patient_context import PATIENT, get_patient_localized

VERSION = "0.11.0"

_logger = logging.getLogger("oncoteam.dashboard_api")

# Last trigger result (for debugging via /api/autonomous?last_trigger=1)
_last_trigger_result: dict | None = None

# Patterns that identify test/E2E data created by automated tests
_TEST_TITLE_PATTERNS = ("e2e-test-", "e2e test ", "testovacia")
_TEST_TOOL_NAMES = ("e2e_test",)
_TEST_AGENT_IDS = ("oncoteam-e2e",)
_TEST_TAGS = ("e2e-test",)


def _is_test_entry(entry: dict) -> bool:
    """Return True if the entry looks like test/E2E data."""
    title = (entry.get("title") or "").lower()
    if any(p in title for p in _TEST_TITLE_PATTERNS):
        return True
    tool = (entry.get("tool_name") or entry.get("tool") or "").lower()
    if tool in _TEST_TOOL_NAMES:
        return True
    agent = (entry.get("agent_id") or "").lower()
    if agent in _TEST_AGENT_IDS:
        return True
    tags = entry.get("tags")
    if isinstance(tags, list) and any(t in _TEST_TAGS for t in tags):
        return True
    return isinstance(tags, str) and any(t in tags for t in _TEST_TAGS)


def _show_test(request: Request) -> bool:
    """Check if ?show_test=true is in query params."""
    return request.query_params.get("show_test", "").lower() in ("true", "1", "yes")


def _filter_test(entries: list[dict], request: Request) -> list[dict]:
    """Filter out test entries unless ?show_test=true."""
    if _show_test(request):
        return entries
    return [e for e in entries if not _is_test_entry(e)]


# --- Timeline deduplication ---

_CYCLE_RE = re.compile(r"\b(?:c|cycle|cyklus)\s*(\d+)\b", re.IGNORECASE)


def _extract_cycle_number(title: str) -> int | None:
    """Extract cycle number from event title (e.g., 'FOLFOX C2' -> 2)."""
    m = _CYCLE_RE.search(title)
    if m:
        return int(m.group(1))
    # Try leading number pattern: "2. cyklus FOLFOX"
    m2 = re.match(r"^(\d+)\.\s*(?:cyklus|cycle)\b", title, re.IGNORECASE)
    return int(m2.group(1)) if m2 else None


def _deduplicate_timeline(events: list[dict]) -> list[dict]:
    """Merge events that share the same date and cycle number.

    For events without a cycle number, no deduplication is applied.
    Among duplicates, the entry with the longest notes is kept.
    """
    by_key: dict[tuple[str, int], list[dict]] = {}
    no_cycle: list[dict] = []

    for e in events:
        date = e.get("event_date") or e.get("date") or ""
        title = e.get("title") or ""
        cycle = _extract_cycle_number(title)
        if cycle is not None:
            by_key.setdefault((date, cycle), []).append(e)
        else:
            no_cycle.append(e)

    merged: list[dict] = []
    for group in by_key.values():
        best = max(group, key=lambda x: len(x.get("notes") or ""))
        merged.append(best)

    result = merged + no_cycle
    # Preserve original order by date (descending) then id
    result.sort(
        key=lambda x: (x.get("event_date") or x.get("date") or "", x.get("id") or 0),
        reverse=True,
    )
    return result


# --- Session relevance filtering ---

_NON_ONCOLOGY_PATTERNS = (
    "accounting",
    "instarea",
    "invoice",
    "billing",
    "email scan",
    "contacts refiner",
    "homegrif",
    "shift rotation",
)


def _is_oncology_session(entry: dict) -> bool:
    """Return True if the session is oncology-relevant."""
    title = (entry.get("title") or "").lower()
    content = (entry.get("content") or "").lower()
    # Check negative patterns in title
    for pattern in _NON_ONCOLOGY_PATTERNS:
        if pattern in title:
            return False
    # Also check content first 200 chars for non-oncology patterns
    snippet = content[:200]
    return all(pattern not in snippet for pattern in _NON_ONCOLOGY_PATTERNS)


def _extract_list(result: dict | list | str, key: str) -> list[dict]:
    """Extract a list from an oncofiles response.

    Oncofiles tools may return a plain JSON array (list), a dict with
    the data under `key`, or a dict with an "entries" key.
    """
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        if key in result:
            return result[key]
        if "entries" in result:
            return result["entries"]
    return []


def _build_external_url(source: str, external_id: str) -> str | None:
    """Build external URL for PubMed/ClinicalTrials.gov entries."""
    if source == "pubmed" and external_id:
        return f"https://pubmed.ncbi.nlm.nih.gov/{external_id}/"
    if source == "clinicaltrials" and external_id:
        return f"https://clinicaltrials.gov/study/{external_id}"
    return None


def _cors_json(data: dict, status_code: int = 200) -> JSONResponse:
    """Return JSONResponse with CORS headers for dashboard access."""
    response = JSONResponse(data, status_code=status_code)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


async def api_status(request: Request) -> JSONResponse:
    """GET /api/status — server status and config."""
    tools = [
        "search_pubmed",
        "search_clinical_trials",
        "search_clinical_trials_adjacent",
        "fetch_pubmed_article",
        "fetch_trial_details",
        "check_trial_eligibility",
        "daily_briefing",
        "get_lab_trends",
        "store_lab_values",
        "get_lab_trends_by_parameter",
        "search_documents",
        "get_patient_context",
        "view_document",
        "analyze_labs",
        "compare_labs",
        "log_research_decision",
        "log_session_note",
        "summarize_session",
        "review_session",
        "create_improvement_issue",
    ]
    return _cors_json(
        {
            "status": "ok",
            "server": "oncoteam",
            "version": VERSION,
            "session_id": get_session_id(),
            "tools_count": len(tools),
            "tools": tools,
        }
    )


async def api_activity(request: Request) -> JSONResponse:
    """GET /api/activity — recent activity log entries."""
    limit = int(request.query_params.get("limit", "50"))
    try:
        result = await oncofiles_client.search_activity_log(agent_id="oncoteam", limit=limit)
        entries = _filter_test(_extract_list(result, "entries"), request)
        return _cors_json(
            {
                "entries": [
                    {
                        "tool": e.get("tool_name"),
                        "status": e.get("status"),
                        "duration_ms": e.get("duration_ms"),
                        "timestamp": e.get("created_at"),
                        "input": e.get("input_summary"),
                        "output": e.get("output_summary"),
                        "error": e.get("error_message"),
                    }
                    for e in entries
                ],
                "total": len(entries),
            }
        )
    except Exception as e:
        record_suppressed_error("api_activity", "fetch", e)
        return _cors_json({"error": str(e), "entries": [], "total": 0}, status_code=502)


async def api_stats(request: Request) -> JSONResponse:
    """GET /api/stats — aggregated activity statistics."""
    try:
        result = await oncofiles_client.get_activity_stats(agent_id="oncoteam")
        if isinstance(result, dict):
            return _cors_json(result)
        return _cors_json({"stats": result})
    except Exception as e:
        record_suppressed_error("api_stats", "fetch", e)
        return _cors_json({"error": str(e)}, status_code=502)


async def api_timeline(request: Request) -> JSONResponse:
    """GET /api/timeline — treatment events timeline."""
    limit = int(request.query_params.get("limit", "50"))
    try:
        result = await oncofiles_client.list_treatment_events(limit=limit)
        events = _filter_test(_extract_list(result, "events"), request)
        events = _deduplicate_timeline(events)
        return _cors_json(
            {
                "events": [
                    {
                        "id": e.get("id"),
                        "date": e.get("event_date"),
                        "type": e.get("event_type"),
                        "title": e.get("title"),
                        "notes": e.get("notes"),
                    }
                    for e in events
                ],
                "total": len(events),
            }
        )
    except Exception as e:
        record_suppressed_error("api_timeline", "fetch", e)
        return _cors_json({"error": str(e), "events": [], "total": 0}, status_code=502)


async def api_patient(request: Request) -> JSONResponse:
    """GET /api/patient — patient profile (static, no oncofiles call)."""
    lang = get_lang(request)
    data = get_patient_localized(lang)
    return _cors_json(data)


async def api_research(request: Request) -> JSONResponse:
    """GET /api/research — research entries from oncofiles."""
    limit = int(request.query_params.get("limit", "20"))
    source = request.query_params.get("source")
    try:
        result = await oncofiles_client.list_research_entries(source=source, limit=limit)
        entries = _filter_test(_extract_list(result, "entries"), request)
        return _cors_json(
            {
                "entries": [
                    {
                        "id": e.get("id"),
                        "source": e.get("source"),
                        "external_id": e.get("external_id"),
                        "title": e.get("title"),
                        "summary": e.get("summary"),
                        "date": e.get("created_at"),
                        "external_url": _build_external_url(
                            e.get("source", ""), e.get("external_id", "")
                        ),
                    }
                    for e in entries
                ],
                "total": len(entries),
            }
        )
    except Exception as e:
        record_suppressed_error("api_research", "fetch", e)
        return _cors_json({"error": str(e), "entries": [], "total": 0}, status_code=502)


async def api_sessions(request: Request) -> JSONResponse:
    """GET /api/sessions — session summaries from conversations."""
    limit = int(request.query_params.get("limit", "20"))
    try:
        result = await oncofiles_client.search_conversations(
            entry_type="session_summary", limit=limit
        )
        entries = _filter_test(_extract_list(result, "entries"), request)
        entries = [e for e in entries if _is_oncology_session(e)]
        return _cors_json(
            {
                "sessions": [
                    {
                        "id": e.get("id"),
                        "title": e.get("title"),
                        "content": e.get("content"),
                        "date": e.get("created_at"),
                        "tags": e.get("tags"),
                    }
                    for e in entries
                ],
                "total": len(entries),
            }
        )
    except Exception as e:
        record_suppressed_error("api_sessions", "fetch", e)
        return _cors_json({"error": str(e), "sessions": [], "total": 0}, status_code=502)


async def api_autonomous(request: Request) -> JSONResponse:
    """GET /api/autonomous — autonomous agent status and manual trigger."""
    from .autonomous import get_daily_cost

    # Check last trigger result
    if request.query_params.get("last_trigger"):
        return _cors_json(_last_trigger_result or {"status": "no_trigger_yet"})

    # Manual trigger via ?trigger=<task_name>
    trigger = request.query_params.get("trigger")
    if trigger:
        from . import autonomous_tasks

        task_fn = getattr(autonomous_tasks, f"run_{trigger}", None)
        if task_fn is None:
            return _cors_json({"error": f"Unknown task: {trigger}"}, status_code=400)

        from .config import ANTHROPIC_API_KEY

        if not ANTHROPIC_API_KEY:
            return _cors_json(
                {"error": "ANTHROPIC_API_KEY not configured"}, status_code=500
            )

        # Run in background with error capture
        async def _run_with_capture():
            global _last_trigger_result
            try:
                result = await task_fn()
                _last_trigger_result = {
                    "task": trigger,
                    "status": "completed",
                    "cost": result.get("cost", 0),
                    "tool_calls": len(result.get("tool_calls", [])),
                    "error": result.get("error"),
                    "duration_ms": result.get("duration_ms", 0),
                }
                _logger.info("Trigger %s completed: %s", trigger, _last_trigger_result)
            except Exception as e:
                _last_trigger_result = {
                    "task": trigger,
                    "status": "failed",
                    "error": str(e),
                }
                _logger.error("Trigger %s failed: %s", trigger, e)

        asyncio.create_task(_run_with_capture())
        return _cors_json({"triggered": trigger, "status": "started"})

    # Default: return scheduler status
    data: dict = {
        "enabled": AUTONOMOUS_ENABLED,
        "daily_cost": round(get_daily_cost(), 4),
    }

    if AUTONOMOUS_ENABLED:
        try:
            lang = get_lang(request)
            # Jobs are registered at startup, we report their config
            jobs_raw = [
                {
                    "id": "pre_cycle_check",
                    "assigned_tool": "pre_cycle_check",
                    "schedule": L("každých 13 dní", "every 13 days"),
                    "description": L(
                        "Kontrola bezpečnosti pred cyklom FOLFOX", "Pre-cycle FOLFOX safety check"
                    ),
                },
                {
                    "id": "tumor_marker_review",
                    "assigned_tool": "tumor_marker_review",
                    "schedule": L("každé 4 týždne", "every 4 weeks"),
                    "description": L("Analýza trendu CEA/CA 19-9", "CEA/CA 19-9 trend analysis"),
                },
                {
                    "id": "response_assessment",
                    "assigned_tool": "response_assessment",
                    "schedule": L("každých 8 týždňov", "every 8 weeks"),
                    "description": L("Hodnotenie odpovede RECIST", "RECIST response evaluation"),
                },
                {
                    "id": "daily_research",
                    "assigned_tool": "search_pubmed",
                    "schedule": L("denne 07:00 UTC", "daily 07:00 UTC"),
                    "description": L("Prehľad výskumu PubMed", "PubMed research scan"),
                },
                {
                    "id": "trial_monitor",
                    "assigned_tool": "search_clinical_trials",
                    "schedule": L("každých 6 hodín", "every 6 hours"),
                    "description": L(
                        "Monitorovanie klinických štúdií", "Clinical trial monitoring"
                    ),
                },
                {
                    "id": "file_scan",
                    "assigned_tool": "search_documents",
                    "schedule": L("každé 2 hodiny", "every 2 hours"),
                    "description": L("Skenovanie nových dokumentov", "New document scan"),
                },
                {
                    "id": "weekly_briefing",
                    "assigned_tool": "daily_briefing",
                    "schedule": L("pondelok 06:00 UTC", "Monday 06:00 UTC"),
                    "description": L("Týždenný briefing pre lekára", "Weekly physician briefing"),
                },
                {
                    "id": "mtb_preparation",
                    "assigned_tool": "review_session",
                    "schedule": L("piatok 14:00 UTC", "Friday 14:00 UTC"),
                    "description": L("Príprava na tumor board", "Tumor board preparation"),
                },
                {
                    "id": "lab_sync",
                    "assigned_tool": "analyze_labs",
                    "schedule": L("každých 6 hodín", "every 6 hours"),
                    "description": L(
                        "Extrakcia lab. hodnôt z dokumentov", "Extract lab values from documents"
                    ),
                },
                {
                    "id": "toxicity_extraction",
                    "assigned_tool": "compare_labs",
                    "schedule": L("denne 08:00 UTC", "daily 08:00 UTC"),
                    "description": L(
                        "Extrakcia toxicity zo správ z vyšetrení",
                        "Extract toxicity from visit reports",
                    ),
                },
                {
                    "id": "weight_extraction",
                    "assigned_tool": "get_lab_trends",
                    "schedule": L("denne 09:00 UTC", "daily 09:00 UTC"),
                    "description": L(
                        "Extrakcia hmotnosti/BMI zo správ", "Extract weight/BMI from visit notes"
                    ),
                },
                {
                    "id": "family_update",
                    "assigned_tool": "summarize_session",
                    "schedule": L("nedeľa 18:00 UTC", "Sunday 18:00 UTC"),
                    "description": L("Týždenná správa pre rodinu", "Weekly family update"),
                },
                {
                    "id": "medication_adherence_check",
                    "assigned_tool": "log_session_note",
                    "schedule": L("denne 20:00 UTC", "daily 20:00 UTC"),
                    "description": L(
                        "Kontrola dennej adherencie liekov (Clexane kritický)",
                        "Check daily medication adherence (Clexane critical)",
                    ),
                },
            ]
            data["jobs"] = resolve(jobs_raw, lang)
            data["job_count"] = len(jobs_raw)
        except Exception:
            data["jobs"] = []
            data["job_count"] = 0

    return _cors_json(data)


async def api_autonomous_cost(request: Request) -> JSONResponse:
    """GET /api/autonomous/cost — budget overview for dashboard widget.

    Returns MTD spend, daily spend, expected EOM bill, remaining credit,
    daily cap, and budget alert status. Visible to all roles.
    """
    from calendar import monthrange
    from datetime import UTC, datetime

    from .autonomous import get_daily_cost

    now = datetime.now(UTC)
    days_in_month = monthrange(now.year, now.month)[1]
    day_of_month = now.day

    # Today's spend (from in-memory accumulator, restored from DB on cold start)
    today_spend = round(get_daily_cost(), 4)

    # Fetch MTD spend from oncofiles agent_state
    mtd_spend = today_spend
    try:
        state = await oncofiles_client.get_agent_state("autonomous_mtd_cost")
        if isinstance(state, dict) and state.get("month") == now.strftime("%Y-%m"):
            mtd_spend = round(
                float(state.get("cost_usd", 0.0)) + today_spend, 4
            )
    except Exception:
        pass

    # Project EOM spend (linear extrapolation)
    if day_of_month > 0:
        daily_avg = mtd_spend / day_of_month
        expected_eom = round(daily_avg * days_in_month, 2)
    else:
        daily_avg = 0.0
        expected_eom = 0.0

    remaining_credit = round(ANTHROPIC_CREDIT_BALANCE - mtd_spend, 2)
    days_remaining = (
        round(remaining_credit / daily_avg, 1) if daily_avg > 0 else 999
    )

    budget_alert = remaining_credit <= ANTHROPIC_BUDGET_ALERT_THRESHOLD

    return _cors_json({
        "today_spend": today_spend,
        "daily_cap": AUTONOMOUS_COST_LIMIT,
        "mtd_spend": round(mtd_spend, 2),
        "expected_eom": expected_eom,
        "remaining_credit": max(remaining_credit, 0),
        "total_credit": ANTHROPIC_CREDIT_BALANCE,
        "days_remaining": days_remaining,
        "budget_alert": budget_alert,
        "alert_threshold": ANTHROPIC_BUDGET_ALERT_THRESHOLD,
        "month": now.strftime("%Y-%m"),
        "day_of_month": day_of_month,
        "days_in_month": days_in_month,
    })


async def api_protocol(request: Request) -> JSONResponse:
    """GET /api/protocol — clinical protocol data (thresholds, milestones, dose mods)."""
    from .clinical_protocol import resolve_protocol

    lang = get_lang(request)
    return _cors_json(resolve_protocol(lang))


async def api_protocol_cycles(request: Request) -> JSONResponse:
    """GET /api/protocol/cycles — previous cycle history with lab evaluations."""
    from .clinical_protocol import LAB_SAFETY_THRESHOLDS, check_lab_safety

    cycle = PATIENT.current_cycle or 3

    # Fetch lab results and chemo events
    try:
        lab_result, chemo_result = await asyncio.gather(
            oncofiles_client.list_treatment_events(event_type="lab_result", limit=50),
            oncofiles_client.list_treatment_events(event_type="chemotherapy", limit=50),
        )
        lab_entries = _extract_list(lab_result, "entries")
        chemo_entries = _extract_list(chemo_result, "entries")
    except Exception as e:
        record_suppressed_error("api_protocol_cycles", "fetch", e)
        return _cors_json({"cycles": [], "current_cycle": cycle, "error": str(e)})

    # Build a map: cycle_number -> chemo date
    chemo_by_cycle: dict[int, str] = {}
    for entry in chemo_entries:
        title = entry.get("title") or ""
        c_num = _extract_cycle_number(title)
        if c_num and c_num < cycle:
            chemo_by_cycle[c_num] = entry.get("event_date") or entry.get("date") or ""

    # Lab parameter name mapping (from lab entry keys to LAB_SAFETY_THRESHOLDS keys)
    lab_key_map = {
        "ABS_NEUT": "ANC",
        "ANC": "ANC",
        "PLT": "PLT",
        "creatinine": "creatinine",
        "ALT": "ALT",
        "AST": "AST",
        "bilirubin": "bilirubin",
    }

    cycles = []
    for c_num in range(1, cycle):
        chemo_date = chemo_by_cycle.get(c_num, "")
        # Find lab entries near this cycle's date (within 3 days before, or same day)
        lab_eval: dict[str, dict] = {}
        source_id = None
        for lab in lab_entries:
            lab_date = lab.get("event_date") or lab.get("date") or ""
            if not chemo_date or not lab_date:
                continue
            # Simple date proximity: check if lab_date is within 3 days before chemo_date
            try:
                from datetime import datetime

                ld = datetime.fromisoformat(lab_date[:10])
                cd = datetime.fromisoformat(chemo_date[:10])
                diff = (cd - ld).days
                if 0 <= diff <= 3:
                    # Extract lab values from notes/data
                    data_field = lab.get("data") or {}
                    if isinstance(data_field, str):
                        with contextlib.suppress(Exception):
                            data_field = json.loads(data_field)
                    values = data_field if isinstance(data_field, dict) else {}
                    # Check each threshold parameter
                    for raw_key, threshold_key in lab_key_map.items():
                        val = values.get(raw_key)
                        if val is not None:
                            try:
                                fval = float(val)
                                threshold = LAB_SAFETY_THRESHOLDS.get(threshold_key, {})
                                result = check_lab_safety(threshold_key, fval)
                                lab_eval[threshold_key] = {
                                    "value": fval,
                                    "threshold": threshold.get("min", threshold.get("max_ratio")),
                                    "unit": threshold.get("unit", ""),
                                    "pass": result["safe"],
                                }
                            except (ValueError, TypeError):
                                pass
                    source_id = lab.get("id")
                    break  # Use first matching lab
            except Exception:
                continue

        overall_pass = all(v["pass"] for v in lab_eval.values()) if lab_eval else True
        cycles.append(
            {
                "cycle_number": c_num,
                "date": chemo_date,
                "lab_evaluation": lab_eval,
                "overall_pass": overall_pass,
                "source_event_id": source_id,
            }
        )

    return _cors_json({"cycles": cycles, "current_cycle": cycle})


async def api_briefings(request: Request) -> JSONResponse:
    """GET /api/briefings — autonomous briefings + cost alerts from oncofiles diary."""
    limit = int(request.query_params.get("limit", "20"))
    try:
        briefings_res, alerts_res = await asyncio.gather(
            oncofiles_client.search_conversations(
                entry_type="autonomous_briefing", limit=limit
            ),
            oncofiles_client.search_conversations(
                entry_type="cost_alert", limit=5
            ),
            return_exceptions=True,
        )
        briefings = (
            _extract_list(briefings_res, "entries") if isinstance(briefings_res, dict) else []
        )
        alerts = (
            _extract_list(alerts_res, "entries") if isinstance(alerts_res, dict) else []
        )
        entries = _filter_test(briefings + alerts, request)
        entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        return _cors_json(
            {
                "briefings": [
                    {
                        "id": e.get("id"),
                        "title": e.get("title"),
                        "content": e.get("content"),
                        "date": e.get("created_at"),
                        "tags": e.get("tags"),
                        "type": e.get("entry_type", "autonomous_briefing"),
                    }
                    for e in entries[:limit]
                ],
                "total": len(entries),
            }
        )
    except Exception as e:
        record_suppressed_error("api_briefings", "fetch", e)
        return _cors_json({"error": str(e), "briefings": [], "total": 0}, status_code=502)


async def api_toxicity(request: Request) -> JSONResponse:
    """GET/POST /api/toxicity — toxicity log entries.

    GET: list toxicity logs (treatment events with event_type=toxicity_log).
    POST: create a new toxicity log entry.
    """
    if request.method == "POST":
        try:
            body = json.loads(await request.body())
        except (json.JSONDecodeError, Exception):
            return _cors_json({"error": "Invalid JSON body"}, status_code=400)

        required = ["date"]
        if not all(body.get(k) for k in required):
            return _cors_json({"error": "date is required"}, status_code=400)

        metadata = {
            k: body[k]
            for k in (
                "neuropathy",
                "diarrhea",
                "mucositis",
                "fatigue",
                "hand_foot",
                "nausea",
                "weight_kg",
                "ecog",
                "appetite",
                "oral_intake",
            )
            if k in body
        }

        try:
            result = await oncofiles_client.add_treatment_event(
                event_date=body["date"],
                event_type="toxicity_log",
                title=f"Toxicity log {body['date']}",
                notes=body.get("notes", ""),
                metadata=metadata,
            )
            return _cors_json({"created": True, "result": result})
        except Exception as e:
            record_suppressed_error("api_toxicity", "create", e)
            return _cors_json({"error": str(e)}, status_code=502)

    # GET: list toxicity logs
    limit = int(request.query_params.get("limit", "50"))
    try:
        result = await oncofiles_client.list_treatment_events(
            event_type="toxicity_log", limit=limit
        )
        events = _filter_test(_extract_list(result, "events"), request)
        return _cors_json(
            {
                "entries": [
                    {
                        "id": e.get("id"),
                        "date": e.get("event_date"),
                        "notes": e.get("notes"),
                        "metadata": e.get("metadata", {}),
                    }
                    for e in events
                ],
                "total": len(events),
            }
        )
    except Exception as e:
        record_suppressed_error("api_toxicity", "fetch", e)
        return _cors_json({"error": str(e), "entries": [], "total": 0}, status_code=502)


async def api_labs(request: Request) -> JSONResponse:
    """GET/POST /api/labs — structured lab results.

    GET: list lab results (treatment events with event_type=lab_result).
    POST: create a new lab result entry.
    """
    if request.method == "POST":
        try:
            body = json.loads(await request.body())
        except (json.JSONDecodeError, Exception):
            return _cors_json({"error": "Invalid JSON body"}, status_code=400)

        if not body.get("date"):
            return _cors_json({"error": "date is required"}, status_code=400)

        values = body.get("values", {})
        try:
            result = await oncofiles_client.add_treatment_event(
                event_date=body["date"],
                event_type="lab_result",
                title=f"Lab results {body['date']}",
                notes=body.get("notes", ""),
                metadata=values,
            )
            return _cors_json({"created": True, "result": result})
        except Exception as e:
            record_suppressed_error("api_labs", "create", e)
            return _cors_json({"error": str(e)}, status_code=502)

    # GET: list lab results
    limit = int(request.query_params.get("limit", "50"))
    try:
        result = await oncofiles_client.list_treatment_events(event_type="lab_result", limit=limit)
        events = _filter_test(_extract_list(result, "events"), request)

        # Fallback: if no structured lab_result events, try analyze_labs
        if not events:
            try:
                analysis = await oncofiles_client.analyze_labs(limit=limit)
                if isinstance(analysis, dict):
                    # analyze_labs may return structured results we can display
                    lab_sets = analysis.get("lab_results", analysis.get("results", []))
                    if isinstance(lab_sets, list):
                        for lab in lab_sets:
                            if isinstance(lab, dict) and lab.get("date"):
                                events.append(
                                    {
                                        "event_date": lab["date"],
                                        "metadata": {
                                            k: v
                                            for k, v in lab.items()
                                            if k not in ("date", "id", "document_id")
                                        },
                                        "notes": lab.get("notes", "From document analysis"),
                                        "id": lab.get("id"),
                                    }
                                )
            except Exception as fallback_err:
                record_suppressed_error("api_labs", "analyze_labs_fallback", fallback_err)

        # Extract values and check against safety thresholds + reference ranges
        entries = []
        for e in events:
            meta = e.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    meta = {}
            alerts = []
            value_statuses = {}
            for param, threshold in LAB_SAFETY_THRESHOLDS.items():
                if param in meta:
                    val = meta[param]
                    if (
                        isinstance(val, (int, float))
                        and "min" in threshold
                        and val < threshold["min"]
                    ):
                        alerts.append(
                            {
                                "param": param,
                                "value": val,
                                "threshold": threshold["min"],
                                "action": threshold["action"],
                            }
                        )
            # Determine status for each value against reference ranges
            for param, val in meta.items():
                if not isinstance(val, (int, float)):
                    continue
                ref = LAB_REFERENCE_RANGES.get(param)
                if ref is None:
                    continue
                if val < ref["min"]:
                    value_statuses[param] = "low"
                elif val > ref["max"]:
                    value_statuses[param] = "high"
                else:
                    value_statuses[param] = "normal"
            entries.append(
                {
                    "id": e.get("id"),
                    "date": e.get("event_date"),
                    "values": meta,
                    "notes": e.get("notes"),
                    "alerts": alerts,
                    "value_statuses": value_statuses,
                }
            )

        return _cors_json(
            {
                "entries": entries,
                "total": len(entries),
                "reference_ranges": LAB_REFERENCE_RANGES,
            }
        )
    except Exception as e:
        record_suppressed_error("api_labs", "fetch", e)
        return _cors_json({"error": str(e), "entries": [], "total": 0}, status_code=502)


async def api_detail(request: Request) -> JSONResponse:
    """GET /api/detail/{type}/{id} — fetch full detail for any data element."""
    detail_type = request.path_params.get("type", "")
    detail_id = request.path_params.get("id", "")

    try:
        data: dict = {}
        source: dict = {"oncofiles_id": None, "gdrive_file_id": None, "gdrive_url": None}
        related: list[dict] = []

        if detail_type == "treatment_event":
            raw = await oncofiles_client.get_treatment_event(int(detail_id))
            data = raw if isinstance(raw, dict) else {"raw": raw}
            source["oncofiles_id"] = int(detail_id)
            # Parse metadata if string
            meta = data.get("metadata", {})
            if isinstance(meta, str):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    data["metadata"] = json.loads(meta)

        elif detail_type == "research":
            try:
                raw = await oncofiles_client.get_research_entry(int(detail_id))
                data = raw if isinstance(raw, dict) else {"raw": raw}
            except Exception:
                # Fallback: fetch list and filter
                result = await oncofiles_client.list_research_entries(limit=100)
                entries = _extract_list(result, "entries")
                match = [e for e in entries if e.get("id") == int(detail_id)]
                data = match[0] if match else {"error": "not found"}
            source["oncofiles_id"] = int(detail_id)
            # Build external link
            ext_id = data.get("external_id", "")
            src = data.get("source", "")
            if src == "pubmed" and ext_id:
                data["external_url"] = f"https://pubmed.ncbi.nlm.nih.gov/{ext_id}/"
            elif src == "clinicaltrials" and ext_id:
                data["external_url"] = f"https://clinicaltrials.gov/study/{ext_id}"

        elif detail_type == "conversation":
            try:
                raw = await oncofiles_client.get_conversation(int(detail_id))
                data = raw if isinstance(raw, dict) else {"raw": raw}
            except Exception:
                result = await oncofiles_client.search_conversations(limit=100)
                entries = _extract_list(result, "entries")
                match = [e for e in entries if e.get("id") == int(detail_id)]
                data = match[0] if match else {"error": "not found"}
            source["oncofiles_id"] = int(detail_id)

        elif detail_type == "document":
            raw = await oncofiles_client.get_document(int(detail_id))
            data = raw if isinstance(raw, dict) else {"raw": raw}
            source["oncofiles_id"] = int(detail_id)
            gdrive_id = data.get("gdrive_file_id") or data.get("google_drive_id")
            if gdrive_id:
                source["gdrive_file_id"] = gdrive_id
                source["gdrive_url"] = f"https://drive.google.com/file/d/{gdrive_id}/view"
            # Fetch full content if file_id is available
            file_id = data.get("file_id")
            if file_id:
                try:
                    content = await oncofiles_client.view_document(file_id)
                    data["content"] = content
                except Exception:
                    pass  # Content fetch failed — metadata still available

        elif detail_type == "biomarker":
            # Static from patient context
            patient_data = PATIENT.model_dump()
            biomarkers = patient_data.get("biomarkers", {})
            value = biomarkers.get(detail_id, biomarkers.get(detail_id.replace(" ", "_")))
            data = {
                "name": detail_id,
                "value": str(value) if value is not None else "unknown",
                "biomarkers": biomarkers,
                "excluded_therapies": patient_data.get("excluded_therapies", {}),
                "diagnosis": patient_data.get("diagnosis_description"),
                "staging": patient_data.get("staging"),
            }

        elif detail_type == "protocol_section":
            sections = {
                "lab_thresholds": LAB_SAFETY_THRESHOLDS,
                "dose_modifications": DOSE_MODIFICATION_RULES,
                "milestones": TREATMENT_MILESTONES,
                "monitoring_schedule": MONITORING_SCHEDULE,
                "safety_flags": SAFETY_FLAGS,
                "second_line_options": SECOND_LINE_OPTIONS,
                "watched_trials": WATCHED_TRIALS,
            }
            data = {"section": detail_id, "data": sections.get(detail_id, {})}

        elif detail_type == "activity":
            # Fetch from activity log by searching recent entries
            result = await oncofiles_client.search_activity_log(agent_id="oncoteam", limit=200)
            entries = _extract_list(result, "entries")
            match = [e for e in entries if str(e.get("id")) == str(detail_id)]
            data = match[0] if match else {"error": "not found"}
            source["oncofiles_id"] = data.get("id")

        elif detail_type == "medication":
            # Fetch medication log entry (treatment event)
            raw = await oncofiles_client.get_treatment_event(int(detail_id))
            data = raw if isinstance(raw, dict) else {"raw": raw}
            source["oncofiles_id"] = int(detail_id)
            meta = data.get("metadata", {})
            if isinstance(meta, str):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    data["metadata"] = json.loads(meta)

        elif detail_type == "patient":
            patient_data = PATIENT.model_dump()
            if patient_data.get("diagnosis_date"):
                patient_data["diagnosis_date"] = str(patient_data["diagnosis_date"])
            data = patient_data

        else:
            return _cors_json({"error": f"Unknown detail type: {detail_type}"}, status_code=400)

        return _cors_json(
            {
                "type": detail_type,
                "id": detail_id,
                "data": data,
                "source": source,
                "related": related,
            }
        )

    except Exception as e:
        record_suppressed_error("api_detail", f"{detail_type}/{detail_id}", e)
        return _cors_json({"error": str(e)}, status_code=502)


async def api_diagnostics(request: Request) -> JSONResponse:
    """GET /api/diagnostics — probe oncofiles connectivity and report health."""
    checks: list[dict] = []
    probes = [
        ("treatment_events", oncofiles_client.list_treatment_events, {"limit": 1}, "events"),
        ("research_entries", oncofiles_client.list_research_entries, {"limit": 1}, "entries"),
        ("conversations", oncofiles_client.search_conversations, {"limit": 1}, "entries"),
        ("activity_log", oncofiles_client.search_activity_log, {"limit": 1}, "entries"),
    ]
    for name, fn, kwargs, key in probes:
        try:
            t0 = time.time()
            result = await fn(**kwargs)
            ms = int((time.time() - t0) * 1000)
            count = len(_extract_list(result, key))
            checks.append({"name": name, "ok": True, "ms": ms, "sample_count": count})
        except Exception as e:
            checks.append({"name": name, "ok": False, "error": str(e)})

    return _cors_json(
        {
            "healthy": all(c["ok"] for c in checks),
            "checks": checks,
            "oncofiles_url": (ONCOFILES_MCP_URL[:30] + "...") if ONCOFILES_MCP_URL else "NOT SET",
            "autonomous_enabled": AUTONOMOUS_ENABLED,
            "suppressed_errors": get_suppressed_errors()[-10:],
        }
    )


# ── Default medications (FOLFOX regimen) ──────

_DEFAULT_MEDICATIONS = [
    {
        "name": "Clexane",
        "dose": "0,6ml SC",
        "frequency": L("2x/deň", "2x/day"),
        "active": True,
        "notes": L(
            "Antikoagulant — kritický, aktívna VJI trombóza",
            "Anticoagulant — critical, active VJI thrombosis",
        ),
    },
    {
        "name": "Ondansetron",
        "dose": "8mg",
        "frequency": L("podľa potreby", "as needed"),
        "active": True,
        "notes": L("Antiemetikum", "Anti-emetic"),
    },
    {
        "name": "Dexamethasone",
        "dose": L("podľa protokolu", "per protocol"),
        "frequency": L("s chemoterapiou", "with chemo"),
        "active": True,
        "notes": L(
            "Antiemetikum, podávané s chemoterapiou", "Anti-emetic, given with chemotherapy"
        ),
    },
    {
        "name": "Aprepitant",
        "dose": "125/80mg",
        "frequency": L("D1-3 cyklu", "D1-3 of cycle"),
        "active": True,
        "notes": L("Antiemetikum, dni 1-3 každého cyklu", "Anti-emetic, days 1-3 of each cycle"),
    },
]


async def api_medications(request: Request) -> JSONResponse:
    """GET/POST /api/medications — medication tracker.

    GET: list medication log entries + default regimen medications.
    POST: create a new medication log entry.
    """
    if request.method == "POST":
        try:
            body = json.loads(await request.body())
        except (json.JSONDecodeError, Exception):
            return _cors_json({"error": "Invalid JSON body"}, status_code=400)

        # Adherence check-in: {date, medications: {name: taken_bool}}
        if "medications" in body and isinstance(body["medications"], dict):
            if not body.get("date"):
                return _cors_json({"error": "date is required"}, status_code=400)
            try:
                result = await oncofiles_client.add_treatment_event(
                    event_date=body["date"],
                    event_type="medication_adherence",
                    title=f"Adherence {body['date']}",
                    notes=body.get("notes", ""),
                    metadata={"medications": body["medications"]},
                )
                return _cors_json(
                    {"created": True, "event_type": "medication_adherence", "result": result}
                )
            except Exception as e:
                record_suppressed_error("api_medications", "create_adherence", e)
                return _cors_json({"error": str(e)}, status_code=502)

        # Regular medication log
        if not body.get("date") or not body.get("name"):
            return _cors_json({"error": "date and name are required"}, status_code=400)

        metadata = {
            k: body[k] for k in ("dose", "frequency", "time_of_day", "active", "notes") if k in body
        }

        try:
            result = await oncofiles_client.add_treatment_event(
                event_date=body["date"],
                event_type="medication_log",
                title=f"{body['name']} {body['date']}",
                notes=body.get("notes", ""),
                metadata={"name": body["name"], **metadata},
            )
            return _cors_json({"created": True, "result": result})
        except Exception as e:
            record_suppressed_error("api_medications", "create", e)
            return _cors_json({"error": str(e)}, status_code=502)

    # GET: list medication logs + adherence data
    limit = int(request.query_params.get("limit", "50"))
    try:
        med_result, adh_result = await asyncio.gather(
            oncofiles_client.list_treatment_events(event_type="medication_log", limit=limit),
            oncofiles_client.list_treatment_events(event_type="medication_adherence", limit=7),
            return_exceptions=True,
        )

        # Process medication logs
        events = (
            _filter_test(_extract_list(med_result, "events"), request)
            if not isinstance(med_result, Exception)
            else []
        )
        medications = []
        for e in events:
            meta = e.get("metadata", {})
            if isinstance(meta, str):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    meta = json.loads(meta)
            medications.append(
                {
                    "id": e.get("id"),
                    "date": e.get("event_date"),
                    "name": meta.get("name", e.get("title", "")),
                    "dose": meta.get("dose"),
                    "frequency": meta.get("frequency"),
                    "time_of_day": meta.get("time_of_day"),
                    "active": meta.get("active", True),
                    "notes": e.get("notes") or meta.get("notes"),
                }
            )

        # Process adherence data
        adherence_entries = (
            _extract_list(adh_result, "events") if not isinstance(adh_result, Exception) else []
        )
        last_7_days = []
        missed = []
        total_checks = 0
        taken_count = 0
        for ae in adherence_entries:
            meta = ae.get("metadata", {})
            if isinstance(meta, str):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    meta = json.loads(meta)
            meds = meta.get("medications", {})
            date = ae.get("event_date", "")
            last_7_days.append({"date": date, "medications": meds})
            for med_name, taken in meds.items():
                total_checks += 1
                if taken:
                    taken_count += 1
                else:
                    missed.append({"date": date, "medication": med_name})
        compliance_pct = round((taken_count / total_checks) * 100, 1) if total_checks > 0 else None

        lang = get_lang(request)
        return _cors_json(
            {
                "medications": medications,
                "default_medications": resolve(_DEFAULT_MEDICATIONS, lang),
                "adherence": {
                    "last_7_days": last_7_days,
                    "compliance_pct": compliance_pct,
                    "missed": missed,
                },
                "total": len(medications),
            }
        )
    except Exception as e:
        record_suppressed_error("api_medications", "fetch", e)
        lang = get_lang(request)
        return _cors_json(
            {
                "error": str(e),
                "medications": [],
                "default_medications": resolve(_DEFAULT_MEDICATIONS, lang),
                "adherence": {"last_7_days": [], "compliance_pct": None, "missed": []},
                "total": 0,
            },
            status_code=502,
        )


async def api_weight(request: Request) -> JSONResponse:
    """GET /api/weight — weight/nutrition trend data.

    Aggregates weight from weight_measurement and toxicity_log events.
    Calculates % change from baseline and flags >5% loss.
    """
    limit = int(request.query_params.get("limit", "50"))
    baseline = PATIENT.baseline_weight_kg or 72.0

    try:
        # Fetch both weight_measurement and toxicity_log events in parallel
        weight_result, toxicity_result = await asyncio.gather(
            oncofiles_client.list_treatment_events(event_type="weight_measurement", limit=limit),
            oncofiles_client.list_treatment_events(event_type="toxicity_log", limit=limit),
            return_exceptions=True,
        )

        entries_by_date: dict[str, dict] = {}

        # Process weight_measurement events
        if not isinstance(weight_result, Exception):
            for e in _extract_list(weight_result, "events"):
                meta = e.get("metadata", {})
                if isinstance(meta, str):
                    with contextlib.suppress(json.JSONDecodeError, TypeError):
                        meta = json.loads(meta)
                date = e.get("event_date", "")
                weight = meta.get("weight_kg")
                if date and weight is not None:
                    entries_by_date[date] = {
                        "date": date,
                        "weight_kg": weight,
                        "appetite": meta.get("appetite"),
                        "oral_intake": meta.get("oral_intake"),
                    }

        # Process toxicity_log events (may also have weight_kg)
        if not isinstance(toxicity_result, Exception):
            for e in _extract_list(toxicity_result, "events"):
                meta = e.get("metadata", {})
                if isinstance(meta, str):
                    with contextlib.suppress(json.JSONDecodeError, TypeError):
                        meta = json.loads(meta)
                date = e.get("event_date", "")
                weight = meta.get("weight_kg")
                if date and weight is not None and date not in entries_by_date:
                    entries_by_date[date] = {
                        "date": date,
                        "weight_kg": weight,
                        "appetite": meta.get("appetite"),
                        "oral_intake": meta.get("oral_intake"),
                    }

        # Calculate % change and alerts
        entries = []
        alerts = []
        for date in sorted(entries_by_date.keys()):
            entry = entries_by_date[date]
            weight = entry["weight_kg"]
            pct_change = round(((weight - baseline) / baseline) * 100, 1)
            alert = abs(pct_change) >= 5 and pct_change < 0
            entry["pct_change"] = pct_change
            entry["alert"] = alert
            entries.append(entry)
            if alert:
                loss_pct = round(abs(pct_change), 1)
                loss_kg = round(baseline - weight, 1)
                # Find the matching nutrition escalation action
                escalation_action = None
                escalation_severity = "warning"
                lang = get_lang(request)
                for rule in reversed(NUTRITION_ESCALATION):
                    if loss_pct >= rule["loss_pct"]:
                        escalation_action = resolve(rule["action"], lang)
                        escalation_severity = rule["severity"]
                        break
                alerts.append(
                    {
                        "date": date,
                        "weight_kg": weight,
                        "loss_pct": loss_pct,
                        "action": escalation_action
                        or f"Úbytok hmotnosti o {loss_kg} kg — konzultácia s nutricionistom",
                        "severity": escalation_severity,
                    }
                )

        lang = get_lang(request)
        return _cors_json(
            {
                "entries": entries,
                "baseline_weight_kg": baseline,
                "total": len(entries),
                "alerts": alerts,
                "nutrition_escalation": resolve(NUTRITION_ESCALATION, lang),
            }
        )
    except Exception as e:
        record_suppressed_error("api_weight", "fetch", e)
        lang = get_lang(request)
        return _cors_json(
            {
                "error": str(e),
                "entries": [],
                "baseline_weight_kg": baseline,
                "total": 0,
                "alerts": [],
                "nutrition_escalation": resolve(NUTRITION_ESCALATION, lang),
            },
            status_code=502,
        )


async def api_cumulative_dose(request: Request) -> JSONResponse:
    """GET /api/cumulative-dose — cumulative oxaliplatin dose tracking."""
    cycle = PATIENT.current_cycle or 2
    oxa = CUMULATIVE_DOSE_THRESHOLDS["oxaliplatin"]
    dose_per_cycle = oxa["dose_per_cycle"]
    cumulative = cycle * dose_per_cycle

    thresholds_reached = [t for t in oxa["thresholds"] if cumulative >= t["at"]]
    thresholds_upcoming = [t for t in oxa["thresholds"] if cumulative < t["at"]]
    next_threshold = thresholds_upcoming[0] if thresholds_upcoming else None
    pct_to_next = round((cumulative / next_threshold["at"]) * 100, 1) if next_threshold else 100.0

    return _cors_json(
        {
            "drug": "oxaliplatin",
            "unit": oxa["unit"],
            "dose_per_cycle": dose_per_cycle,
            "cycles_counted": cycle,
            "cumulative_mg_m2": cumulative,
            "thresholds_reached": thresholds_reached,
            "next_threshold": next_threshold,
            "pct_to_next": pct_to_next,
            "all_thresholds": oxa["thresholds"],
            "max_recommended": oxa["thresholds"][-1]["at"],
        }
    )


# ── Family update translation helpers ─────────


def _translate_for_family(
    labs: dict | None,
    toxicity: dict | None,
    milestones: list[dict],
    weight_data: dict | None,
    lang: str = "sk",
) -> str:
    """Translate clinical data to plain language for family members."""
    parts: list[str] = []
    cycle = PATIENT.current_cycle or 2

    if lang == "sk":
        parts.append(f"Liečba prebieha — cyklus {cycle} z chemoterapie mFOLFOX6.\n")

        # Labs
        if labs and isinstance(labs, dict):
            anc = labs.get("ANC")
            if anc is not None:
                if anc >= 1500:
                    parts.append("Krvné hodnoty sú v bezpečnom rozsahu pre ďalšiu liečbu.")
                else:
                    parts.append(
                        f"Krvné hodnoty (ANC {anc}) sú nižšie — onkológ rozhodne o ďalšom postupe."
                    )

        # Toxicity
        if toxicity and isinstance(toxicity, dict):
            neuro = toxicity.get("neuropathy", 0)
            if neuro and neuro >= 1:
                parts.append(
                    "Mierne brnenie v prstoch rúk/nôh (bežný vedľajší účinok, sleduje sa)."
                )
            fatigue = toxicity.get("fatigue", 0)
            if fatigue and fatigue >= 2:
                parts.append(
                    "Zvýšená únava — zvláda väčšinu bežných denných aktivít, "
                    "ale rýchlejšie sa unaví."
                )

        # Weight
        if weight_data:
            alerts = weight_data.get("alerts", [])
            if alerts:
                latest = alerts[-1]
                loss_kg = round(
                    (weight_data.get("baseline_weight_kg", 72) - latest["weight_kg"]),
                    1,
                )
                parts.append(f"Úbytok hmotnosti o {loss_kg} kg, konzultácia s nutricionistom.")
            else:
                parts.append("Hmotnosť je stabilná.")

        # Milestones
        if milestones:
            for m in milestones[:2]:
                desc = m.get("description", "")
                if "CT" in desc or "imaging" in desc.lower():
                    parts.append(f"CT vyšetrenie naplánované okolo cyklu {m.get('cycle', '?')}.")
                else:
                    parts.append(f"Míľnik: {desc} (cyklus {m.get('cycle', '?')}).")

    else:
        # English
        parts.append(f"Treatment is ongoing — cycle {cycle} of mFOLFOX6 chemotherapy.\n")

        if labs and isinstance(labs, dict):
            anc = labs.get("ANC")
            if anc is not None:
                if anc >= 1500:
                    parts.append("Blood counts are in a safe range for the next treatment.")
                else:
                    parts.append(
                        f"Blood counts (ANC {anc}) are lower than ideal — "
                        "the oncologist will decide on next steps."
                    )

        if toxicity and isinstance(toxicity, dict):
            neuro = toxicity.get("neuropathy", 0)
            if neuro and neuro >= 1:
                parts.append("Mild tingling in fingers/toes (common side effect, being monitored).")
            fatigue = toxicity.get("fatigue", 0)
            if fatigue and fatigue >= 2:
                parts.append(
                    "Increased fatigue — able to manage most daily activities "
                    "but tires more quickly."
                )

        if weight_data:
            alerts = weight_data.get("alerts", [])
            if alerts:
                latest = alerts[-1]
                parts.append(
                    f"Weight loss of {latest['loss_pct']}% — "
                    "nutritional support consultation recommended."
                )
            else:
                parts.append("Weight is stable.")

        if milestones:
            for m in milestones[:2]:
                desc = m.get("description", "")
                parts.append(f"Upcoming: {desc} (cycle {m.get('cycle', '?')}).")

    return "\n".join(parts)


async def api_family_update(request: Request) -> JSONResponse:
    """GET/POST /api/family-update — weekly family update in plain language.

    GET: list past family updates. Accepts ?lang=sk or ?lang=en.
    POST: generate and store a new family update.
    """
    lang = request.query_params.get("lang", "sk")
    if lang not in ("sk", "en"):
        lang = "sk"

    if request.method == "POST":
        try:
            # Accept optional lang override from body
            body = {}
            raw = await request.body()
            if raw:
                with contextlib.suppress(json.JSONDecodeError):
                    body = json.loads(raw)
            post_lang = body.get("lang", lang)
            if post_lang not in ("sk", "en"):
                post_lang = "sk"

            # Fetch latest data in parallel
            labs_data, toxicity_data, weight_data = None, None, None
            results = await asyncio.gather(
                oncofiles_client.list_treatment_events(event_type="lab_result", limit=1),
                oncofiles_client.list_treatment_events(event_type="toxicity_log", limit=1),
                oncofiles_client.list_treatment_events(event_type="weight_measurement", limit=5),
                return_exceptions=True,
            )

            if not isinstance(results[0], Exception):
                events = _extract_list(results[0], "events")
                if events:
                    meta = events[0].get("metadata", {})
                    if isinstance(meta, str):
                        with contextlib.suppress(json.JSONDecodeError, TypeError):
                            meta = json.loads(meta)
                    labs_data = meta

            if not isinstance(results[1], Exception):
                events = _extract_list(results[1], "events")
                if events:
                    meta = events[0].get("metadata", {})
                    if isinstance(meta, str):
                        with contextlib.suppress(json.JSONDecodeError, TypeError):
                            meta = json.loads(meta)
                    toxicity_data = meta

            # Build simple weight_data for translation
            baseline = PATIENT.baseline_weight_kg or 72.0
            weight_info: dict = {"baseline_weight_kg": baseline, "alerts": []}
            if not isinstance(results[2], Exception):
                for e in _extract_list(results[2], "events"):
                    meta = e.get("metadata", {})
                    if isinstance(meta, str):
                        with contextlib.suppress(json.JSONDecodeError, TypeError):
                            meta = json.loads(meta)
                    w = meta.get("weight_kg")
                    if w is not None:
                        pct = ((w - baseline) / baseline) * 100
                        if pct <= -5:
                            weight_info["alerts"].append(
                                {
                                    "weight_kg": w,
                                    "loss_pct": round(abs(pct), 1),
                                }
                            )
            weight_data = weight_info

            # Get milestones (resolve bilingual descriptions)
            from .clinical_protocol import TREATMENT_MILESTONES

            cycle = PATIENT.current_cycle or 2
            milestones = resolve(
                [m for m in TREATMENT_MILESTONES if m.get("cycle", 0) >= cycle],
                post_lang,
            )

            content = _translate_for_family(
                labs=labs_data,
                toxicity=toxicity_data,
                milestones=milestones,
                weight_data=weight_data,
                lang=post_lang,
            )

            # Store as conversation
            title = "Týždenná správa pre rodinu" if post_lang == "sk" else "Weekly Family Update"
            try:
                await oncofiles_client.log_conversation(
                    title=title,
                    content=content,
                    entry_type="family_update",
                    tags=f"lang:{post_lang}",
                )
            except Exception as store_err:
                record_suppressed_error("api_family_update", "store", store_err)

            return _cors_json({"created": True, "content": content, "lang": post_lang})
        except Exception as e:
            record_suppressed_error("api_family_update", "generate", e)
            return _cors_json({"error": str(e)}, status_code=502)

    # GET: list past family updates
    limit = int(request.query_params.get("limit", "20"))
    try:
        result = await oncofiles_client.search_conversations(
            entry_type="family_update", limit=limit
        )
        entries = _filter_test(_extract_list(result, "entries"), request)
        updates = [
            {
                "id": e.get("id"),
                "title": e.get("title"),
                "content": e.get("content"),
                "date": e.get("created_at"),
                "tags": e.get("tags"),
            }
            for e in entries
        ]
        return _cors_json({"updates": updates, "total": len(updates)})
    except Exception as e:
        record_suppressed_error("api_family_update", "fetch", e)
        return _cors_json({"error": str(e), "updates": [], "total": 0}, status_code=502)


async def api_cors_preflight(request: Request) -> JSONResponse:
    """OPTIONS handler for CORS preflight on all /api/* routes."""
    return _cors_json({})
