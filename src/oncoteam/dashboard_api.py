"""Dashboard API: JSON endpoints for the web dashboard and future channels."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import oncofiles_client
from .activity_logger import get_session_id, record_suppressed_error
from .patient_context import PATIENT

VERSION = "0.6.0"

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
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


async def api_status(request: Request) -> JSONResponse:
    """GET /api/status — server status and config."""
    tools = [
        "search_pubmed", "search_clinical_trials", "search_clinical_trials_adjacent",
        "fetch_pubmed_article", "fetch_trial_details", "check_trial_eligibility",
        "daily_briefing", "get_lab_trends", "search_documents", "get_patient_context",
        "view_document", "analyze_labs", "compare_labs", "log_research_decision",
        "log_session_note", "summarize_session", "review_session",
        "create_improvement_issue",
    ]
    return _cors_json({
        "status": "ok",
        "server": "oncoteam",
        "version": VERSION,
        "session_id": get_session_id(),
        "tools_count": len(tools),
        "tools": tools,
    })


async def api_activity(request: Request) -> JSONResponse:
    """GET /api/activity — recent activity log entries."""
    limit = int(request.query_params.get("limit", "50"))
    try:
        result = await oncofiles_client.search_activity_log(
            agent_id="oncoteam", limit=limit
        )
        entries = _filter_test(_extract_list(result, "entries"), request)
        return _cors_json({
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
        })
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
        return _cors_json({
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
        })
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
        result = await oncofiles_client.list_research_entries(
            source=source, limit=limit
        )
        entries = _filter_test(_extract_list(result, "entries"), request)
        return _cors_json({
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
        })
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
        return _cors_json({
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
        })
    except Exception as e:
        record_suppressed_error("api_sessions", "fetch", e)
        return _cors_json({"error": str(e), "sessions": [], "total": 0}, status_code=502)


async def api_cors_preflight(request: Request) -> JSONResponse:
    """OPTIONS handler for CORS preflight on all /api/* routes."""
    return _cors_json({})
