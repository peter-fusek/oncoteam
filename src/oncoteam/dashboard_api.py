"""Dashboard API: JSON endpoints for the web dashboard and future channels."""

from __future__ import annotations

import asyncio
import collections
import contextlib
import contextvars
import json
import logging
import re
import resource
import sys
import time

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import oncofiles_client
from .activity_logger import get_session_id, record_suppressed_error
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
    DASHBOARD_ALLOWED_ORIGINS,
    DASHBOARD_API_KEY,
    FUP_AGENT_RUNS_PER_MONTH,
    FUP_AI_QUERIES_PER_MONTH,
    FUP_ONCOFILES_DOCUMENTS,
    GIT_COMMIT,
    MCP_TRANSPORT,
)
from .eligibility import assess_research_relevance
from .locale import get_lang, resolve
from .patient_context import (
    DEFAULT_PATIENT_ID,
    THERAPY_CATEGORIES,
    get_patient,
    get_patient_localized,
)
from .request_context import (
    get_correlation_id,
)
from .request_context import (
    get_token_for_patient as _get_token_for_patient,
)
from .request_context import (
    new_correlation_id as _new_correlation_id,
)
from .request_context import (
    set_correlation_id as _set_correlation_id,
)

VERSION = "0.81.0"

_logger = logging.getLogger("oncoteam.dashboard_api")


def _circuit_breaker_503(fallback_data: dict) -> JSONResponse | None:
    """Return 503 response if circuit breaker is open, else None."""
    cb = oncofiles_client.get_circuit_breaker_status()
    if cb["state"] == "open":
        return _cors_json(
            {
                "error": "Database temporarily unavailable. Try again in a minute.",
                "unavailable": True,
                **fallback_data,
            },
            status_code=503,
        )
    return None


# _last_trigger_result moved to api_agents.py

# Patterns that identify test/E2E data created by automated tests
_TEST_TITLE_PATTERNS = ("e2e-test-", "e2e test", "testovacia")
_TEST_TOOL_NAMES = ("e2e_test",)
_TEST_AGENT_IDS = ("oncoteam-e2e",)
_TEST_TAGS = ("e2e-test",)
# Known contaminated event IDs (E2E test data that leaked into production — #85)
# IDs 19-21: manually entered placeholder labs with CEA/CA19-9 values 100-1000x too low
#   vs PDF-confirmed values. Feb 20 CEA=8.4 but Feb 27 PDF confirms CEA=1559.5. (#116)
# ID 32: duplicate of ID 27 (same Feb 27 labs, same values)
_CONTAMINATED_EVENT_IDS = {19, 20, 21, 22, 23, 24, 32}


_KNOWN_LAB_PARAMS = frozenset(
    {
        "WBC",
        "ANC",
        "ABS_NEUT",
        "ABS_LYMPH",
        "PLT",
        "hemoglobin",
        "HGB",
        "creatinine",
        "ALT",
        "AST",
        "bilirubin",
        "CEA",
        "CA_19_9",
        "neutrophils_pct",
        "lymphocytes_pct",
        "monocytes_pct",
        "NEUT_pct",
        "GMT_ukat_l",
        "ALP_ukat_l",
        "SII",
        "post_op_day",
        "document_id",
    }
)


def _normalize_lab_values(meta: dict) -> dict:
    """Normalize lab parameter names and units.

    - Strips non-lab keys (e.g. 'dates_processed' from workflow artifacts)
    - Maps ABS_NEUT → ANC (canonical name)
    - Detects ANC in G/L (< 30) and converts to /µL (* 1000)
    - Detects PLT in G/L (< 1000) and converts to /µL (* 1000)
    - Detects WBC in G/L (< 100) and converts to ×10³/µL (keep as-is, already correct)
    - Detects hemoglobin aliases (HGB → hemoglobin)
    """
    # Strip non-lab keys (workflow artifacts like dates_processed)
    unknown_keys = [k for k in meta if k not in _KNOWN_LAB_PARAMS]
    for k in unknown_keys:
        del meta[k]

    # Parameter name aliases
    if "ABS_NEUT" in meta and "ANC" not in meta:
        meta["ANC"] = meta.pop("ABS_NEUT")
    if "HGB" in meta and "hemoglobin" not in meta:
        meta["hemoglobin"] = meta.pop("HGB")

    # Unit conversions: G/L → /µL
    if "ANC" in meta and isinstance(meta["ANC"], (int, float)) and meta["ANC"] < 30:
        meta["ANC"] = round(meta["ANC"] * 1000)  # G/L → /µL
    if "PLT" in meta and isinstance(meta["PLT"], (int, float)) and meta["PLT"] < 1000:
        meta["PLT"] = round(meta["PLT"] * 1000)  # G/L → /µL (e.g., 587 → 587000)
    if (
        "ABS_LYMPH" in meta
        and isinstance(meta["ABS_LYMPH"], (int, float))
        and meta["ABS_LYMPH"] < 30
    ):
        meta["ABS_LYMPH"] = round(meta["ABS_LYMPH"] * 1000)  # G/L → /µL
    return meta


def _is_test_entry(entry: dict) -> bool:
    """Return True if the entry looks like test/E2E data."""
    # Blocklist of known contaminated event IDs (#85)
    eid = entry.get("id")
    if isinstance(eid, int) and eid in _CONTAMINATED_EVENT_IDS:
        return True
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


def _get_patient_id(request: Request) -> str:
    """Extract patient_id from query params. Defaults to Erika."""
    return request.query_params.get("patient_id", DEFAULT_PATIENT_ID)


def _get_patient_for_request(request: Request):
    """Get PatientProfile for the request's patient_id. Falls back to default."""
    pid = _get_patient_id(request)
    return get_patient(pid)


# _get_token_for_patient — moved to request_context.py, imported above.


def _extract_output_data(tool_name: str | None, output_str: str | None) -> dict | None:
    """Parse structured output_data from a tool's output_summary string.

    Returns a summary dict for known tools, or the parsed JSON for others.
    Returns None if the output cannot be parsed as JSON.
    """
    if not output_str or not isinstance(output_str, str):
        return None

    # Try to parse JSON from the output string
    parsed = None
    # Some outputs are plain JSON
    with contextlib.suppress(json.JSONDecodeError, TypeError, ValueError):
        parsed = json.loads(output_str)

    tool = (tool_name or "").lower()

    if tool == "search_pubmed" and parsed:
        articles = parsed if isinstance(parsed, list) else parsed.get("articles", [])
        if isinstance(articles, list):
            top_title = articles[0].get("title", "") if articles else ""
            return {"articles_count": len(articles), "top_title": top_title}

    trial_tools = ("search_trials", "search_clinical_trials_adjacent", "search_clinical_trials_eu")
    if tool in trial_tools and parsed:
        trials = parsed if isinstance(parsed, list) else parsed.get("trials", [])
        if isinstance(trials, list):
            return {"trials_count": len(trials)}

    if tool == "check_trial_eligibility" and parsed and isinstance(parsed, dict):
        return {
            "eligible": parsed.get("eligible"),
            "reason": parsed.get("reason", parsed.get("summary", "")),
        }

    # For any other tool with valid parsed JSON, return it directly
    if parsed is not None:
        return parsed

    return None


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


# Keywords for classifying sessions as technical vs clinical
_TECHNICAL_KEYWORDS = (
    "deploy",
    "sprint",
    "debug",
    "ci/cd",
    "ci pipeline",
    "migration",
    "refactor",
    "infra",
    "railway",
    "dockerfile",
    "eslint",
    "ruff",
    "github action",
    "pipeline",
    "pr review",
    "pull request",
    "nuxt",
    "dashboard bug",
    "pnpm",
    "typescript",
    "vue",
    "api endpoint",
    "503",
    "timeout",
    "semaphore",
    "proxy",
    "backend",
    "frontend",
    "css",
    "build",
    "commit",
    "git",
    "branch",
    "merge",
    "linting",
    "formatting",
    "env var",
    "bug fix",
    "code review",
)
_CLINICAL_KEYWORDS = (
    "chemo",
    "toxicity",
    "briefing",
    "cycle",
    "folfox",
    "cea",
    "anc",
    "onkolog",
    "vysetrenie",
    "kontrola",
    "pacient",
    "liecba",
    "neuropathy",
    "nausea",
    "diarrhea",
    "pubmed",
    "trial",
    "biomarker",
    "dose",
    "lab result",
    "hemoglobin",
    "platelet",
    "tumor marker",
    "kras",
    "braf",
    "egfr",
    "msi",
    "staging",
    "metast",
    "oncologist",
    "pre-cycle",
    "adverse event",
)
# Tags that strongly indicate technical sessions
_TECHNICAL_TAG_PREFIXES = ("sys:", "task:deploy", "task:sprint", "task:fix", "task:refactor")


def _classify_session_type(entry: dict) -> str:
    """Classify a session as 'clinical' or 'technical'.

    Uses keyword matching in title (2x weight) and content (first 500 chars).
    Tags with sys: or task: prefixes strongly indicate technical sessions.
    """
    title = (entry.get("title") or "").lower()
    content = (entry.get("content") or "").lower()
    tags = entry.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    # Tag-based strong signal
    tag_text = " ".join(str(t).lower() for t in tags)
    for prefix in _TECHNICAL_TAG_PREFIXES:
        if prefix in tag_text:
            return "technical"
    # Clinical tag signal
    if any(t.lower().startswith("clin:") or t.lower().startswith("bio:") for t in tags):
        return "clinical"

    # Keyword scoring: title counts double
    title_text = title
    body_text = content[:500]
    tech_hits = sum(2 for kw in _TECHNICAL_KEYWORDS if kw in title_text)
    tech_hits += sum(1 for kw in _TECHNICAL_KEYWORDS if kw in body_text)
    clin_hits = sum(2 for kw in _CLINICAL_KEYWORDS if kw in title_text)
    clin_hits += sum(1 for kw in _CLINICAL_KEYWORDS if kw in body_text)

    if tech_hits > clin_hits:
        return "technical"
    # Default to clinical when unclear or tied
    return "clinical"


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


def _build_external_url(source: str, external_id: str, raw_data: str = "") -> str | None:
    """Build external URL for PubMed/ClinicalTrials.gov/ESMO entries."""
    if source == "pubmed" and external_id:
        return f"https://pubmed.ncbi.nlm.nih.gov/{external_id}/"
    if source == "clinicaltrials" and external_id:
        return f"https://clinicaltrials.gov/study/{external_id}"
    # Fallback: extract first URL from raw_data (e.g. ESMO entries)
    if raw_data:
        m = re.search(r"https?://[^\s|]+", raw_data)
        if m:
            return m.group(0)
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


_CURRENT_REQUEST: contextvars.ContextVar[Request | None] = contextvars.ContextVar(
    "_CURRENT_REQUEST", default=None
)

# ── Request correlation ID ─────────────────────────────────────────────
# Moved to request_context.py — imported above for backward compat.


# _parse_agent_run_entry moved to api_agents.py — re-exported at bottom of file


MAX_REQUEST_BODY_BYTES = 1_000_000  # 1 MB — prevents oversized POST payloads


async def _parse_json_body(request: Request) -> dict:
    """Parse JSON body with size limit. Raises ValueError if too large."""
    body = await request.body()
    if len(body) > MAX_REQUEST_BODY_BYTES:
        raise ValueError(
            f"Request body too large ({len(body)} bytes, max {MAX_REQUEST_BODY_BYTES})"
        )
    return json.loads(body)


def _parse_limit(request: Request, default: int = 50, max_val: int = 500) -> int:
    """Parse and cap `limit` query param. Safe against non-integer values."""
    try:
        return max(1, min(max_val, int(request.query_params.get("limit", str(default)))))
    except (ValueError, TypeError):
        return default


def _cors_json(
    data: dict, status_code: int = 200, *, request: Request | None = None
) -> JSONResponse:
    """Return JSONResponse with CORS headers for dashboard access."""
    if isinstance(data, dict) and "last_updated" not in data:
        from datetime import UTC
        from datetime import datetime as _dt

        data["last_updated"] = _dt.now(UTC).isoformat()
    response = JSONResponse(data, status_code=status_code)
    req = request or _CURRENT_REQUEST.get()
    origin = _get_cors_origin(req) if req else ""
    response.headers["Access-Control-Allow-Origin"] = origin or ""
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Vary"] = "Origin"
    cid = get_correlation_id()
    if cid:
        response.headers["X-Correlation-ID"] = cid
    return response


def _check_api_auth(request: Request) -> JSONResponse | None:
    """Check API key auth. Returns error response if unauthorized, None if OK.

    Also generates a correlation ID for this request and stores it in ContextVar.
    """
    # Generate correlation ID for every request (even failed auth)
    _set_correlation_id(_new_correlation_id())

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
        pid = request.query_params.get("patient_id", "global")
        if not _check_rate_limit(pid):
            return _cors_json({"error": "Rate limit exceeded"}, status_code=429, request=request)
        return None  # Authorized
    return _cors_json({"error": "Unauthorized"}, status_code=401, request=request)


# ── Rate limiter ─────────────────────────────────
# Two-tier sliding window: general API + strict limit for expensive endpoints
# that trigger Claude API calls (WhatsApp chat, agent triggers, document pipeline).
# Per-patient keyed + global safety valve.
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 120  # per-patient requests per window
_RATE_LIMIT_GLOBAL_MAX = 600  # global safety valve across all patients
_rate_timestamps: dict[str, collections.deque] = {}
_rate_global: collections.deque = collections.deque()

# Expensive endpoints: Claude API calls cost real money
_EXPENSIVE_RATE_WINDOW = 300  # 5 minutes
_EXPENSIVE_RATE_MAX = 10  # max 10 Claude API calls per 5 min
_expensive_timestamps: collections.deque = collections.deque()


def _check_rate_limit(patient_id: str = "global") -> bool:
    """Return True if within rate limit, False if exceeded.

    Checks per-patient limit and global safety valve.
    """
    now = time.time()

    # Check global safety valve (don't append yet — TOCTOU fix #201)
    cutoff = now - _RATE_LIMIT_WINDOW
    while _rate_global and _rate_global[0] < cutoff:
        _rate_global.popleft()
    if len(_rate_global) >= _RATE_LIMIT_GLOBAL_MAX:
        return False

    # Check per-patient limit (don't append yet)
    if patient_id not in _rate_timestamps:
        _rate_timestamps[patient_id] = collections.deque()
    dq = _rate_timestamps[patient_id]
    while dq and dq[0] < cutoff:
        dq.popleft()
    if len(dq) >= _RATE_LIMIT_MAX:
        return False

    # Both checks passed — now record
    _rate_global.append(now)
    dq.append(now)
    return True


def _check_expensive_rate_limit() -> bool:
    """Strict rate limit for endpoints that trigger Claude API calls."""
    now = time.time()
    cutoff = now - _EXPENSIVE_RATE_WINDOW
    while _expensive_timestamps and _expensive_timestamps[0] < cutoff:
        _expensive_timestamps.popleft()
    if len(_expensive_timestamps) >= _EXPENSIVE_RATE_MAX:
        return False
    _expensive_timestamps.append(now)
    return True


# ── FUP (Fair Use Policy) — per-patient monthly counters ─────────────

_fup_ai_queries: dict[str, int] = {}  # "patient_id:month" → count
_fup_agent_runs: dict[str, int] = {}


def _fup_month_key() -> str:
    """Current month key for FUP tracking, e.g. '2026-03'."""
    from datetime import UTC
    from datetime import datetime as _dt

    return _dt.now(UTC).strftime("%Y-%m")


def _fup_key(patient_id: str = "") -> str:
    """Build per-patient FUP key: '{patient_id}:{month}' or 'global:{month}'."""
    pid = patient_id.strip() if patient_id else "global"
    return f"{pid}:{_fup_month_key()}"


def _check_fup_ai_query(patient_id: str = "") -> bool:
    """Record an AI query and return True if within FUP limit."""
    month = _fup_month_key()
    key = _fup_key(patient_id)
    count = _fup_ai_queries.get(key, 0)
    if count >= FUP_AI_QUERIES_PER_MONTH:
        return False
    _fup_ai_queries[key] = count + 1
    # Clean old months (any key not ending with current month)
    for k in list(_fup_ai_queries):
        if not k.endswith(f":{month}"):
            del _fup_ai_queries[k]
    return True


def _check_fup_agent_run(patient_id: str = "") -> bool:
    """Record an agent run and return True if within FUP limit."""
    month = _fup_month_key()
    key = _fup_key(patient_id)
    count = _fup_agent_runs.get(key, 0)
    if count >= FUP_AGENT_RUNS_PER_MONTH:
        return False
    _fup_agent_runs[key] = count + 1
    for k in list(_fup_agent_runs):
        if not k.endswith(f":{month}"):
            del _fup_agent_runs[k]
    return True


def _get_fup_status() -> dict:
    """Return current FUP usage for the /api/status endpoint, with per-patient breakdown."""
    month = _fup_month_key()
    # Aggregate per-patient breakdown for current month
    ai_breakdown: dict[str, int] = {}
    agent_breakdown: dict[str, int] = {}
    for k, v in _fup_ai_queries.items():
        if k.endswith(f":{month}"):
            pid = k.rsplit(":", 1)[0]
            ai_breakdown[pid] = v
    for k, v in _fup_agent_runs.items():
        if k.endswith(f":{month}"):
            pid = k.rsplit(":", 1)[0]
            agent_breakdown[pid] = v
    ai_total = sum(ai_breakdown.values())
    agent_total = sum(agent_breakdown.values())
    return {
        "month": month,
        "ai_queries": {
            "used": ai_total,
            "limit": FUP_AI_QUERIES_PER_MONTH,
            "per_patient": ai_breakdown,
        },
        "agent_runs": {
            "used": agent_total,
            "limit": FUP_AGENT_RUNS_PER_MONTH,
            "per_patient": agent_breakdown,
        },
        "oncofiles_documents": {"limit": FUP_ONCOFILES_DOCUMENTS, "note": "enforced by oncofiles"},
    }


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
        checks["oncofiles"] = (
            f"error: {type(e).__name__}: {e}" if str(e) else f"error: {type(e).__name__}"
        )

    # Scheduler status
    if _standalone_scheduler is not None and _standalone_scheduler.running:
        jobs = _standalone_scheduler.get_jobs()
        next_runs = {}
        for j in jobs:
            if j.next_run_time:
                next_runs[j.id] = j.next_run_time.isoformat()
        checks["scheduler"] = {
            "running": True,
            "job_count": len(jobs),
            "next_runs": next_runs,
        }
    else:
        checks["scheduler"] = {"running": False, "job_count": 0}

    overall = "ok" if checks["oncofiles"] == "ok" else "degraded"

    # Circuit breaker telemetry — early warning for oncofiles instability
    cb_status = oncofiles_client.get_circuit_breaker_status()
    if cb_status["state"] == "open":
        overall = "degraded"

    # Process memory (RSS) — track for OOM early warning
    # macOS ru_maxrss is in bytes; Linux is in KB
    rss_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_mb = rss_raw / (1024 * 1024) if sys.platform == "darwin" else rss_raw / 1024

    return _cors_json(
        {
            "status": overall,
            "version": VERSION,
            "commit": GIT_COMMIT,
            "memory_rss_mb": round(rss_mb, 1),
            "circuit_breaker": cb_status,
            **checks,
        }
    )


async def api_activity(request: Request) -> JSONResponse:
    """GET /api/activity — recent activity log entries."""
    cb_resp = _circuit_breaker_503({"entries": [], "total": 0})
    if cb_resp:
        return cb_resp
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    limit = _parse_limit(request, default=50)
    try:
        result = await oncofiles_client.search_activity_log(
            agent_id="oncoteam", limit=limit, token=token
        )
        entries = _filter_test(_extract_list(result, "entries"), request)
        enriched = []
        for e in entries:
            entry = {
                "tool": e.get("tool_name"),
                "status": e.get("status"),
                "duration_ms": e.get("duration_ms"),
                "timestamp": e.get("created_at"),
                "input": e.get("input_summary"),
                "output": e.get("output_summary"),
                "error": e.get("error_message"),
            }
            output_data = _extract_output_data(e.get("tool_name"), e.get("output_summary"))
            if output_data is not None:
                entry["output_data"] = output_data
            enriched.append(entry)
        return _cors_json(
            {
                "entries": enriched,
                "total": len(enriched),
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
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    try:
        result = await oncofiles_client.search_activity_log(
            agent_id="oncoteam", limit=500, token=token
        )
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


# Document category → timeline event_type. Used when treatment_events are
# sparse/empty and we fall back to documents so the timeline shows something
# real instead of a red error banner (#369).
_DOC_SUBTYPE_TO_EVENT_TYPE = {
    "labs": "lab_work",
    "lab_report": "lab_work",
    "chemo_sheet": "chemo_cycle",
    "chemo_record": "chemo_cycle",
    "chemotherapy": "chemo_cycle",
    "imaging": "scan",
    "radiology": "scan",
    "pathology": "consultation",
    "genetics": "consultation",
    "reports": "consultation",
    "consultation": "consultation",
    "surgery": "surgery",
    "vaccination": "vaccination",
    "dental": "dental",
    "screening": "screening",
    "checkup": "checkup",
}


def _doc_to_timeline_event(item: dict) -> dict | None:
    """Project a get_journey_timeline document item into a timeline event.

    Only documents are projected — conversations stay in /facts. The synthesized
    id is prefixed with `doc:` so the frontend drilldown opens the document
    detail (`document_id` path), not a non-existent treatment_event.
    """
    if item.get("type") != "document":
        return None
    date = item.get("date")
    if not date:
        return None
    subtype = item.get("subtype", "")
    event_type = _DOC_SUBTYPE_TO_EVENT_TYPE.get(subtype, "document")
    return {
        "id": f"doc:{item.get('id', 0)}",
        "event_date": date,
        "event_type": event_type,
        "title": item.get("title", "") or subtype.replace("_", " ").title(),
        "notes": (item.get("detail") or "")[:300],
        "source": {
            "type": "document",
            "id": item.get("id"),
            "label": "Document",
            "url": item.get("gdrive_url"),
        },
        "_synthetic": True,
    }


async def api_timeline(request: Request) -> JSONResponse:
    """GET /api/timeline — treatment events timeline.

    Primary source: `list_treatment_events`. When empty or erroring, falls back
    to `get_journey_timeline` so historical documents (labs, chemo sheets,
    imaging, reports) render as timeline dots. Empty oncofiles state was
    surfacing as "backend unavailable" even though the service was fine (#369).
    """
    cb_resp = _circuit_breaker_503({"events": [], "total": 0})
    if cb_resp:
        return cb_resp
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    limit = _parse_limit(request, default=50)
    scrubbed_params = {k: v for k, v in request.query_params.items() if k not in ("nocache", "_t")}
    cache_key = _cache_key("timeline", patient_id, str(limit), str(sorted(scrubbed_params.items())))
    nocache = request.query_params.get("nocache") == "1"
    if not nocache and cache_key in _timeline_cache:
        cached_time, cached_response = _timeline_cache[cache_key]
        if time.time() - cached_time < _TIMELINE_CACHE_TTL:
            return cached_response

    events: list[dict] = []
    primary_error: str | None = None
    try:
        result = await _deduplicated_fetch(
            cache_key,
            lambda: asyncio.wait_for(
                oncofiles_client.list_treatment_events(limit=limit, token=token), timeout=8.0
            ),
        )
        events = _filter_test(_extract_list(result, "events"), request)
        events = _deduplicate_timeline(events)
    except Exception as e:
        primary_error = str(e)
        record_suppressed_error("api_timeline", "fetch_treatment_events", e)

    # Fallback: synthesize from documents when treatment_events is empty
    # (pre-migration state, or lab_sync hasn't produced events yet).
    if not events:
        try:
            journey = await asyncio.wait_for(
                oncofiles_client.get_journey_timeline(limit=limit, token=token), timeout=8.0
            )
            items = journey
            if isinstance(items, str):
                items = json.loads(items)
            if isinstance(items, dict):
                items = items.get("result") or items.get("items") or []
                if isinstance(items, str):
                    items = json.loads(items)
            if isinstance(items, list):
                synthesized: list[dict] = []
                for item in items:
                    ev = _doc_to_timeline_event(item)
                    if ev:
                        synthesized.append(ev)
                synthesized.sort(key=lambda e: e.get("event_date", ""), reverse=True)
                events = synthesized[:limit]
        except Exception as e:
            record_suppressed_error("api_timeline", "fallback_journey_timeline", e)

    if not events and primary_error:
        # Both paths failed — honest error, cache miss
        return _cors_json({"error": primary_error, "events": [], "total": 0}, status_code=502)

    response = _cors_json(
        {
            "events": [
                {
                    "id": e.get("id"),
                    "event_date": e.get("event_date"),
                    "event_type": e.get("event_type"),
                    "title": e.get("title"),
                    "notes": e.get("notes"),
                    "source": e.get("source") or _build_source_ref(e, "treatment_event"),
                }
                for e in events
            ],
            "total": len(events),
        }
    )
    _timeline_cache[cache_key] = (time.time(), response)
    _cache_evict(_timeline_cache)
    return response


_facts_cache: dict[str, tuple[float, JSONResponse]] = {}
_FACTS_CACHE_TTL = 90  # seconds — facts make 2 parallel oncofiles calls

# Category → event_type mapping for facts
_FACT_CATEGORY_MAP = {
    "clinical": {
        "chemo_cycle",
        "chemotherapy",
        "lab_result",
        "toxicity_log",
        "weight_measurement",
        "medication_log",
        "medication_adherence",
        "consultation",
        "surgery",
        "scan",
        "checkup",
        "screening",
        "vaccination",
        "dental",
    },
    "documents": {"document"},
    "intelligence": {
        "autonomous_briefing",
        "session_summary",
        "decision",
        "note",
        "family_update",
        "cost_alert",
    },
    "operational": {"agent_run", "whatsapp"},
}


def _normalize_fact(item: dict, source: str) -> dict:
    """Normalize a raw item from any source into a FactItem dict."""
    if source == "journey":
        # get_journey_timeline returns {date, type, subtype, title, detail, id}
        item_type = item.get("type", "")  # "document" or "conversation"
        subtype = item.get("subtype", "")
        if item_type == "document":
            category = "documents"
            id_prefix = "doc"
        elif subtype in _FACT_CATEGORY_MAP.get("intelligence", set()):
            category = "intelligence"
            id_prefix = "narr"
        elif subtype in _FACT_CATEGORY_MAP.get("operational", set()):
            category = "operational"
            id_prefix = "narr"
        else:
            category = "intelligence"
            id_prefix = "narr"
        return {
            "id": f"{id_prefix}:{item.get('id', 0)}",
            "fact_type": item_type,
            "category": category,
            "event_subtype": subtype,
            "title": item.get("title", ""),
            "date": item.get("date", ""),
            "summary": (item.get("detail") or "")[:300],
            "source_label": item_type.replace("_", " ").title(),
            "gdrive_url": item.get("gdrive_url"),
            "document_id": item.get("id") if item_type == "document" else None,
            "oncofiles_id": item.get("id"),
            "tags": [],
            "has_document": item_type == "document",
        }
    elif source == "treatment_event":
        event_type = item.get("event_type", "")
        category = "clinical"
        return {
            "id": f"te:{item.get('id', 0)}",
            "fact_type": "treatment_event",
            "category": category,
            "event_subtype": event_type,
            "title": item.get("title", ""),
            "date": item.get("event_date", ""),
            "summary": (item.get("notes") or "")[:300],
            "source_label": "Treatment Event",
            "gdrive_url": None,
            "document_id": None,
            "oncofiles_id": item.get("id"),
            "tags": item.get("tags", []),
            "has_document": False,
        }
    return {}


async def api_facts(request: Request) -> JSONResponse:
    """GET /api/facts — unified fact timeline across all data sources."""
    cb_resp = _circuit_breaker_503({"facts": [], "total": 0, "has_more": False})
    if cb_resp:
        return cb_resp

    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)

    # Parse query params
    categories_raw = request.query_params.get("categories", "")
    categories = set(categories_raw.split(",")) if categories_raw else set()
    event_types_raw = request.query_params.get("event_types", "")
    event_types = set(event_types_raw.split(",")) if event_types_raw else set()
    search = request.query_params.get("search", "").strip().lower()
    date_from = request.query_params.get("date_from", "")
    date_to = request.query_params.get("date_to", "")
    sort_order = request.query_params.get("sort", "newest")
    offset = max(0, int(request.query_params.get("offset", "0") or "0"))
    limit = min(50, max(1, int(request.query_params.get("limit", "20") or "20")))

    # Cache only offset=0 to avoid bloat
    cache_key = _cache_key(
        "facts",
        patient_id,
        categories_raw,
        event_types_raw,
        search,
        date_from,
        date_to,
        sort_order,
    )
    if offset == 0 and cache_key in _facts_cache:
        cached_time, cached_response = _facts_cache[cache_key]
        if time.time() - cached_time < _FACTS_CACHE_TTL:
            return cached_response

    try:
        # Fetch treatment events first (fast, <2s), journey timeline is slower
        events_coro = oncofiles_client.list_treatment_events(limit=200, token=token)
        journey_coro = oncofiles_client.get_journey_timeline(
            date_from=date_from or None,
            date_to=date_to or None,
            limit=200,
            token=token,
        )
        events_raw, journey_raw = await asyncio.gather(
            asyncio.wait_for(events_coro, timeout=8.0),
            asyncio.wait_for(journey_coro, timeout=18.0),
            return_exceptions=True,
        )

        all_facts: list[dict] = []

        # Process journey timeline (documents + conversations)
        if not isinstance(journey_raw, BaseException):
            items = journey_raw
            if isinstance(items, str):
                items = json.loads(items)
            if isinstance(items, dict):
                items = items.get("result") or items.get("items") or []
                if isinstance(items, str):
                    items = json.loads(items)
            if isinstance(items, list):
                for item in items:
                    fact = _normalize_fact(item, "journey")
                    if fact and fact.get("date"):
                        all_facts.append(fact)
        else:
            record_suppressed_error("api_facts", "journey_timeline", journey_raw)

        # Process treatment events
        if not isinstance(events_raw, BaseException):
            events = _extract_list(events_raw, "events")
            events = _filter_test(events, request)
            for ev in events:
                eid = ev.get("id")
                if isinstance(eid, int) and eid in _CONTAMINATED_EVENT_IDS:
                    continue
                fact = _normalize_fact(ev, "treatment_event")
                if fact:
                    all_facts.append(fact)
        else:
            record_suppressed_error("api_facts", "treatment_events", events_raw)

        # Filter by categories
        if categories:
            all_facts = [f for f in all_facts if f["category"] in categories]

        # Filter by event types
        if event_types:
            all_facts = [f for f in all_facts if f["event_subtype"] in event_types]

        # Fulltext search (3+ chars)
        if len(search) >= 3:
            all_facts = [
                f
                for f in all_facts
                if search in (f.get("title") or "").lower()
                or search in (f.get("summary") or "").lower()
                or any(search in t.lower() for t in (f.get("tags") or []))
            ]

        # Date range filter
        if date_from:
            all_facts = [f for f in all_facts if (f.get("date") or "") >= date_from]
        if date_to:
            all_facts = [f for f in all_facts if (f.get("date") or "") <= date_to]

        # Sort
        reverse = sort_order != "oldest"
        all_facts.sort(key=lambda f: f.get("date") or "", reverse=reverse)

        # Paginate
        total = len(all_facts)
        page = all_facts[offset : offset + limit]
        has_more = (offset + limit) < total

        response = _cors_json(
            {
                "facts": page,
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": has_more,
            }
        )

        # Cache offset=0 only
        if offset == 0:
            _facts_cache[cache_key] = (time.time(), response)
            _cache_evict(_facts_cache)

        return response

    except Exception as exc:
        record_suppressed_error("api_facts", "fetch", exc)
        if cache_key in _facts_cache:
            return _facts_cache[cache_key][1]
        return _cors_json(
            {"error": str(exc), "facts": [], "total": 0, "has_more": False},
            status_code=502,
        )


_patient_ids_cache: dict[str, tuple[float, dict]] = {}
_PATIENT_IDS_CACHE_TTL = 600  # 10 minutes — patient IDs change very rarely


async def api_patient(request: Request) -> JSONResponse:
    """GET /api/patient — patient profile with live patient_ids from oncofiles."""
    lang = get_lang(request)
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    data = get_patient_localized(lang, patient_id=patient_id)

    # Fetch live patient_ids from oncofiles patient_context (with TTL cache)
    cache_key = _cache_key("patient_ids", patient_id)
    cached = _patient_ids_cache.get(cache_key)
    if cached and time.time() - cached[0] < _PATIENT_IDS_CACHE_TTL:
        data["patient_ids"] = cached[1]
    else:
        live_ids = await _fetch_patient_ids(patient_id, token)
        if live_ids is not None:
            # Only cache successful oncofiles responses, not fallbacks
            _patient_ids_cache[cache_key] = (time.time(), live_ids)
            data["patient_ids"] = live_ids
        else:
            # Fallback: use static profile (not cached — retry next request)
            profile = get_patient(patient_id)
            data["patient_ids"] = {k: v for k, v in profile.patient_ids.items() if v}

    # Include therapy categories for frontend badge rendering
    data["therapy_categories"] = {
        k: {"label": v["label_en"] if lang == "en" else v["label"], "color": v["color"]}
        for k, v in THERAPY_CATEGORIES.items()
    }
    return _cors_json(data)


async def _fetch_patient_ids(patient_id: str, token: str | None = None) -> dict[str, str] | None:
    """Fetch patient_ids from oncofiles patient_context. Returns None on failure."""
    try:
        ctx = await asyncio.wait_for(oncofiles_client.get_patient_context(token=token), timeout=8.0)
        if isinstance(ctx, dict):
            ids = ctx.get("patient_ids")
            if isinstance(ids, dict) and ids:
                return {k: str(v) for k, v in ids.items() if v}
    except Exception as e:
        record_suppressed_error("api_patient", "fetch_patient_ids", e)
    return None


async def api_sessions(request: Request) -> JSONResponse:
    """GET /api/sessions — session summaries from conversations.

    Query params:
        limit: max entries (default 20)
        type: filter by session type — 'clinical', 'technical', or 'all' (default 'all')
    """
    cb_resp = _circuit_breaker_503({"sessions": [], "total": 0})
    if cb_resp:
        return cb_resp
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    limit = _parse_limit(request, default=20)
    type_filter = request.query_params.get("type", "all").lower()
    try:
        result = await oncofiles_client.search_conversations(
            entry_type="session_summary", limit=limit, token=token
        )
        entries = _filter_test(_extract_list(result, "entries"), request)
        # Only filter non-oncology sessions for oncology patients
        from .patient_context import is_general_health_patient

        patient = _get_patient_for_request(request)
        if not is_general_health_patient(patient):
            entries = [e for e in entries if _is_oncology_session(e)]

        # Classify each session
        classified = []
        type_counts = {"clinical": 0, "technical": 0}
        for e in entries:
            session_type = _classify_session_type(e)
            type_counts[session_type] += 1
            classified.append((e, session_type))

        # Filter by type if requested
        if type_filter in ("clinical", "technical"):
            classified = [(e, st) for e, st in classified if st == type_filter]

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
                        "session_type": session_type,
                    }
                    for e, session_type in classified
                ],
                "total": len(classified),
                "type_counts": type_counts,
            }
        )
    except Exception as e:
        record_suppressed_error("api_sessions", "fetch", e)
        empty_counts = {"clinical": 0, "technical": 0}
        return _cors_json(
            {"error": str(e), "sessions": [], "total": 0, "type_counts": empty_counts},
            status_code=502,
        )


# api_autonomous, api_autonomous_status, api_autonomous_cost moved to api_agents.py


# ── Cache helpers (patient-scoped) ────────────────────────────────────────
_CACHE_MAX_SIZE = 200


def _cache_key(prefix: str, patient_id: str, *extra: str) -> str:
    """Build cache key scoped to patient."""
    parts = [prefix, patient_id or DEFAULT_PATIENT_ID] + list(extra)
    return ":".join(parts)


def _cache_evict(cache: dict) -> None:
    """Evict oldest entries if cache exceeds max size."""
    if len(cache) > _CACHE_MAX_SIZE:
        entries = sorted(cache.items(), key=lambda x: x[1][0])
        for k, _ in entries[: len(entries) // 5]:
            del cache[k]


_protocol_cache: dict[str, tuple[float, JSONResponse]] = {}
_PROTOCOL_CACHE_TTL = 300  # seconds — protocol is mostly static clinical data

# TTL caches for oncofiles-dependent endpoints (#173 — prevent hanging requests)
_timeline_cache: dict[str, tuple[float, JSONResponse]] = {}
_TIMELINE_CACHE_TTL = 60  # seconds
_briefings_cache: dict[str, tuple[float, JSONResponse]] = {}
_BRIEFINGS_CACHE_TTL = 120  # seconds — briefings change infrequently
_labs_cache: dict[str, tuple[float, JSONResponse]] = {}
_LABS_CACHE_TTL = 60  # seconds

# ── Request deduplication ────────────────────────────────────────────
# Concurrent identical requests share a single in-flight fetch.
_pending_requests: dict[str, asyncio.Future] = {}


async def _deduplicated_fetch(cache_key: str, fetcher) -> any:
    """Deduplicate concurrent fetches: if a fetch for cache_key is
    already in flight, await its result instead of making a second call."""
    if cache_key in _pending_requests:
        return await asyncio.shield(_pending_requests[cache_key])
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    _pending_requests[cache_key] = future
    try:
        result = await fetcher()
        future.set_result(result)
        return result
    except BaseException as e:
        # Catch BaseException (incl. CancelledError) to ensure future is
        # always resolved — otherwise waiters hang indefinitely (#201)
        if not future.done():
            future.set_exception(e)
        raise
    finally:
        _pending_requests.pop(cache_key, None)


async def api_protocol(request: Request) -> JSONResponse:
    """GET /api/protocol — clinical protocol data (thresholds, milestones, dose mods)."""
    from .breast_protocol import is_breast_patient, resolve_breast_protocol
    from .clinical_protocol import resolve_protocol
    from .general_health_protocol import resolve_general_health_protocol
    from .patient_context import is_general_health_patient

    lang = get_lang(request)
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)

    # Short-lived response cache to avoid repeated MCP calls (#106 perf fix)
    cache_key = _cache_key("protocol", patient_id, lang, str(request.query_params))
    if cache_key in _protocol_cache:
        cached_time, cached_response = _protocol_cache[cache_key]
        if time.time() - cached_time < _PROTOCOL_CACHE_TTL:
            return cached_response

    patient = _get_patient_for_request(request)
    if is_general_health_patient(patient):
        data = resolve_general_health_protocol(lang)
    elif is_breast_patient(patient.diagnosis_code):
        data = resolve_breast_protocol(lang)
    else:
        data = resolve_protocol(lang)

    # Fetch lab values + treatment events + lab trends concurrently (#106 perf fix)
    # Deduplicated: concurrent protocol requests share a single in-flight fetch
    try:
        lab_result, events_result, trends_result = await _deduplicated_fetch(
            cache_key,
            lambda: asyncio.wait_for(
                asyncio.gather(
                    oncofiles_client.list_treatment_events(
                        event_type="lab_result", limit=1, token=token
                    ),
                    oncofiles_client.list_treatment_events(limit=20, token=token),
                    oncofiles_client.get_lab_trends_data(limit=200, token=token),
                    return_exceptions=True,
                ),
                timeout=8.0,
            ),
        )
    except TimeoutError:
        record_suppressed_error("api_protocol", "oncofiles_timeout", TimeoutError("8s"))
        lab_result = TimeoutError("oncofiles timeout")
        events_result = TimeoutError("oncofiles timeout")
        trends_result = TimeoutError("oncofiles timeout")

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
                meta = _normalize_lab_values(meta)
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

    # Fallback: fill missing threshold params from lab_values table (#72/#73)
    # Uses pre-fetched trends_result (parallel call above, #106 perf fix)
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
    _missing = set(LAB_SAFETY_THRESHOLDS.keys()) - set(last_lab_values.keys())
    if _missing and not isinstance(trends_result, BaseException):
        try:
            values_list = _extract_list(trends_result, "values")
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
                    _normalize_lab_values(latest_vals)
                    for stored_name, val in latest_vals.items():
                        threshold_key = _param_to_threshold.get(stored_name)
                        if not threshold_key or not isinstance(val, (int, float)):
                            continue
                        if threshold_key in last_lab_values:
                            continue  # don't overwrite fresher data from primary path
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
        except Exception as e:
            record_suppressed_error("api_protocol", "fallback_lab_trends", e)
    elif isinstance(trends_result, Exception):
        record_suppressed_error("api_protocol", "fallback_lab_trends", trends_result)

    # Data freshness timestamp
    lab_dates = [v.get("sample_date", "") for v in last_lab_values.values() if v.get("sample_date")]
    data["lab_data_last_updated"] = max(lab_dates) if lab_dates else None
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

        # Current dose level from patient context (reuse `patient` from line 1457)
        real_values["current_regimen"] = {
            "regimen": patient.treatment_regimen,
            "cycle": patient.current_cycle,
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
                    "baseline_kg": patient.baseline_weight_kg,
                }
    elif isinstance(events_result, Exception):
        record_suppressed_error("api_protocol", "fetch_real_values", events_result)

    data["real_values"] = real_values

    # Enrich safety flags with activation status from patient data (#230)
    if not is_general_health_patient(patient) and isinstance(data.get("safety_flags"), dict):
        biomarkers = patient.biomarkers or {}
        kras = str(biomarkers.get("KRAS", "")).lower()
        msi = str(biomarkers.get("MSI", "")).lower()
        plt_val = last_lab_values.get("PLT", {}).get("value")
        flag_active: dict[str, dict] = {}
        flag_active["anti_egfr_kras_mutant"] = {
            "active": "mutant" in kras or "mut" in kras,
            "severity": "permanent",
        }
        flag_active["bevacizumab_active_vte"] = {
            "active": bool(patient.excluded_therapies.get("bevacizumab")),
            "severity": "high",
        }
        flag_active["oxaliplatin_grade3_neuropathy"] = {
            "active": False,
            "severity": "conditional",
        }
        flag_active["checkpoint_mono_pmmr_mss"] = {
            "active": "pmmr" in msi or "mss" in msi,
            "severity": "permanent",
        }
        flag_active["lmwh_thrombocytopenia_50k"] = {
            "active": isinstance(plt_val, (int, float)) and plt_val < 50000,
            "severity": "conditional",
        }
        flag_active["5fu_dpd_deficiency"] = {
            "active": False,
            "severity": "conditional",
        }
        for key, flag in data["safety_flags"].items():
            if key in flag_active:
                flag.update(flag_active[key])

    response = _cors_json(data)
    _protocol_cache[cache_key] = (time.time(), response)
    _cache_evict(_protocol_cache)
    return response


async def api_protocol_cycles(request: Request) -> JSONResponse:
    """GET /api/protocol/cycles — previous cycle history with lab evaluations."""
    from .clinical_protocol import LAB_SAFETY_THRESHOLDS, check_lab_safety

    pt = _get_patient_for_request(request)
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    cycle = pt.current_cycle or 3

    # Fetch lab results and chemo events
    try:
        lab_result, chemo_result = await asyncio.wait_for(
            asyncio.gather(
                oncofiles_client.list_treatment_events(
                    event_type="lab_result", limit=50, token=token
                ),
                oncofiles_client.list_treatment_events(
                    event_type="chemotherapy", limit=50, token=token
                ),
            ),
            timeout=10.0,
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
                        with contextlib.suppress(json.JSONDecodeError, ValueError, TypeError):
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
    cb_resp = _circuit_breaker_503({"briefings": [], "total": 0})
    if cb_resp:
        return cb_resp
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    limit = _parse_limit(request, default=20)
    nocache = request.query_params.get("nocache")
    cache_key = _cache_key("briefings", patient_id, str(limit), str(request.query_params))
    if nocache:
        # Explicit refresh — clear all briefings cache entries for this patient
        prefix = f"briefings:{patient_id or DEFAULT_PATIENT_ID}"
        stale = [k for k in _briefings_cache if k.startswith(prefix)]
        for k in stale:
            _briefings_cache.pop(k, None)
    elif cache_key in _briefings_cache:
        cached_time, cached_response = _briefings_cache[cache_key]
        if time.time() - cached_time < _BRIEFINGS_CACHE_TTL:
            return cached_response
    try:
        briefings_res, alerts_res = await _deduplicated_fetch(
            cache_key,
            lambda: asyncio.wait_for(
                asyncio.gather(
                    oncofiles_client.search_conversations(
                        entry_type="autonomous_briefing", limit=limit, token=token
                    ),
                    oncofiles_client.search_conversations(
                        entry_type="cost_alert", limit=5, token=token
                    ),
                    return_exceptions=True,
                ),
                timeout=18.0,
            ),
        )
        briefings = (
            _extract_list(briefings_res, "entries") if isinstance(briefings_res, dict) else []
        )
        alerts = _extract_list(alerts_res, "entries") if isinstance(alerts_res, dict) else []
        entries = _filter_test(briefings + alerts, request)
        entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        # Deduplicate cost_alert entries by (title, date)
        seen_alerts: set[tuple[str, str]] = set()
        deduped: list[dict] = []
        for e in entries:
            if e.get("entry_type") == "cost_alert":
                key = (e.get("title", ""), (e.get("created_at") or "")[:10])
                if key in seen_alerts:
                    continue
                seen_alerts.add(key)
            deduped.append(e)
        response = _cors_json(
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
                    for e in deduped[:limit]
                ],
                "total": len(deduped),
            }
        )
        _briefings_cache[cache_key] = (time.time(), response)
        _cache_evict(_briefings_cache)
        return response
    except Exception as e:
        record_suppressed_error("api_briefings", "fetch", e)
        if cache_key in _briefings_cache:
            return _briefings_cache[cache_key][1]
        return _cors_json({"error": str(e), "briefings": [], "total": 0}, status_code=502)


async def api_toxicity(request: Request) -> JSONResponse:
    """GET/POST /api/toxicity — toxicity log entries.

    GET: list toxicity logs (treatment events with event_type=toxicity_log).
    POST: create a new toxicity log entry.
    """
    cb_resp = _circuit_breaker_503({"entries": [], "total": 0})
    if cb_resp:
        return cb_resp
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
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
                token=token,
            )
            return _cors_json({"created": True, "result": result})
        except Exception as e:
            record_suppressed_error("api_toxicity", "create", e)
            return _cors_json({"error": str(e)}, status_code=502)

    # GET: list toxicity logs
    limit = _parse_limit(request, default=50)
    try:
        result = await oncofiles_client.list_treatment_events(
            event_type="toxicity_log", limit=limit, token=token
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
    # Fail fast if oncofiles is down
    cb = oncofiles_client.get_circuit_breaker_status()
    if cb["state"] == "open":
        return _cors_json(
            {
                "error": "Database temporarily unavailable. Try again in a minute.",
                "entries": [],
                "total": 0,
                "unavailable": True,
            },
            status_code=503,
        )

    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)

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
                token=token,
            )
            # Invalidate labs cache for this patient only
            stale_keys = [k for k in _labs_cache if k.startswith(f"labs:{patient_id}:")]
            for k in stale_keys:
                del _labs_cache[k]
            return _cors_json({"created": True, "result": result})
        except Exception as e:
            record_suppressed_error("api_labs", "create", e)
            return _cors_json({"error": str(e)}, status_code=502)

    # GET: list lab results
    limit = _parse_limit(request, default=50)
    # Strip cache-busting params from the cache key so nocache=1 and _t
    # don't each create a new cache slot (would leak memory).
    scrubbed_params = {k: v for k, v in request.query_params.items() if k not in ("nocache", "_t")}
    cache_key = _cache_key("labs", patient_id, str(limit), str(sorted(scrubbed_params.items())))
    nocache = request.query_params.get("nocache") == "1"
    if not nocache and cache_key in _labs_cache:
        cached_time, cached_response = _labs_cache[cache_key]
        if time.time() - cached_time < _LABS_CACHE_TTL:
            return cached_response
    try:
        result = await _deduplicated_fetch(
            cache_key,
            lambda: asyncio.wait_for(
                oncofiles_client.list_treatment_events(
                    event_type="lab_result", limit=limit, token=token
                ),
                timeout=8.0,
            ),
        )
        events = _filter_test(_extract_list(result, "events"), request)

        # Always attempt enrichment from the lab_values table — even when every
        # event already has some metadata. The lab_sync agent often writes
        # PARTIAL metadata (e.g. CEA only) while the lab_values rows hold the
        # full panel (CEA + CA 19-9 + ANC + …). Without this pass, clinically
        # relevant parameters are silently dropped from charts (#386). The
        # merge is non-destructive — curated event values always win.
        enrich_from_lab_values = True
        if enrich_from_lab_values:
            try:
                trends = await oncofiles_client.get_lab_trends_data(limit=200, token=token)
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
                    # Enrich existing events with any parameters missing from
                    # their curated metadata. The treatment_event metadata is
                    # authoritative for keys it already holds — lab_values rows
                    # only backfill missing keys. Previous logic (#386) skipped
                    # enrichment entirely when an event had ANY metadata, which
                    # silently dropped CA 19-9 / ANC when the lab_sync agent
                    # extracted only CEA for a given date.
                    existing_dates = {e.get("event_date"): e for e in events}
                    for d, data in by_date.items():
                        _normalize_lab_values(data["metadata"])
                        if d in existing_dates:
                            existing_meta = existing_dates[d].get("metadata") or {}
                            if isinstance(existing_meta, str):
                                try:
                                    existing_meta = json.loads(existing_meta)
                                except (json.JSONDecodeError, TypeError):
                                    existing_meta = {}
                            if not isinstance(existing_meta, dict):
                                existing_meta = {}
                            for k, v in data["metadata"].items():
                                if k not in existing_meta or existing_meta.get(k) in (
                                    None,
                                    "",
                                    {},
                                    [],
                                ):
                                    existing_meta[k] = v
                            existing_dates[d]["metadata"] = existing_meta
                        else:
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
                analysis = await oncofiles_client.analyze_labs(limit=limit, token=token)
                if isinstance(analysis, dict):
                    lab_sets = analysis.get("lab_results", analysis.get("results", []))
                    if isinstance(lab_sets, list):
                        for lab in lab_sets:
                            if isinstance(lab, dict) and lab.get("date"):
                                meta = {
                                    k: v
                                    for k, v in lab.items()
                                    if k not in ("date", "id", "document_id")
                                }
                                _normalize_lab_values(meta)
                                events.append(
                                    {
                                        "event_date": lab["date"],
                                        "metadata": meta,
                                        "notes": lab.get("notes", "From document analysis"),
                                        "id": lab.get("id"),
                                    }
                                )
            except Exception as fallback_err:
                record_suppressed_error("api_labs", "analyze_labs_fallback", fallback_err)

        # Dedupe by event_date — keep the entry with the richest metadata.
        # Root cause: lab_sync / document_pipeline can create multiple
        # treatment_events for the same sample date (re-ingest, manual entry,
        # backfill). Charts otherwise render duplicate x-axis labels and
        # flat-line artifacts (#366). Preference order:
        #   1) most populated metadata (by non-empty value count)
        #   2) newest created_at as tiebreaker
        def _event_metadata_count(ev: dict) -> int:
            m = ev.get("metadata", {})
            if isinstance(m, str):
                try:
                    m = json.loads(m)
                except (json.JSONDecodeError, TypeError):
                    return 0
            if not isinstance(m, dict):
                return 0
            return sum(1 for v in m.values() if v not in (None, "", {}, []))

        by_event_date: dict[str, dict] = {}
        for e in events:
            d = e.get("event_date")
            if not d:
                continue
            existing = by_event_date.get(d)
            if existing is None:
                by_event_date[d] = e
                continue
            new_score = _event_metadata_count(e)
            old_score = _event_metadata_count(existing)
            if new_score > old_score or (
                new_score == old_score
                and (e.get("created_at") or "") > (existing.get("created_at") or "")
            ):
                by_event_date[d] = e
        events = list(by_event_date.values())

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
            meta = _normalize_lab_values(meta)
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

        # Strip non-numeric values from entries (prevents raw JSON in frontend)
        for entry in entries:
            entry["values"] = {
                k: v for k, v in entry["values"].items() if isinstance(v, (int, float))
            }

        # Outlier detection: flag entries with >90% single-reading change
        # (e.g., CEA 1559→6 is medically impossible in 1 week)
        outlier_params = {"CEA", "CA_19_9", "CA_15_3", "CA_27_29"}
        for i, entry in enumerate(entries):
            suspects: list[dict] = []
            prev = entries[i + 1] if i + 1 < len(entries) else None
            if prev:
                for param in outlier_params:
                    val = entry["values"].get(param)
                    prev_val = prev["values"].get(param)
                    if (
                        isinstance(val, (int, float))
                        and isinstance(prev_val, (int, float))
                        and prev_val > 0
                    ):
                        pct_change = abs(val - prev_val) / prev_val
                        if pct_change > 0.9:
                            suspects.append(
                                {
                                    "param": param,
                                    "value": val,
                                    "prev_value": prev_val,
                                    "pct_change": round(pct_change * 100, 1),
                                    "prev_date": prev["date"],
                                }
                            )
            entry["suspects"] = suspects

        response = _cors_json(
            {
                "entries": entries,
                "total": len(entries),
                "reference_ranges": LAB_REFERENCE_RANGES,
            }
        )
        _labs_cache[cache_key] = (time.time(), response)
        _cache_evict(_labs_cache)
        return response
    except Exception as e:
        record_suppressed_error("api_labs", "fetch", e)
        # Serve stale cache on error
        if cache_key in _labs_cache:
            return _labs_cache[cache_key][1]
        return _cors_json({"error": str(e), "entries": [], "total": 0}, status_code=502)


async def api_detail(request: Request) -> JSONResponse:
    """GET /api/detail/{type}/{id} — fetch full detail for any data element."""
    detail_type = request.path_params.get("type", "")
    detail_id = request.path_params.get("id", "")
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)

    # Fail fast if oncofiles is down
    cb = oncofiles_client.get_circuit_breaker_status()
    if cb["state"] == "open":
        return _cors_json(
            {"error": "Database temporarily unavailable", "type": detail_type, "id": detail_id},
            status_code=503,
        )

    try:
        data: dict = {}
        source: dict = {"oncofiles_id": None, "gdrive_file_id": None, "gdrive_url": None}
        related: list[dict] = []

        if detail_type == "treatment_event":
            raw = await oncofiles_client.get_treatment_event(int(detail_id), token=token)
            data = raw if isinstance(raw, dict) else {"raw": raw}
            source["oncofiles_id"] = int(detail_id)
            # Parse metadata if string
            meta = data.get("metadata", {})
            if isinstance(meta, str):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    data["metadata"] = json.loads(meta)

        elif detail_type == "research":
            try:
                raw = await asyncio.wait_for(
                    oncofiles_client.get_research_entry(int(detail_id), token=token),
                    timeout=8.0,
                )
                data = raw if isinstance(raw, dict) else {"raw": raw}
            except Exception:
                # Fallback: fetch list and filter (with timeout)
                try:
                    result = await asyncio.wait_for(
                        oncofiles_client.list_research_entries(limit=100, token=token),
                        timeout=8.0,
                    )
                    entries = _extract_list(result, "entries")
                    match = [e for e in entries if e.get("id") == int(detail_id)]
                    data = match[0] if match else {"error": "not found"}
                except TimeoutError:
                    return _cors_json(
                        {"error": "Request timed out", "type": detail_type, "id": detail_id},
                        status_code=504,
                    )
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

        elif detail_type == "agent_run":
            # Full agent run trace — no truncation on tool outputs
            try:
                raw = await oncofiles_client.get_conversation(int(detail_id), token=token)
                entry = raw if isinstance(raw, dict) else {"raw": raw}
            except Exception:
                result = await asyncio.wait_for(
                    oncofiles_client.search_conversations(limit=100, token=token),
                    timeout=8.0,
                )
                entries = _extract_list(result, "entries")
                match = [e for e in entries if e.get("id") == int(detail_id)]
                entry = match[0] if match else {"error": "not found"}
            source["oncofiles_id"] = int(detail_id)
            # Parse the JSON content to expose the full trace
            content = entry.get("content", "")
            try:
                trace = json.loads(content) if isinstance(content, str) else content
            except (json.JSONDecodeError, TypeError):
                trace = {}
            data = {
                "id": entry.get("id"),
                "timestamp": entry.get("created_at"),
                **trace,
            }

        elif detail_type in ("conversation", "narrative"):
            try:
                raw = await oncofiles_client.get_conversation(int(detail_id), token=token)
                data = raw if isinstance(raw, dict) else {"raw": raw}
            except Exception:
                result = await asyncio.wait_for(
                    oncofiles_client.search_conversations(limit=100, token=token),
                    timeout=8.0,
                )
                entries = _extract_list(result, "entries")
                match = [e for e in entries if e.get("id") == int(detail_id)]
                data = match[0] if match else {"error": "not found"}
            source["oncofiles_id"] = int(detail_id)

        elif detail_type == "document":
            # Prefer REST doc-detail (single call: metadata + preview + pages)
            try:
                data = await oncofiles_client.get_doc_detail(int(detail_id), token=token)
            except Exception:
                # Fallback to MCP two-call approach
                raw = await oncofiles_client.get_document(int(detail_id), token=token)
                data = raw if isinstance(raw, dict) else {"raw": raw}
                file_id = data.get("file_id")
                if file_id:
                    with contextlib.suppress(Exception):
                        content = await oncofiles_client.view_document(file_id, token=token)
                        data["content"] = content
            source["oncofiles_id"] = int(detail_id)
            if data.get("gdrive_url"):
                source["gdrive_url"] = data["gdrive_url"]
            if data.get("preview_url"):
                source["preview_url"] = data["preview_url"]
            gdrive_id = data.get("gdrive_id") or data.get("gdrive_file_id")
            if gdrive_id:
                source["gdrive_file_id"] = gdrive_id
                if not source.get("gdrive_url"):
                    source["gdrive_url"] = f"https://drive.google.com/file/d/{gdrive_id}/view"

        elif detail_type == "biomarker":
            # Static from patient context
            patient_data = _get_patient_for_request(request).model_dump()
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
            result = await oncofiles_client.search_activity_log(
                agent_id="oncoteam", limit=200, token=token
            )
            entries = _extract_list(result, "entries")
            match = [e for e in entries if str(e.get("id")) == str(detail_id)]
            data = match[0] if match else {"error": "not found"}
            source["oncofiles_id"] = data.get("id")
            # Enrich with structured output_data (#31)
            output_data = _extract_output_data(data.get("tool_name"), data.get("output_summary"))
            if output_data is not None:
                data["output_data"] = output_data

        elif detail_type == "medication":
            # Fetch medication log entry (treatment event)
            raw = await oncofiles_client.get_treatment_event(int(detail_id), token=token)
            data = raw if isinstance(raw, dict) else {"raw": raw}
            source["oncofiles_id"] = int(detail_id)
            meta = data.get("metadata", {})
            if isinstance(meta, str):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    data["metadata"] = json.loads(meta)

        elif detail_type == "patient":
            patient_data = _get_patient_for_request(request).model_dump()
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


# _get_whisper_diagnostics, api_diagnostics moved to api_agents.py


_documents_cache: dict[str, tuple[float, JSONResponse]] = {}
_DOCUMENTS_CACHE_TTL = 120  # 2 minutes — heavy query, cache aggressively


async def api_documents(request: Request) -> JSONResponse:
    """GET /api/documents — document status matrix or category-filtered list.

    Two modes:
      - Default (?filter=...): status matrix from get_document_status_matrix,
        with has_ocr / has_ai / has_metadata flags. Used by the Documents page.
      - Category mode (?category=genetics|pathology|...): full document
        envelopes from search_documents, with ai_summary, structured_metadata,
        gdrive_url, filename, document_date, institution, doctors. Used by the
        Patient page hereditary panel.
    """
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    category = request.query_params.get("category")
    filter_param = request.query_params.get("filter", "all")
    # Status-matrix mode is the Documents archive view — it must return the
    # entire catalog or the header total silently undercounts (#378 — q1b had
    # 109 docs but was showing 100 because the default defaulted to 50).
    # Category mode stays at 50 because it's typically used for a single panel.
    default_limit = 500 if (category is None) else 50
    max_limit = 2000 if (category is None) else 500
    limit = _parse_limit(request, default=default_limit, max_val=max_limit)
    cache_key = _cache_key("docs", patient_id, category or filter_param, str(limit))
    nocache = request.query_params.get("nocache") == "1"

    # Serve from cache if fresh (unless caller forced a refresh)
    if not nocache and cache_key in _documents_cache:
        cached_time, cached_response = _documents_cache[cache_key]
        if time.time() - cached_time < _DOCUMENTS_CACHE_TTL:
            return cached_response

    # Fail fast if oncofiles is down — don't wait 20s for timeout
    cb = oncofiles_client.get_circuit_breaker_status()
    if cb["state"] == "open":
        # Serve stale cache if available
        if cache_key in _documents_cache:
            return _documents_cache[cache_key][1]
        return _cors_json(
            {
                "error": "Database temporarily unavailable. Try again in a minute.",
                "documents": [],
                "total": 0,
                "filter": filter_param,
                "category": category,
                "summary": {"total": 0, "ocr_complete": 0, "missing_ocr": 0, "missing_metadata": 0},
                "unavailable": True,
            },
            status_code=503,
        )

    try:
        if category:
            result = await _deduplicated_fetch(
                cache_key,
                lambda: asyncio.wait_for(
                    oncofiles_client.search_documents(
                        text="", category=category, limit=limit, token=token
                    ),
                    timeout=12.0,
                ),
            )
            docs = result if isinstance(result, list) else result.get("documents", [])
            response = _cors_json(
                {
                    "documents": docs,
                    "total": len(docs),
                    "category": category,
                }
            )
        else:
            result = await _deduplicated_fetch(
                cache_key,
                lambda: asyncio.wait_for(
                    oncofiles_client.call_oncofiles(
                        "get_document_status_matrix",
                        {"filter": filter_param, "limit": limit},
                        token=token,
                    ),
                    timeout=12.0,
                ),
            )
            docs = result if isinstance(result, list) else result.get("documents", [])
            # Compute summary counts
            # Oncofiles get_document_status_matrix returns boolean flags:
            # has_ocr, has_ai, has_metadata, fully_complete, is_synced, etc.
            total = len(docs)
            ocr_complete = sum(1 for d in docs if d.get("has_ocr") or d.get("has_ai"))
            missing_ocr = sum(1 for d in docs if not d.get("has_ocr") and not d.get("has_ai"))
            missing_metadata = sum(1 for d in docs if not d.get("has_metadata"))
            response = _cors_json(
                {
                    "documents": docs,
                    "total": total,
                    "filter": filter_param,
                    "summary": {
                        "total": total,
                        "ocr_complete": ocr_complete,
                        "missing_ocr": missing_ocr,
                        "missing_metadata": missing_metadata,
                    },
                }
            )
        _documents_cache[cache_key] = (time.time(), response)
        _cache_evict(_documents_cache)
        return response
    except Exception as e:
        record_suppressed_error("api_documents", "fetch", e)
        # Serve stale cache on error
        if cache_key in _documents_cache:
            return _documents_cache[cache_key][1]
        return _cors_json(
            {
                "error": str(e),
                "documents": [],
                "total": 0,
                "filter": filter_param,
                "category": category,
                "summary": {"total": 0, "ocr_complete": 0, "missing_ocr": 0, "missing_metadata": 0},
            },
            status_code=502,
        )


# ── Default medications (empty — real data from oncofiles) ──────

_DEFAULT_MEDICATIONS: list[dict] = []


async def api_medications(request: Request) -> JSONResponse:
    """GET/POST /api/medications — medication tracker.

    GET: list medication log entries + default regimen medications.
    POST: create a new medication log entry.
    """
    cb_resp = _circuit_breaker_503({"medications": [], "adherence": [], "total": 0})
    if cb_resp:
        return cb_resp
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
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
                    token=token,
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
                token=token,
            )
            return _cors_json({"created": True, "result": result})
        except Exception as e:
            record_suppressed_error("api_medications", "create", e)
            return _cors_json({"error": str(e)}, status_code=502)

    # GET: list medication logs + adherence data
    limit = _parse_limit(request, default=50)
    try:
        med_result, adh_result = await asyncio.gather(
            oncofiles_client.list_treatment_events(
                event_type="medication_log", limit=limit, token=token
            ),
            oncofiles_client.list_treatment_events(
                event_type="medication_adherence", limit=7, token=token
            ),
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


# ---------------------------------------------------------------------------
# Preventive care screenings (general health patients only)
# ---------------------------------------------------------------------------

_EU_SCREENINGS = [
    {
        "id": "colonoscopy",
        "name": "Colonoscopy",
        "interval_days": 3650,
        "min_age": 50,
        "event_types": ["screening"],
        "keywords": ["colonoscopy", "koloskopia"],
    },
    {
        "id": "fobt",
        "name": "FOBT/FIT",
        "interval_days": 730,
        "min_age": 50,
        "event_types": ["screening", "lab_result"],
        "keywords": ["fobt", "fit", "occult blood", "okultné"],
    },
    {
        "id": "dental",
        "name": "Dental checkup",
        "interval_days": 183,
        "min_age": 0,
        "event_types": ["dental", "checkup"],
        "keywords": ["dental", "dentist", "zubár", "stomatológ"],
    },
    {
        "id": "ophthalmology",
        "name": "Ophthalmology",
        "interval_days": 730,
        "min_age": 40,
        "event_types": ["checkup", "screening"],
        "keywords": ["ophthalmology", "eye", "oči", "oftalmológ"],
    },
    {
        "id": "dermatology",
        "name": "Dermatology",
        "interval_days": 730,
        "min_age": 35,
        "event_types": ["checkup", "screening"],
        "keywords": ["dermatology", "skin", "dermatológ", "melanoma"],
    },
    {
        "id": "cv_risk",
        "name": "CV risk (SCORE2)",
        "interval_days": 1825,
        "min_age": 40,
        "event_types": ["checkup", "screening"],
        "keywords": ["cardiovascular", "score2", "cv risk", "kardio"],
    },
    {
        "id": "psa",
        "name": "PSA screening",
        "interval_days": 730,
        "min_age": 50,
        "event_types": ["lab_result", "screening"],
        "keywords": ["psa", "prostate"],
    },
    {
        "id": "lipid_panel",
        "name": "Lipid panel",
        "interval_days": 1825,
        "min_age": 40,
        "event_types": ["lab_result"],
        "keywords": ["lipid", "cholesterol", "hdl", "ldl", "triglycerid"],
    },
    {
        "id": "glucose",
        "name": "Fasting glucose",
        "interval_days": 1095,
        "min_age": 45,
        "event_types": ["lab_result"],
        "keywords": ["glucose", "glukóza", "glycemia", "hba1c"],
    },
    {
        "id": "flu_vaccine",
        "name": "Flu vaccine",
        "interval_days": 365,
        "min_age": 50,
        "event_types": ["vaccination"],
        "keywords": ["flu", "influenza", "chrípka"],
    },
    {
        "id": "tetanus",
        "name": "Tetanus booster",
        "interval_days": 3650,
        "min_age": 0,
        "event_types": ["vaccination"],
        "keywords": ["tetanus", "tetanový"],
    },
]

_preventive_care_cache: dict[str, tuple[float, JSONResponse]] = {}
_PREVENTIVE_CARE_CACHE_TTL = 120


async def api_preventive_care(request: Request) -> JSONResponse:
    """GET /api/preventive-care — EU preventive care screening status.

    Returns screening compliance for general health patients based on
    EU/WHO/ESC guidelines. Only available for non-oncology patients.
    """
    cb_resp = _circuit_breaker_503({"screenings": [], "summary": {}})
    if cb_resp:
        return cb_resp

    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    patient = _get_patient_for_request(request)

    from .patient_context import is_general_health_patient

    if not is_general_health_patient(patient):
        return _cors_json(
            {"error": "Preventive care endpoint is only available for general health patients"},
            status_code=400,
        )

    cache_key = _cache_key("preventive_care", patient_id)
    if cache_key in _preventive_care_cache:
        cached_time, cached_response = _preventive_care_cache[cache_key]
        if time.time() - cached_time < _PREVENTIVE_CARE_CACHE_TTL:
            return cached_response

    from datetime import date, timedelta

    try:
        # Try oncofiles get_preventive_care_status for authoritative data
        oncofiles_status: dict = {}
        try:
            oncofiles_result = await oncofiles_client.call_oncofiles(
                "get_preventive_care_status", {}, token=token
            )
            if isinstance(oncofiles_result, dict):
                oncofiles_status = oncofiles_result
        except Exception as e:
            record_suppressed_error("api_preventive_care", "oncofiles_preventive_care", e)

        # Fetch treatment events for relevant types in parallel
        event_types = ["checkup", "screening", "vaccination", "dental", "lab_result"]
        fetch_tasks = [
            oncofiles_client.list_treatment_events(event_type=et, limit=50, token=token)
            for et in event_types
        ]
        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        # Collect all events into a flat list
        all_events: list[dict] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                record_suppressed_error("api_preventive_care", f"fetch_{event_types[i]}", result)
                continue
            all_events.extend(_extract_list(result, "events"))

        today = date.today()
        screenings = []
        summary = {"up_to_date": 0, "due": 0, "overdue": 0, "unknown": 0, "total": 0}

        for scr in _EU_SCREENINGS:
            screening_id = scr["id"]
            last_date_str: str | None = None

            # 1) Check oncofiles authoritative status
            if isinstance(oncofiles_status.get("screenings"), list):
                for os_entry in oncofiles_status["screenings"]:
                    if os_entry.get("id") == screening_id and os_entry.get("last_date"):
                        last_date_str = os_entry["last_date"]
                        break

            # 2) Scan events by type + keyword match
            if not last_date_str:
                for ev in all_events:
                    ev_type = ev.get("event_type", "")
                    if ev_type not in scr["event_types"]:
                        continue
                    ev_notes = (ev.get("notes", "") or "").lower()
                    ev_title = (ev.get("title", "") or "").lower()
                    ev_meta = str(ev.get("metadata", "")).lower()
                    searchable = f"{ev_notes} {ev_title} {ev_meta}"
                    if any(kw in searchable for kw in scr["keywords"]):
                        ev_date = ev.get("event_date", "")
                        if ev_date and (not last_date_str or ev_date > last_date_str):
                            last_date_str = ev_date

            # Compute status
            status = "unknown"
            next_due: str | None = None
            days_until: int | None = None

            if last_date_str:
                try:
                    last_dt = date.fromisoformat(last_date_str[:10])
                    next_dt = last_dt + timedelta(days=scr["interval_days"])
                    days_until = (next_dt - today).days
                    next_due = next_dt.isoformat()
                    if days_until > 30:
                        status = "up_to_date"
                    elif days_until >= 0:
                        status = "due"
                    else:
                        status = "overdue"
                except (ValueError, TypeError):
                    status = "unknown"

            summary[status] += 1
            summary["total"] += 1

            # Human-readable interval label
            days = scr["interval_days"]
            if days >= 3650:
                interval_label = f"{days // 365}y"
            elif days >= 365:
                y = days // 365
                interval_label = f"{y}y" if days % 365 < 30 else f"~{y}y"
            elif days >= 30:
                interval_label = f"{days // 30}mo"
            else:
                interval_label = f"{days}d"

            screenings.append(
                {
                    "id": screening_id,
                    "name": scr["name"],
                    "interval_days": scr["interval_days"],
                    "interval_label": interval_label,
                    "min_age": scr["min_age"],
                    "last_date": last_date_str,
                    "next_due": next_due,
                    "days_until": days_until,
                    "status": status,
                }
            )

        response = _cors_json(
            {
                "screenings": screenings,
                "summary": summary,
                "last_updated": today.isoformat(),
            }
        )
        _preventive_care_cache[cache_key] = (time.time(), response)
        _cache_evict(_preventive_care_cache)
        return response

    except Exception as e:
        record_suppressed_error("api_preventive_care", "fetch", e)
        return _cors_json(
            {
                "error": str(e),
                "screenings": [],
                "summary": {"up_to_date": 0, "due": 0, "overdue": 0, "unknown": 0, "total": 0},
            },
            status_code=502,
        )


async def api_weight(request: Request) -> JSONResponse:
    """GET /api/weight — weight/nutrition trend data.

    Aggregates weight from weight_measurement and toxicity_log events.
    Calculates % change from baseline and flags >5% loss.
    """
    cb_resp = _circuit_breaker_503({"entries": [], "total": 0})
    if cb_resp:
        return cb_resp
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    limit = _parse_limit(request, default=50)
    pt = _get_patient_for_request(request)
    baseline = pt.baseline_weight_kg or 72.0

    try:
        # Fetch both weight_measurement and toxicity_log events in parallel
        weight_result, toxicity_result = await asyncio.gather(
            oncofiles_client.list_treatment_events(
                event_type="weight_measurement", limit=limit, token=token
            ),
            oncofiles_client.list_treatment_events(
                event_type="toxicity_log", limit=limit, token=token
            ),
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


def _find_cumulative_dose_drug(pt) -> str | None:
    """Return the first drug in the patient's active_therapies that has
    a cumulative-dose threshold defined. None if no such drug is active
    (e.g. CDK4/6-based breast regimens — cumulative limits N/A)."""
    known_drugs = {k.lower() for k in CUMULATIVE_DOSE_THRESHOLDS}
    for therapy in pt.active_therapies:
        for drug in therapy.get("drugs", []):
            name = str(drug.get("name", "")).lower().split()[0] if drug.get("name") else ""
            if name in known_drugs:
                return name
    return None


async def api_cumulative_dose(request: Request) -> JSONResponse:
    """GET /api/cumulative-dose — cumulative dose tracking keyed on the
    active regimen's primary drug. For regimens without cumulative-dose
    limits (e.g. CDK4/6 + AI for HR+/HER2- metastatic breast), returns
    applicable=false with a clear reason rather than hardcoding oxaliplatin.
    """
    cb_resp = _circuit_breaker_503({"entries": [], "total": 0})
    if cb_resp:
        return cb_resp
    lang = get_lang(request)
    pt = _get_patient_for_request(request)
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    cycle = pt.current_cycle or 2

    drug_name = _find_cumulative_dose_drug(pt)
    if drug_name is None:
        return _cors_json(
            {
                "drug": None,
                "applicable": False,
                "reason": (
                    "No cumulative-dose drug in active regimen "
                    "(CDK4/6, endocrine, and monoclonal therapies have no cumulative thresholds)"
                ),
                "cycles_counted": cycle,
                "data_source": "n/a",
            }
        )

    drug_cfg = resolve(CUMULATIVE_DOSE_THRESHOLDS[drug_name], lang)

    # Resolve per-cycle dose from patient profile (fallback)
    dose_per_cycle_fallback = drug_cfg["dose_per_cycle"]
    for therapy in pt.active_therapies:
        for drug in therapy.get("drugs", []):
            if drug.get("name", "").lower().startswith(drug_name):
                with contextlib.suppress(ValueError, IndexError, KeyError):
                    dose_per_cycle_fallback = float(drug["dose"].split()[0])

    # Try to read actual extracted doses from chemotherapy events
    cumulative: float | None = None
    dose_per_cycle = dose_per_cycle_fallback
    cycles_detail: list[dict] = []
    try:
        chemo_result = await asyncio.wait_for(
            oncofiles_client.list_treatment_events(
                event_type="chemotherapy", limit=50, token=token
            ),
            timeout=8.0,
        )
        for entry in _extract_list(chemo_result, "entries"):
            raw_meta = entry.get("metadata") or entry.get("data") or {}
            if isinstance(raw_meta, str):
                with contextlib.suppress(json.JSONDecodeError):
                    raw_meta = json.loads(raw_meta)
            if not isinstance(raw_meta, dict):
                continue
            for drug in raw_meta.get("drugs", []):
                if str(drug.get("name", "")).lower().startswith(drug_name):
                    drug_dose = drug.get("dose_mg_m2")
                    if drug_dose is not None:
                        with contextlib.suppress(ValueError, TypeError):
                            cycles_detail.append(
                                {
                                    "cycle": raw_meta.get("cycle"),
                                    "dose_mg_m2": float(drug_dose),
                                    "date": entry.get("event_date", ""),
                                    "reduction_pct": drug.get("dose_reduction_pct", 0),
                                }
                            )
                    break
        if cycles_detail:
            cumulative = sum(c["dose_mg_m2"] for c in cycles_detail)
            sorted_c = sorted(cycles_detail, key=lambda c: c.get("cycle") or 0, reverse=True)
            dose_per_cycle = sorted_c[0]["dose_mg_m2"]
    except Exception as e:
        record_suppressed_error("api_cumulative_dose", "fetch_chemo_events", e)

    # Fall back to calculated if no extracted data
    if cumulative is None:
        cumulative = cycle * dose_per_cycle_fallback
        dose_per_cycle = dose_per_cycle_fallback

    cycles_counted = len(cycles_detail) if cycles_detail else cycle
    data_source = "extracted" if cycles_detail else "calculated"

    thresholds_reached = [t for t in drug_cfg["thresholds"] if cumulative >= t["at"]]
    thresholds_upcoming = [t for t in drug_cfg["thresholds"] if cumulative < t["at"]]
    next_threshold = thresholds_upcoming[0] if thresholds_upcoming else None
    pct_to_next = round((cumulative / next_threshold["at"]) * 100, 1) if next_threshold else 100.0

    return _cors_json(
        {
            "drug": drug_name,
            "applicable": True,
            "unit": drug_cfg["unit"],
            "dose_per_cycle": dose_per_cycle,
            "cycles_counted": cycles_counted,
            "cumulative_mg_m2": cumulative,
            "data_source": data_source,
            "cycles_detail": cycles_detail,
            "thresholds_reached": thresholds_reached,
            "next_threshold": next_threshold,
            "pct_to_next": pct_to_next,
            "all_thresholds": drug_cfg["thresholds"],
            "max_recommended": drug_cfg["thresholds"][-1]["at"],
        }
    )


# ── Family update translation helpers ─────────


def _translate_general_health_for_family(
    labs: dict | None,
    weight_data: dict | None,
    lang: str,
    patient,
) -> str:
    """Plain-language health summary for general health (non-oncology) patients."""
    parts: list[str] = []
    if lang == "sk":
        parts.append("Zdravotný prehľad — preventívna starostlivosť.\n")
        if labs and isinstance(labs, dict):
            parts.append("Laboratórne výsledky:")
            for key, val in labs.items():
                if isinstance(val, (int, float)):
                    parts.append(f"  {key}: {val}")
            if not any(isinstance(v, (int, float)) for v in labs.values()):
                parts.append("  Žiadne číselné hodnoty.")
        if weight_data:
            alerts = weight_data.get("alerts", [])
            if alerts:
                parts.append("\nZmena hmotnosti zaznamenaná — konzultácia s lekárom.")
            else:
                parts.append("\nHmotnosť je stabilná.")
        parts.append("")
        parts.append("Všetky údaje sú pre informáciu — konzultujte s ošetrujúcim lekárom.")
    else:
        parts.append("Health summary — preventive care.\n")
        if labs and isinstance(labs, dict):
            parts.append("Lab results:")
            for key, val in labs.items():
                if isinstance(val, (int, float)):
                    parts.append(f"  {key}: {val}")
            if not any(isinstance(v, (int, float)) for v in labs.values()):
                parts.append("  No numeric values available.")
        if weight_data:
            alerts = weight_data.get("alerts", [])
            if alerts:
                parts.append("\nWeight change detected — consult with physician.")
            else:
                parts.append("\nWeight is stable.")
        parts.append("")
        parts.append("All information is for reference — discuss details with your physician.")
    return "\n".join(parts)


def _translate_for_family(
    labs: dict | None,
    toxicity: dict | None,
    milestones: list[dict],
    weight_data: dict | None,
    lang: str = "sk",
    patient=None,
) -> str:
    """Translate clinical data to comprehensive plain language for family members."""
    from .patient_context import is_general_health_patient

    pt = patient or get_patient(DEFAULT_PATIENT_ID)
    parts: list[str] = []

    # General health patients get a simpler, non-oncology summary
    if is_general_health_patient(pt):
        return _translate_general_health_for_family(labs, weight_data, lang, pt)

    cycle = pt.current_cycle or 2

    if lang == "sk":
        parts.append(f"Liečba prebieha — cyklus {cycle} z chemoterapie {pt.treatment_regimen}.\n")

        # Blood counts
        if labs and isinstance(labs, dict):
            anc = labs.get("ANC")
            if anc is not None:
                if anc >= 1500:
                    parts.append("Krvné hodnoty sú v bezpečnom rozsahu pre ďalšiu liečbu.")
                else:
                    parts.append(
                        f"Krvné hodnoty (ANC {anc}) sú nižšie — onkológ rozhodne o ďalšom postupe."
                    )

            # Tumor markers
            cea = labs.get("CEA")
            ca199 = labs.get("CA_19_9")
            if cea is not None or ca199 is not None:
                parts.append("")
                parts.append("Nádorové markery:")
                if cea is not None:
                    parts.append(f"  CEA: {cea:,.1f} ng/mL")
                if ca199 is not None:
                    parts.append(f"  CA 19-9: {ca199:,.1f} U/mL")
                # Note: trend info would need previous values, but we provide current snapshot

            # Hemoglobin
            hgb = labs.get("hemoglobin")
            if hgb is not None and hgb < 10:
                parts.append(
                    f"Hemoglobín ({hgb:.1f} g/dL) je nižší — sleduje sa, "
                    "prípadne sa zváži transfúzia."
                )

            # Platelets
            plt_val = labs.get("PLT")
            if plt_val is not None and plt_val < 100000:
                parts.append(f"Krvné doštičky ({plt_val:,.0f}/µL) sú nižšie — sleduje sa.")

        # Toxicity
        if toxicity and isinstance(toxicity, dict):
            tox_items: list[str] = []
            neuro = toxicity.get("neuropathy", 0)
            if neuro and neuro >= 1:
                tox_items.append(
                    "mierne brnenie v prstoch rúk/nôh (bežný vedľajší účinok, sleduje sa)"
                )
            fatigue = toxicity.get("fatigue", 0)
            if fatigue and fatigue >= 2:
                tox_items.append(
                    "zvýšená únava — zvláda väčšinu bežných aktivít, ale rýchlejšie sa unaví"
                )
            nausea = toxicity.get("nausea", 0)
            if nausea and nausea >= 1:
                tox_items.append("mierna nevoľnosť (kontrolovaná liekmi)")
            diarrhea = toxicity.get("diarrhea", 0)
            if diarrhea and diarrhea >= 1:
                tox_items.append("občasné zažívacie ťažkosti")
            if tox_items:
                parts.append("")
                parts.append("Vedľajšie účinky:")
                for item in tox_items:
                    parts.append(f"  - {item}")
            else:
                parts.append("\nVedľajšie účinky sú minimálne.")

        # Weight
        if weight_data:
            alerts = weight_data.get("alerts", [])
            if alerts:
                latest = alerts[-1]
                loss_kg = round(
                    (weight_data.get("baseline_weight_kg", 72) - latest["weight_kg"]),
                    1,
                )
                parts.append(f"\nÚbytok hmotnosti o {loss_kg} kg — konzultácia s nutricionistom.")
            else:
                parts.append("\nHmotnosť je stabilná.")

        # Milestones
        if milestones:
            parts.append("")
            parts.append("Najbližšie kroky:")
            for m in milestones[:3]:
                desc = m.get("description", "")
                parts.append(f"  - {desc} (cyklus {m.get('cycle', '?')})")

        parts.append("")
        parts.append("Všetky údaje sú pre informáciu — detaily konzultujte s ošetrujúcim lekárom.")

    else:
        # English
        parts.append(
            f"Treatment is ongoing — cycle {cycle} of {pt.treatment_regimen} chemotherapy.\n"
        )

        # Blood counts
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

            # Tumor markers
            cea = labs.get("CEA")
            ca199 = labs.get("CA_19_9")
            if cea is not None or ca199 is not None:
                parts.append("")
                parts.append("Tumor markers:")
                if cea is not None:
                    parts.append(f"  CEA: {cea:,.1f} ng/mL")
                if ca199 is not None:
                    parts.append(f"  CA 19-9: {ca199:,.1f} U/mL")

            # Hemoglobin
            hgb = labs.get("hemoglobin")
            if hgb is not None and hgb < 10:
                parts.append(
                    f"Hemoglobin ({hgb:.1f} g/dL) is lower — being monitored, "
                    "transfusion may be considered."
                )

            # Platelets
            plt_val = labs.get("PLT")
            if plt_val is not None and plt_val < 100000:
                parts.append(f"Platelets ({plt_val:,.0f}/µL) are lower — being monitored.")

        # Toxicity
        if toxicity and isinstance(toxicity, dict):
            tox_items: list[str] = []
            neuro = toxicity.get("neuropathy", 0)
            if neuro and neuro >= 1:
                tox_items.append(
                    "mild tingling in fingers/toes (common side effect, being monitored)"
                )
            fatigue = toxicity.get("fatigue", 0)
            if fatigue and fatigue >= 2:
                tox_items.append(
                    "increased fatigue — able to manage most daily activities "
                    "but tires more quickly"
                )
            nausea = toxicity.get("nausea", 0)
            if nausea and nausea >= 1:
                tox_items.append("mild nausea (controlled with medication)")
            diarrhea = toxicity.get("diarrhea", 0)
            if diarrhea and diarrhea >= 1:
                tox_items.append("occasional digestive issues")
            if tox_items:
                parts.append("")
                parts.append("Side effects:")
                for item in tox_items:
                    parts.append(f"  - {item}")
            else:
                parts.append("\nSide effects are minimal.")

        # Weight
        if weight_data:
            alerts = weight_data.get("alerts", [])
            if alerts:
                latest = alerts[-1]
                parts.append(
                    f"\nWeight loss of {latest['loss_pct']}% — "
                    "nutritional support consultation recommended."
                )
            else:
                parts.append("\nWeight is stable.")

        # Milestones
        if milestones:
            parts.append("")
            parts.append("Upcoming steps:")
            for m in milestones[:3]:
                desc = m.get("description", "")
                parts.append(f"  - {desc} (cycle {m.get('cycle', '?')})")

        parts.append("")
        parts.append(
            "All information is for reference — discuss details with the treating physician."
        )

    return "\n".join(parts)


async def api_family_update(request: Request) -> JSONResponse:
    """GET/POST /api/family-update — weekly family update in plain language.

    GET: list past family updates. Accepts ?lang=sk or ?lang=en.
    POST: generate and store a new family update.
    """
    cb_resp = _circuit_breaker_503({"updates": [], "total": 0})
    if cb_resp:
        return cb_resp
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
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

            # Fetch latest data in parallel (limit=5 for labs to merge tumor markers + hematology)
            labs_data, toxicity_data, weight_data = None, None, None
            results = await asyncio.gather(
                oncofiles_client.list_treatment_events(
                    event_type="lab_result", limit=5, token=token
                ),
                oncofiles_client.list_treatment_events(
                    event_type="toxicity_log", limit=1, token=token
                ),
                oncofiles_client.list_treatment_events(
                    event_type="weight_measurement", limit=5, token=token
                ),
                return_exceptions=True,
            )

            if not isinstance(results[0], Exception):
                events = _extract_list(results[0], "events")
                # Merge most recent value for each parameter across entries
                merged: dict = {}
                for ev in events:
                    meta = ev.get("metadata", {})
                    if isinstance(meta, str):
                        with contextlib.suppress(json.JSONDecodeError, TypeError):
                            meta = json.loads(meta)
                    if isinstance(meta, dict):
                        for k, v in meta.items():
                            if k not in merged and isinstance(v, (int, float)):
                                merged[k] = v
                labs_data = merged or None

            if not isinstance(results[1], Exception):
                events = _extract_list(results[1], "events")
                if events:
                    meta = events[0].get("metadata", {})
                    if isinstance(meta, str):
                        with contextlib.suppress(json.JSONDecodeError, TypeError):
                            meta = json.loads(meta)
                    toxicity_data = meta

            # Build simple weight_data for translation
            fpt = _get_patient_for_request(request)
            baseline = fpt.baseline_weight_kg or 72.0
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

            cycle = fpt.current_cycle or 2
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
                patient=fpt,
            )

            # Store as conversation
            title = "Týždenná správa pre rodinu" if post_lang == "sk" else "Weekly Family Update"
            try:
                await oncofiles_client.log_conversation(
                    title=title,
                    content=content,
                    entry_type="family_update",
                    tags=f"lang:{post_lang}",
                    token=token,
                )
            except Exception as store_err:
                record_suppressed_error("api_family_update", "store", store_err)

            return _cors_json({"created": True, "content": content, "lang": post_lang})
        except Exception as e:
            record_suppressed_error("api_family_update", "generate", e)
            return _cors_json({"error": str(e)}, status_code=502)

    # GET: list past family updates
    limit = _parse_limit(request, default=20)
    try:
        result = await oncofiles_client.search_conversations(
            entry_type="family_update", limit=limit, token=token
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


# api_agents, api_agent_config, api_agent_runs, api_agent_runs_all moved to api_agents.py


# WhatsApp handlers moved to api_whatsapp.py (#353)


# api_bug_report, api_document_webhook, api_trigger_agent moved to api_webhooks.py

# api_whatsapp_media + api_whatsapp_voice moved to api_whatsapp.py (#353)

# Phone/token state + helpers moved to api_whatsapp.py (#353)
# Backward compat: admin handlers moved to api_admin.py
from .api_admin import _access_rights_cache as _access_rights_cache  # noqa: E402, F811
from .api_admin import _access_rights_ts as _access_rights_ts  # noqa: E402, F811
from .api_admin import _load_access_rights as _load_access_rights  # noqa: E402, F811
from .api_admin import api_access_rights_get as api_access_rights_get  # noqa: E402, F811
from .api_admin import api_access_rights_set as api_access_rights_set  # noqa: E402, F811
from .api_admin import api_approve_user as api_approve_user  # noqa: E402, F811
from .api_admin import api_onboard_patient as api_onboard_patient  # noqa: E402, F811
from .api_admin import api_onboarding_status as api_onboarding_status  # noqa: E402, F811
from .api_admin import api_patients as api_patients  # noqa: E402, F811

# Backward compat: WhatsApp handlers moved to api_whatsapp.py (#353)
from .api_agents import _parse_agent_run_entry as _parse_agent_run_entry  # noqa: E402, F811
from .api_agents import api_agent_config as api_agent_config  # noqa: E402, F811
from .api_agents import api_agent_runs as api_agent_runs  # noqa: E402, F811
from .api_agents import api_agent_runs_all as api_agent_runs_all  # noqa: E402, F811
from .api_agents import api_agents as api_agents  # noqa: E402, F811
from .api_agents import api_autonomous as api_autonomous  # noqa: E402, F811
from .api_agents import api_autonomous_cost as api_autonomous_cost  # noqa: E402, F811
from .api_agents import api_autonomous_status as api_autonomous_status  # noqa: E402, F811
from .api_agents import api_diagnostics as api_diagnostics  # noqa: E402, F811

# Backward compat: research handlers moved to api_research.py
from .api_research import _FUNNEL_STAGES as _FUNNEL_STAGES  # noqa: E402, F811
from .api_research import (  # noqa: E402
    _FUNNEL_SYSTEM_PROMPT_TEMPLATE as _FUNNEL_SYSTEM_PROMPT_TEMPLATE,  # noqa: F811
)
from .api_research import _RELEVANCE_SORT_ORDER as _RELEVANCE_SORT_ORDER  # noqa: E402, F811
from .api_research import api_assess_funnel as api_assess_funnel  # noqa: E402, F811
from .api_research import api_funnel_stages_get as api_funnel_stages_get  # noqa: E402, F811
from .api_research import api_funnel_stages_save as api_funnel_stages_save  # noqa: E402, F811
from .api_research import api_research as api_research  # noqa: E402, F811
from .api_webhooks import api_bug_report as api_bug_report  # noqa: E402, F811
from .api_webhooks import api_document_webhook as api_document_webhook  # noqa: E402, F811
from .api_webhooks import api_trigger_agent as api_trigger_agent  # noqa: E402, F811
from .api_whatsapp import _approved_phones as _approved_phones  # noqa: E402
from .api_whatsapp import _approved_phones_loaded as _approved_phones_loaded  # noqa: E402
from .api_whatsapp import _persist_approved_phones as _persist_approved_phones  # noqa: E402
from .api_whatsapp import _persist_patient_token as _persist_patient_token  # noqa: E402
from .api_whatsapp import _phone_patient_map as _phone_patient_map  # noqa: E402
from .api_whatsapp import api_log_whatsapp as api_log_whatsapp  # noqa: E402, F811
from .api_whatsapp import api_resolve_patient as api_resolve_patient  # noqa: E402, F811
from .api_whatsapp import api_whatsapp_chat as api_whatsapp_chat  # noqa: E402, F811
from .api_whatsapp import api_whatsapp_history as api_whatsapp_history  # noqa: E402, F811
from .api_whatsapp import api_whatsapp_media as api_whatsapp_media  # noqa: E402, F811
from .api_whatsapp import api_whatsapp_status as api_whatsapp_status  # noqa: E402, F811
from .api_whatsapp import api_whatsapp_voice as api_whatsapp_voice  # noqa: E402, F811
from .api_whatsapp import is_phone_approved as is_phone_approved  # noqa: E402
from .api_whatsapp import load_approved_phones as load_approved_phones  # noqa: E402
from .api_whatsapp import load_patient_tokens as load_patient_tokens  # noqa: E402


async def api_cors_preflight(request: Request) -> JSONResponse:
    """OPTIONS handler for CORS preflight on all /api/* routes."""
    return _cors_json({}, request=request)
