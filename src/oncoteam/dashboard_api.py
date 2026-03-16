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
    PARAMETER_HEALTH_DIRECTION,
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
    DASHBOARD_ALLOWED_ORIGINS,
    DASHBOARD_API_KEY,
    GIT_COMMIT,
    MCP_TRANSPORT,
    ONCOFILES_MCP_URL,
)
from .eligibility import assess_research_relevance
from .locale import L, get_lang, resolve
from .patient_context import PATIENT, THERAPY_CATEGORIES, get_patient_localized

VERSION = "0.20.0"

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
    notes = (entry.get("notes") or "").lower()
    if any(p in notes for p in _TEST_TITLE_PATTERNS):
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


def _build_source_ref(entry: dict, entry_type: str) -> dict:
    """Build a source reference dict for any data entry.

    Returns a dict with: type, id, label, url (gdrive/pubmed/clinicaltrials.gov).
    """
    ref: dict = {"type": entry_type, "id": entry.get("id")}
    # Label: use title, filename, or event_type
    ref["label"] = (
        entry.get("title") or entry.get("filename") or entry.get("event_type", entry_type)
    )
    # URL: prefer gdrive_url, then compute from gdrive_file_id, then external_url
    if entry.get("gdrive_url"):
        ref["url"] = entry["gdrive_url"]
    elif entry.get("gdrive_file_id") or entry.get("google_drive_id"):
        gid = entry.get("gdrive_file_id") or entry.get("google_drive_id")
        ref["url"] = f"https://drive.google.com/file/d/{gid}/view"
    elif entry.get("source") and entry.get("external_id"):
        ref["url"] = _build_external_url(entry["source"], entry["external_id"])
    else:
        ref["url"] = None
    return ref


def _get_cors_origin(request: Request) -> str:
    """Return the allowed CORS origin for this request, or empty string."""
    origin = request.headers.get("origin", "")
    if origin in DASHBOARD_ALLOWED_ORIGINS:
        return origin
    # In dev, allow localhost
    if origin.startswith("http://localhost:"):
        return origin
    return ""


_CURRENT_REQUEST: Request | None = None


def _cors_json(
    data: dict, status_code: int = 200, *, request: Request | None = None
) -> JSONResponse:
    """Return JSONResponse with CORS headers for dashboard access."""
    response = JSONResponse(data, status_code=status_code)
    req = request or _CURRENT_REQUEST
    origin = _get_cors_origin(req) if req else ""
    response.headers["Access-Control-Allow-Origin"] = origin or "null"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Vary"] = "Origin"
    return response


def _check_api_auth(request: Request) -> JSONResponse | None:
    """Check API key auth. Returns error response if unauthorized, None if OK."""
    if not DASHBOARD_API_KEY:
        if MCP_TRANSPORT == "stdio":
            return None  # Dev mode: auth disabled for local stdio
        return _cors_json(
            {"error": "DASHBOARD_API_KEY not configured"}, status_code=500, request=request
        )
    auth_header = request.headers.get("authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if token == DASHBOARD_API_KEY:
        return None  # Authorized
    return _cors_json({"error": "Unauthorized"}, status_code=401, request=request)


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
        "get_lab_safety_check",
        "get_precycle_checklist",
    ]
    return _cors_json(
        {
            "status": "ok",
            "server": "oncoteam",
            "version": VERSION,
            "commit": GIT_COMMIT,
            "session_id": get_session_id(),
            "tools_count": len(tools),
            "tools": tools,
        }
    )


async def api_health_deep(request: Request) -> JSONResponse:
    """GET /health/deep — deep health check with dependency status."""
    from .scheduler import _standalone_scheduler

    checks: dict = {"backend": "ok"}

    # Oncofiles connectivity
    try:
        await asyncio.wait_for(
            oncofiles_client.search_activity_log(agent_id="oncoteam", limit=1),
            timeout=5,
        )
        checks["oncofiles"] = "ok"
    except Exception as e:
        checks["oncofiles"] = f"error: {e}"

    # Scheduler status
    if _standalone_scheduler is not None and _standalone_scheduler.running:
        jobs = _standalone_scheduler.get_jobs()
        checks["scheduler"] = {"running": True, "job_count": len(jobs)}
    else:
        checks["scheduler"] = {"running": False, "job_count": 0}

    overall = "ok" if checks["oncofiles"] == "ok" else "degraded"

    return _cors_json(
        {
            "status": overall,
            "version": VERSION,
            "commit": GIT_COMMIT,
            **checks,
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
    """GET /api/stats — aggregated activity statistics.

    Computes stats from filtered activity entries so counts match
    what /api/activity returns (excluding test entries).
    """
    try:
        result = await oncofiles_client.search_activity_log(agent_id="oncoteam", limit=500)
        entries = _filter_test(_extract_list(result, "entries"), request)
        counts: dict[str, dict] = {}
        for e in entries:
            tool = e.get("tool_name") or "unknown"
            if tool not in counts:
                counts[tool] = {
                    "tool_name": tool,
                    "count": 0,
                    "error_count": 0,
                    "total_duration_ms": 0,
                }
            counts[tool]["count"] += 1
            if e.get("status") == "error":
                counts[tool]["error_count"] += 1
            counts[tool]["total_duration_ms"] += e.get("duration_ms") or 0
        stats = sorted(counts.values(), key=lambda s: s["count"], reverse=True)
        return _cors_json({"stats": stats})
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
                        "source": _build_source_ref(e, "treatment_event"),
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
    # Include therapy categories for frontend badge rendering
    data["therapy_categories"] = {
        k: {"label": v["label_en"] if lang == "en" else v["label"], "color": v["color"]}
        for k, v in THERAPY_CATEGORIES.items()
    }
    return _cors_json(data)


_RELEVANCE_SORT_ORDER = {"high": 0, "medium": 1, "low": 2, "not_applicable": 3}


async def api_research(request: Request) -> JSONResponse:
    """GET /api/research — research entries from oncofiles."""
    limit = int(request.query_params.get("limit", "20"))
    source = request.query_params.get("source")
    try:
        result = await oncofiles_client.list_research_entries(source=source, limit=limit)
        entries = _filter_test(_extract_list(result, "entries"), request)
        items = []
        for e in entries:
            rel = assess_research_relevance(
                e.get("title", ""),
                e.get("summary"),
            )
            ext_url = _build_external_url(e.get("source", ""), e.get("external_id", ""))
            items.append(
                {
                    "id": e.get("id"),
                    "source": e.get("source"),
                    "external_id": e.get("external_id"),
                    "title": e.get("title"),
                    "summary": e.get("summary"),
                    "date": e.get("created_at"),
                    "external_url": ext_url,
                    "relevance": rel.score,
                    "relevance_reason": rel.reason,
                    "source_ref": _build_source_ref(e, "research"),
                }
            )
        items.sort(
            key=lambda x: _RELEVANCE_SORT_ORDER.get(
                x["relevance"],
                2,
            )
        )
        return _cors_json({"entries": items, "total": len(items)})
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
                        "source": _build_source_ref(e, "session"),
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
            return _cors_json({"error": "ANTHROPIC_API_KEY not configured"}, status_code=500)

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
                    "citations": len(result.get("citations", [])),
                    "error": result.get("error"),
                    "duration_ms": result.get("duration_ms", 0),
                }
                _logger.info("Trigger %s completed: %s", trigger, _last_trigger_result)
            except Exception as e:
                import traceback

                _last_trigger_result = {
                    "task": trigger,
                    "status": "failed",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
                _logger.error("Trigger %s failed: %s", trigger, e, exc_info=True)

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


async def api_autonomous_status(request: Request) -> JSONResponse:
    """GET /api/autonomous/status — per-task last-run timestamps."""
    from .autonomous_tasks import _extract_timestamp, _get_state

    task_names = [
        "pre_cycle_check",
        "daily_research",
        "file_scan",
        "tumor_marker_review",
        "response_assessment",
        "trial_monitor",
        "weekly_briefing",
        "lab_sync",
        "toxicity_extraction",
        "weight_extraction",
        "family_update",
        "medication_adherence_check",
        "mtb_preparation",
    ]
    tasks = {}
    for name in task_names:
        try:
            state = await _get_state(f"last_{name}")
            ts = _extract_timestamp(state)
            tasks[name] = {"last_run": ts or None}
        except Exception:
            tasks[name] = {"last_run": None}
    return _cors_json({"tasks": tasks})


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
        from .autonomous import _unwrap_agent_state

        raw = await oncofiles_client.get_agent_state("autonomous_mtd_cost")
        state = _unwrap_agent_state(raw)
        if state.get("month") == now.strftime("%Y-%m"):
            mtd_spend = round(float(state.get("cost_usd", 0.0)) + today_spend, 4)
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
    days_remaining = round(remaining_credit / daily_avg, 1) if daily_avg > 0 else 999

    budget_alert = remaining_credit <= ANTHROPIC_BUDGET_ALERT_THRESHOLD

    return _cors_json(
        {
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
        }
    )


async def api_protocol(request: Request) -> JSONResponse:
    """GET /api/protocol — clinical protocol data (thresholds, milestones, dose mods)."""
    from .clinical_protocol import resolve_protocol

    lang = get_lang(request)
    data = resolve_protocol(lang)

    # Fetch lab values + treatment events concurrently with 5s timeout (#63 perf fix)
    import asyncio

    try:
        lab_result, events_result = await asyncio.wait_for(
            asyncio.gather(
                oncofiles_client.list_treatment_events(event_type="lab_result", limit=1),
                oncofiles_client.list_treatment_events(limit=50),
                return_exceptions=True,
            ),
            timeout=5.0,
        )
    except TimeoutError:
        record_suppressed_error("api_protocol", "oncofiles_timeout", TimeoutError("5s"))
        lab_result = TimeoutError("oncofiles timeout")
        events_result = TimeoutError("oncofiles timeout")

    # Process lab values for threshold status display
    last_lab_values: dict[str, dict] = {}
    if not isinstance(lab_result, BaseException):
        try:
            events = _extract_list(lab_result, "events")
            if events:
                latest = events[0]
                meta = latest.get("metadata", {})
                if isinstance(meta, str):
                    with contextlib.suppress(json.JSONDecodeError, TypeError):
                        meta = json.loads(meta)
                lab_date = latest.get("event_date", "")
                for param, threshold in LAB_SAFETY_THRESHOLDS.items():
                    if param not in meta:
                        continue
                    val = meta[param]
                    if not isinstance(val, (int, float)):
                        continue
                    status = "safe"
                    if "min" in threshold:
                        if val < threshold["min"]:
                            status = "critical"
                        elif val < threshold["min"] * 1.2:
                            status = "warning"
                    elif "max_ratio" in threshold:
                        pass
                    last_lab_values[param] = {
                        "value": val,
                        "sample_date": lab_date,
                        "sync_date": latest.get("created_at", ""),
                        "status": status,
                    }
        except Exception as e:
            record_suppressed_error("api_protocol", "fetch_last_labs", e)
    elif isinstance(lab_result, Exception):
        record_suppressed_error("api_protocol", "fetch_last_labs", lab_result)

    # Fallback: if no lab_result treatment events, try lab_values table (#72/#73)
    # Map stored parameter names → threshold keys
    _param_to_threshold = {
        "ABS_NEUT": "ANC",
        "ANC": "ANC",
        "PLT": "PLT",
        "CREATININE": "creatinine",
        "creatinine": "creatinine",
        "ALT": "ALT",
        "AST": "AST",
        "HGB": "HGB",
        "WBC": "WBC",
        "bilirubin": "bilirubin",
    }
    if not last_lab_values:
        try:
            trends = await asyncio.wait_for(
                oncofiles_client.get_lab_trends_data(limit=200),
                timeout=5.0,
            )
            values_list = _extract_list(trends, "values")
            if values_list:
                # Group by date, pick latest
                from collections import defaultdict

                by_date: dict[str, dict] = defaultdict(dict)
                for v in values_list:
                    d = v.get("lab_date", "")
                    if d:
                        by_date[d][v.get("parameter", "")] = v.get("value")
                if by_date:
                    latest_date = max(by_date.keys())
                    latest_vals = by_date[latest_date]
                    for stored_name, val in latest_vals.items():
                        threshold_key = _param_to_threshold.get(stored_name)
                        if not threshold_key or not isinstance(val, (int, float)):
                            continue
                        threshold = LAB_SAFETY_THRESHOLDS.get(threshold_key, {})
                        status = "safe"
                        if "min" in threshold:
                            if val < threshold["min"]:
                                status = "critical"
                            elif val < threshold["min"] * 1.2:
                                status = "warning"
                        last_lab_values[threshold_key] = {
                            "value": val,
                            "sample_date": latest_date,
                            "sync_date": "",
                            "status": status,
                        }
        except (TimeoutError, Exception) as e:
            record_suppressed_error("api_protocol", "fallback_lab_trends", e)

    data["last_lab_values"] = last_lab_values

    # Process real values for other tabs (#54)
    real_values: dict[str, dict] = {}
    if not isinstance(events_result, BaseException):
        all_events = _extract_list(events_result, "events")

        # Dose modifications: check for any dose reduction events
        dose_events = [
            e
            for e in all_events
            if "dose" in (e.get("title") or "").lower() or "reduk" in (e.get("title") or "").lower()
        ]
        if dose_events:
            real_values["dose_modifications"] = {
                "last_change": dose_events[0].get("title", ""),
                "date": dose_events[0].get("event_date", ""),
            }

        # Current dose level from patient context
        real_values["current_regimen"] = {
            "regimen": PATIENT.treatment_regimen,
            "cycle": PATIENT.current_cycle,
        }

        # Nutrition: latest weight from weight events
        weight_events = [
            e
            for e in all_events
            if e.get("event_type") == "weight"
            or "weight" in (e.get("title") or "").lower()
            or "váha" in (e.get("title") or "").lower()
        ]
        if weight_events:
            meta = weight_events[0].get("metadata", {})
            if isinstance(meta, str):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    meta = json.loads(meta)
            weight = meta.get("weight_kg") or meta.get("weight")
            if weight:
                real_values["nutrition"] = {
                    "weight_kg": weight,
                    "date": weight_events[0].get("event_date", ""),
                    "baseline_kg": PATIENT.baseline_weight_kg,
                }
    elif isinstance(events_result, Exception):
        record_suppressed_error("api_protocol", "fetch_real_values", events_result)

    data["real_values"] = real_values
    return _cors_json(data)


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


def _briefing_summary(content: str) -> dict:
    """Extract a 2-line summary and action item count from briefing content."""
    lines = content.split("\n") if content else []
    summary_lines: list[str] = []
    action_count = 0
    in_questions = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if low.startswith("#"):
            in_questions = "question" in low or "action" in low
            continue
        if in_questions and stripped.startswith("-"):
            action_count += 1
            continue
        if len(summary_lines) < 2 and not stripped.startswith("-"):
            summary_lines.append(stripped)
    return {
        "summary": " ".join(summary_lines)[:200],
        "action_count": action_count,
    }


async def api_briefings(request: Request) -> JSONResponse:
    """GET /api/briefings — autonomous briefings + cost alerts from oncofiles diary."""
    limit = int(request.query_params.get("limit", "20"))
    try:
        briefings_res, alerts_res = await asyncio.gather(
            oncofiles_client.search_conversations(entry_type="autonomous_briefing", limit=limit),
            oncofiles_client.search_conversations(entry_type="cost_alert", limit=5),
            return_exceptions=True,
        )
        briefings = (
            _extract_list(briefings_res, "entries") if isinstance(briefings_res, dict) else []
        )
        alerts = _extract_list(alerts_res, "entries") if isinstance(alerts_res, dict) else []
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
                        **_briefing_summary(e.get("content", "")),
                        "source": _build_source_ref(e, "briefing"),
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
                        "source": _build_source_ref(e, "toxicity"),
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

        # Fallback 1: try lab_values table (structured numeric data)
        if not events:
            try:
                trends = await oncofiles_client.get_lab_trends_data(limit=200)
                values_list = _extract_list(trends, "values")
                if values_list:
                    # Group by lab_date → single entry per date
                    from collections import defaultdict

                    by_date: dict[str, dict] = defaultdict(lambda: {"metadata": {}, "notes": ""})
                    for v in values_list:
                        d = v.get("lab_date", "")
                        if not d:
                            continue
                        by_date[d]["metadata"][v["parameter"]] = v["value"]
                        by_date[d]["document_id"] = v.get("document_id")
                    for d, data in by_date.items():
                        events.append(
                            {
                                "event_date": d,
                                "metadata": data["metadata"],
                                "notes": data.get("notes", ""),
                                "id": data.get("document_id"),
                            }
                        )
            except Exception as fallback_err:
                record_suppressed_error("api_labs", "lab_trends_fallback", fallback_err)

        # Fallback 2: try analyze_labs (unstructured document analysis)
        if not events:
            try:
                analysis = await oncofiles_client.analyze_labs(limit=limit)
                if isinstance(analysis, dict):
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

        # Sort events by date descending (newest first)
        events.sort(key=lambda e: e.get("event_date", ""), reverse=True)

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
                    "sync_date": e.get("created_at", ""),
                    "values": meta,
                    "notes": e.get("notes"),
                    "alerts": alerts,
                    "value_statuses": value_statuses,
                    "source": _build_source_ref(e, "lab"),
                }
            )

        # Compute direction (vs previous entry) and health_direction per parameter
        for i, entry in enumerate(entries):
            directions: dict[str, str] = {}
            health_dirs: dict[str, str] = {}
            prev = entries[i + 1] if i + 1 < len(entries) else None
            for param, val in entry["values"].items():
                if not isinstance(val, (int, float)):
                    continue
                if prev and param in prev["values"]:
                    prev_val = prev["values"][param]
                    if isinstance(prev_val, (int, float)):
                        if val > prev_val:
                            directions[param] = "up"
                        elif val < prev_val:
                            directions[param] = "down"
                        else:
                            directions[param] = "stable"
                        # Determine health direction
                        health = PARAMETER_HEALTH_DIRECTION.get(param, "in_range")
                        if directions[param] == "stable":
                            health_dirs[param] = "stable"
                        elif health == "lower_is_better":
                            health_dirs[param] = (
                                "improving" if directions[param] == "down" else "worsening"
                            )
                        elif health == "higher_is_better":
                            health_dirs[param] = (
                                "improving" if directions[param] == "up" else "worsening"
                            )
                        else:
                            # in_range: check if moving toward or away from range
                            ref = LAB_REFERENCE_RANGES.get(param)
                            if ref:
                                mid = (ref["min"] + ref["max"]) / 2
                                health_dirs[param] = (
                                    "improving"
                                    if abs(val - mid) < abs(prev_val - mid)
                                    else "worsening"
                                )
                            else:
                                health_dirs[param] = "stable"
            entry["directions"] = directions
            entry["health_directions"] = health_dirs

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
            # Add relevance assessment
            rel = assess_research_relevance(
                data.get("title", ""),
                data.get("summary"),
            )
            data["relevance"] = rel.score
            data["relevance_reason"] = rel.reason

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
            # Prefer gdrive_url from oncofiles v3.11+ response; fallback to computing from ID
            if data.get("gdrive_url"):
                source["gdrive_url"] = data["gdrive_url"]
            else:
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
            lang = get_lang(request)
            sections = {
                "lab_thresholds": LAB_SAFETY_THRESHOLDS,
                "dose_modifications": resolve(DOSE_MODIFICATION_RULES, lang),
                "milestones": resolve(TREATMENT_MILESTONES, lang),
                "monitoring_schedule": resolve(MONITORING_SCHEDULE, lang),
                "safety_flags": resolve(SAFETY_FLAGS, lang),
                "second_line_options": resolve(SECOND_LINE_OPTIONS, lang),
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

    # Check if lab_result data is stale (>48h since last lab_result event)
    lab_sync_stale = False
    te_check = next((c for c in checks if c["name"] == "treatment_events"), None)
    if te_check and te_check.get("ok"):
        try:
            lab_events = await oncofiles_client.list_treatment_events(
                event_type="lab_result", limit=1
            )
            events = _extract_list(lab_events, "events")
            if events:
                from datetime import UTC, datetime

                created = events[0].get("created_at", "")
                if created:
                    # Parse ISO timestamp (with or without Z suffix)
                    ts = created.replace("Z", "+00:00")
                    last_sync = datetime.fromisoformat(ts)
                    age_hours = (datetime.now(UTC) - last_sync).total_seconds() / 3600
                    lab_sync_stale = age_hours > 48
            else:
                # No lab_result events at all — stale
                lab_sync_stale = True
        except Exception as e:
            record_suppressed_error("api_diagnostics", "lab_sync_check", e)

    return _cors_json(
        {
            "healthy": all(c["ok"] for c in checks),
            "checks": checks,
            "oncofiles_url": (ONCOFILES_MCP_URL[:30] + "...") if ONCOFILES_MCP_URL else "NOT SET",
            "autonomous_enabled": AUTONOMOUS_ENABLED,
            "lab_sync_stale": lab_sync_stale,
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
                    "source": _build_source_ref(e, "medication"),
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
    lang = get_lang(request)
    cycle = PATIENT.current_cycle or 2
    oxa = resolve(CUMULATIVE_DOSE_THRESHOLDS["oxaliplatin"], lang)
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
    return _cors_json({}, request=request)
