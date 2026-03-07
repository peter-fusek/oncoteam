"""Dashboard API: JSON endpoints for the web dashboard and future channels."""

from __future__ import annotations

import asyncio
import contextlib
import json

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import oncofiles_client
from .activity_logger import get_session_id, record_suppressed_error
from .clinical_protocol import (
    DOSE_MODIFICATION_RULES,
    LAB_SAFETY_THRESHOLDS,
    MONITORING_SCHEDULE,
    SAFETY_FLAGS,
    SECOND_LINE_OPTIONS,
    TREATMENT_MILESTONES,
    WATCHED_TRIALS,
)
from .config import AUTONOMOUS_ENABLED
from .patient_context import PATIENT

VERSION = "0.7.0"

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
    data = PATIENT.model_dump()
    # Convert date objects to strings for JSON
    if data.get("diagnosis_date"):
        data["diagnosis_date"] = str(data["diagnosis_date"])
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

    # Manual trigger via ?trigger=<task_name>
    trigger = request.query_params.get("trigger")
    if trigger:
        from . import autonomous_tasks

        task_fn = getattr(autonomous_tasks, f"run_{trigger}", None)
        if task_fn is None:
            return _cors_json({"error": f"Unknown task: {trigger}"}, status_code=400)
        # Run in background, return immediately
        asyncio.create_task(task_fn())
        return _cors_json({"triggered": trigger, "status": "started"})

    # Default: return scheduler status
    data: dict = {
        "enabled": AUTONOMOUS_ENABLED,
        "daily_cost": round(get_daily_cost(), 4),
    }

    if AUTONOMOUS_ENABLED:
        try:
            # Try to get scheduler state from any running instance
            # Jobs are registered at startup, we report their config
            jobs = [
                {
                    "id": "pre_cycle_check",
                    "schedule": "every 13 days",
                    "description": "Pre-cycle FOLFOX safety check",
                },
                {
                    "id": "tumor_marker_review",
                    "schedule": "every 4 weeks",
                    "description": "CEA/CA 19-9 trend analysis",
                },
                {
                    "id": "response_assessment",
                    "schedule": "every 8 weeks",
                    "description": "RECIST response evaluation",
                },
                {
                    "id": "daily_research",
                    "schedule": "daily 07:00 UTC",
                    "description": "PubMed research scan",
                },
                {
                    "id": "trial_monitor",
                    "schedule": "every 6 hours",
                    "description": "Clinical trial monitoring",
                },
                {
                    "id": "file_scan",
                    "schedule": "every 2 hours",
                    "description": "New document scan",
                },
                {
                    "id": "weekly_briefing",
                    "schedule": "Monday 06:00 UTC",
                    "description": "Weekly physician briefing",
                },
                {
                    "id": "mtb_preparation",
                    "schedule": "Friday 14:00 UTC",
                    "description": "Tumor board preparation",
                },
            ]
            data["jobs"] = jobs
            data["job_count"] = len(jobs)
        except Exception:
            data["jobs"] = []
            data["job_count"] = 0

    return _cors_json(data)


async def api_protocol(request: Request) -> JSONResponse:
    """GET /api/protocol — clinical protocol data (thresholds, milestones, dose mods)."""
    return _cors_json(
        {
            "lab_thresholds": LAB_SAFETY_THRESHOLDS,
            "dose_modifications": DOSE_MODIFICATION_RULES,
            "milestones": TREATMENT_MILESTONES,
            "monitoring_schedule": MONITORING_SCHEDULE,
            "safety_flags": SAFETY_FLAGS,
            "second_line_options": SECOND_LINE_OPTIONS,
            "watched_trials": WATCHED_TRIALS,
            "current_cycle": PATIENT.current_cycle,
        }
    )


async def api_briefings(request: Request) -> JSONResponse:
    """GET /api/briefings — autonomous briefings from oncofiles diary."""
    limit = int(request.query_params.get("limit", "20"))
    try:
        result = await oncofiles_client.search_conversations(
            entry_type="autonomous_briefing",
            limit=limit,
        )
        entries = _filter_test(_extract_list(result, "entries"), request)
        return _cors_json(
            {
                "briefings": [
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

        # Extract values and check against safety thresholds
        entries = []
        for e in events:
            meta = e.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    meta = {}
            alerts = []
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
            entries.append(
                {
                    "id": e.get("id"),
                    "date": e.get("event_date"),
                    "values": meta,
                    "notes": e.get("notes"),
                    "alerts": alerts,
                }
            )

        return _cors_json({"entries": entries, "total": len(entries)})
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


async def api_cors_preflight(request: Request) -> JSONResponse:
    """OPTIONS handler for CORS preflight on all /api/* routes."""
    return _cors_json({})
