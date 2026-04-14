"""Dashboard API: JSON endpoints for the web dashboard and future channels."""

from __future__ import annotations

import asyncio
import collections
import contextlib
import contextvars
import json
import logging
import math
import re
import resource
import sys
import time

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import oncofiles_client
from .activity_logger import get_session_id, get_suppressed_errors, record_suppressed_error
from .autonomous import run_autonomous_task
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
    ANTHROPIC_API_KEY,
    ANTHROPIC_BUDGET_ALERT_THRESHOLD,
    ANTHROPIC_CREDIT_BALANCE,
    AUTONOMOUS_COST_LIMIT,
    AUTONOMOUS_ENABLED,
    AUTONOMOUS_MODEL_LIGHT,
    DASHBOARD_ALLOWED_ORIGINS,
    DASHBOARD_API_KEY,
    FUP_AGENT_RUNS_PER_MONTH,
    FUP_AI_QUERIES_PER_MONTH,
    FUP_ONCOFILES_DOCUMENTS,
    GIT_COMMIT,
    MCP_TRANSPORT,
    ONCOFILES_MCP_URL,
)
from .eligibility import assess_research_relevance
from .locale import get_lang, resolve
from .patient_context import (
    DEFAULT_PATIENT_ID,
    THERAPY_CATEGORIES,
    get_patient,
    get_patient_localized,
    get_patient_token,
)

VERSION = "0.73.0"

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


# Last trigger result (for debugging via /api/autonomous?last_trigger=1)
_last_trigger_result: dict | None = None

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


def _get_token_for_patient(patient_id: str) -> str | None:
    """Get the oncofiles bearer token for a patient. None = default (Erika)."""
    if not patient_id or patient_id == "q1b":
        return None  # Use default ONCOFILES_MCP_TOKEN
    return get_patient_token(patient_id)


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
# Short UUID generated per API request for log correlation.
_CORRELATION_ID: contextvars.ContextVar[str] = contextvars.ContextVar("_CORRELATION_ID", default="")


def _new_correlation_id() -> str:
    """Generate a short correlation ID (8 hex chars)."""
    import uuid

    return uuid.uuid4().hex[:8]


def get_correlation_id() -> str:
    """Return current request's correlation ID (empty if none)."""
    return _CORRELATION_ID.get()


def _parse_agent_run_entry(e: dict, default_task_name: str = "unknown") -> dict:
    """Parse an oncofiles agent_run entry into a lightweight summary dict."""
    tags = e.get("tags", [])
    tag_map = {}
    for t in tags if isinstance(tags, list) else []:
        if ":" in t:
            k, v = t.split(":", 1)
            tag_map[k] = v

    content = e.get("content", "")
    trace: dict = {}
    try:
        trace = json.loads(content) if isinstance(content, str) else content
        if not isinstance(trace, dict):
            trace = {}
    except (json.JSONDecodeError, TypeError):
        trace = {}

    n_tool_calls = len(trace.get("tool_calls", []))

    def _safe_float(val: object, default: float = 0.0) -> float:
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def _safe_int(val: object, default: int = 0) -> int:
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    return {
        "id": e.get("id"),
        "timestamp": e.get("created_at"),
        "task_name": tag_map.get("task", trace.get("task_name", default_task_name)),
        "model": tag_map.get("model", trace.get("model", "")),
        "cost": _safe_float(tag_map.get("cost", trace.get("cost", 0))),
        "duration_ms": _safe_int(tag_map.get("dur", trace.get("duration_ms", 0))),
        "error": trace.get("error"),
        "input_tokens": trace.get("input_tokens", 0),
        "output_tokens": trace.get("output_tokens", 0),
        "turns": trace.get("turns", 0),
        "tool_call_count": _safe_int(tag_map.get("tools", n_tool_calls)),
        "started_at": trace.get("started_at"),
        "completed_at": trace.get("completed_at"),
    }


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
    cid = _CORRELATION_ID.get()
    if cid:
        response.headers["X-Correlation-ID"] = cid
    return response


def _check_api_auth(request: Request) -> JSONResponse | None:
    """Check API key auth. Returns error response if unauthorized, None if OK.

    Also generates a correlation ID for this request and stores it in ContextVar.
    """
    # Generate correlation ID for every request (even failed auth)
    _CORRELATION_ID.set(_new_correlation_id())

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


async def api_timeline(request: Request) -> JSONResponse:
    """GET /api/timeline — treatment events timeline."""
    cb_resp = _circuit_breaker_503({"events": [], "total": 0})
    if cb_resp:
        return cb_resp
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    limit = _parse_limit(request, default=50)
    cache_key = _cache_key("timeline", patient_id, str(limit), str(request.query_params))
    if cache_key in _timeline_cache:
        cached_time, cached_response = _timeline_cache[cache_key]
        if time.time() - cached_time < _TIMELINE_CACHE_TTL:
            return cached_response
    try:
        result = await _deduplicated_fetch(
            cache_key,
            lambda: asyncio.wait_for(
                oncofiles_client.list_treatment_events(limit=limit, token=token), timeout=8.0
            ),
        )
        events = _filter_test(_extract_list(result, "events"), request)
        events = _deduplicate_timeline(events)
        response = _cors_json(
            {
                "events": [
                    {
                        "id": e.get("id"),
                        "event_date": e.get("event_date"),
                        "event_type": e.get("event_type"),
                        "title": e.get("title"),
                        "notes": e.get("notes"),
                        "source": _build_source_ref(e, "treatment_event"),
                    }
                    for e in events
                ],
                "total": len(events),
            }
        )
        _timeline_cache[cache_key] = (time.time(), response)
        _cache_evict(_timeline_cache)
        return response
    except Exception as e:
        record_suppressed_error("api_timeline", "fetch", e)
        # Serve stale cache on error
        if cache_key in _timeline_cache:
            return _timeline_cache[cache_key][1]
        return _cors_json({"error": str(e), "events": [], "total": 0}, status_code=502)


_facts_cache: dict[str, tuple[float, JSONResponse]] = {}
_FACTS_CACHE_TTL = 45  # seconds

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
        # Fetch from multiple sources in parallel
        journey_coro = oncofiles_client.get_journey_timeline(
            date_from=date_from or None,
            date_to=date_to or None,
            limit=200,
            token=token,
        )
        events_coro = oncofiles_client.list_treatment_events(limit=200, token=token)
        journey_raw, events_raw = await asyncio.gather(
            asyncio.wait_for(journey_coro, timeout=12.0),
            asyncio.wait_for(events_coro, timeout=8.0),
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
                    if fact:
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
        ctx = await oncofiles_client.get_patient_context(token=token)
        if isinstance(ctx, dict):
            ids = ctx.get("patient_ids")
            if isinstance(ids, dict) and ids:
                return {k: str(v) for k, v in ids.items() if v}
    except Exception as e:
        record_suppressed_error("api_patient", "fetch_patient_ids", e)
    return None


_RELEVANCE_SORT_ORDER = {"high": 0, "medium": 1, "low": 2, "not_applicable": 3}


async def api_research(request: Request) -> JSONResponse:
    """GET /api/research — research entries from oncofiles.

    Query params:
      - limit: max entries to fetch from oncofiles (default 100)
      - source: filter by source (pubmed, clinicaltrials)
      - sort: relevance (default), date, source
      - page: page number (default 1)
      - per_page: entries per page (default 10)
    """
    cb_resp = _circuit_breaker_503(
        {"entries": [], "total": 0, "page": 1, "per_page": 10, "total_pages": 0}
    )
    if cb_resp:
        return cb_resp
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    limit = _parse_limit(request, default=100)
    source = request.query_params.get("source")
    sort = request.query_params.get("sort", "relevance")
    page = max(1, int(request.query_params.get("page", "1")))
    per_page = max(1, min(100, int(request.query_params.get("per_page", "10"))))
    try:
        result = await oncofiles_client.list_research_entries(
            source=source, limit=limit, token=token
        )
        entries = _filter_test(_extract_list(result, "entries"), request)
        items = []
        for e in entries:
            rel = assess_research_relevance(
                e.get("title", ""),
                e.get("summary"),
            )
            ext_url = _build_external_url(
                e.get("source", ""), e.get("external_id", ""), e.get("raw_data", "")
            )
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
        # Sort
        if sort == "date":
            items.sort(key=lambda x: x.get("date") or "", reverse=True)
        elif sort == "source":
            items.sort(key=lambda x: x.get("source") or "")
        else:
            items.sort(key=lambda x: _RELEVANCE_SORT_ORDER.get(x["relevance"], 2))
        # Paginate
        total = len(items)
        total_pages = max(1, math.ceil(total / per_page))
        start = (page - 1) * per_page
        end = start + per_page
        paginated = items[start:end]
        return _cors_json(
            {
                "entries": paginated,
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
            }
        )
    except Exception as e:
        record_suppressed_error("api_research", "fetch", e)
        return _cors_json(
            {
                "error": str(e),
                "entries": [],
                "total": 0,
                "page": 1,
                "per_page": per_page,
                "total_pages": 0,
            },
            status_code=502,
        )


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

        trigger_patient_id = _get_patient_id(request)

        # Run in background with error capture
        async def _run_with_capture():
            global _last_trigger_result
            try:
                result = await task_fn(patient_id=trigger_patient_id)
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
                _last_trigger_result = {
                    "task": trigger,
                    "status": "failed",
                    "error": str(e),
                }
                _logger.error("Trigger %s failed: %s", trigger, e, exc_info=True)

        asyncio.create_task(_run_with_capture())
        return _cors_json({"triggered": trigger, "status": "started"})

    # Default: return scheduler status — prefer persisted cost over in-memory
    from datetime import UTC
    from datetime import datetime as _dt

    daily_cost = get_daily_cost()
    cost_last_updated: str | None = None
    try:
        # Cost tracking is intentionally global (not per-patient) — tracks total API spend
        state = await oncofiles_client.get_agent_state("autonomous_daily_cost")
        if isinstance(state, dict):
            val = state.get("value", state)
            if isinstance(val, dict):
                val = val.get("value", val)
            persisted_date = val.get("date", "") if isinstance(val, dict) else ""
            today_str = _dt.now(UTC).strftime("%Y-%m-%d")
            if persisted_date == today_str:
                daily_cost = float(val.get("cost_usd", daily_cost))
                cost_last_updated = val.get("updated_at") or state.get("updated_at")
    except Exception as e:
        record_suppressed_error("api_autonomous", "get_daily_cost_state", e)
    data: dict = {
        "enabled": AUTONOMOUS_ENABLED,
        "daily_cost": round(daily_cost, 4),
        "last_updated": cost_last_updated,
    }

    if AUTONOMOUS_ENABLED:
        try:
            lang = get_lang(request)
            # Jobs read from agent registry — single source of truth (#92)
            from .agent_registry import get_dashboard_jobs

            jobs = get_dashboard_jobs(lang)
            data["jobs"] = jobs
            data["job_count"] = len(jobs)
        except Exception:
            data["jobs"] = []
            data["job_count"] = 0

    return _cors_json(data)


async def api_autonomous_status(request: Request) -> JSONResponse:
    """GET /api/autonomous/status — per-task last-run timestamps."""
    # Read task names from agent registry (#92)
    from .agent_registry import get_enabled_agents
    from .autonomous_tasks import _extract_timestamp, _get_state

    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    task_names = [a.id for a in get_enabled_agents(exclude_system=True)]

    # Parallel state fetches (was sequential N+1, #harden)
    # State keys include patient_id (e.g. "last_daily_research:q1b")
    async def _safe_ts(name: str):
        try:
            state = await asyncio.wait_for(
                _get_state(f"last_{name}:{patient_id}", token=token), timeout=2.0
            )
            return _extract_timestamp(state)
        except Exception:
            return None

    timestamps = await asyncio.gather(*[_safe_ts(n) for n in task_names])
    tasks = {
        name: {"last_run": ts or None} for name, ts in zip(task_names, timestamps, strict=True)
    }
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
    except Exception as e:
        record_suppressed_error("api_autonomous_cost", "fetch_mtd", e)

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
            "fup": _get_fup_status(),
        }
    )


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
_PROTOCOL_CACHE_TTL = 30  # seconds

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
    else:
        data = resolve_protocol(lang)

    # Fetch lab values + treatment events + lab trends concurrently (#106 perf fix)
    # All 3 calls in parallel to avoid sequential fallback penalty
    import asyncio

    try:
        lab_result, events_result, trends_result = await asyncio.wait_for(
            asyncio.gather(
                oncofiles_client.list_treatment_events(
                    event_type="lab_result", limit=1, token=token
                ),
                oncofiles_client.list_treatment_events(limit=20, token=token),
                oncofiles_client.get_lab_trends_data(limit=200, token=token),
                return_exceptions=True,
            ),
            timeout=8.0,
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
            lambda: asyncio.gather(
                oncofiles_client.search_conversations(
                    entry_type="autonomous_briefing", limit=limit, token=token
                ),
                oncofiles_client.search_conversations(
                    entry_type="cost_alert", limit=5, token=token
                ),
                return_exceptions=True,
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
    cache_key = _cache_key("labs", patient_id, str(limit), str(request.query_params))
    if cache_key in _labs_cache:
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

        # Fallback: try lab_values table if no events exist OR any events
        # have empty metadata (lab_sync agent writes to lab_values table but
        # often omits metadata in treatment events — merge from lab_values).
        has_empty = events and any(not e.get("metadata") for e in events)
        if not events or has_empty:
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
                    # Enrich existing events or add new ones
                    existing_dates = {e.get("event_date"): e for e in events}
                    for d, data in by_date.items():
                        _normalize_lab_values(data["metadata"])
                        if d in existing_dates and not existing_dates[d].get("metadata"):
                            existing_dates[d]["metadata"] = data["metadata"]
                        elif d not in existing_dates:
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
        outlier_params = {"CEA", "CA_19_9"}
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
                result = await oncofiles_client.search_conversations(limit=100, token=token)
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

        elif detail_type == "conversation":
            try:
                raw = await oncofiles_client.get_conversation(int(detail_id), token=token)
                data = raw if isinstance(raw, dict) else {"raw": raw}
            except Exception:
                result = await oncofiles_client.search_conversations(limit=100, token=token)
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


def _get_whisper_diagnostics() -> dict:
    """Get Whisper transcription stats for diagnostics."""
    try:
        from .whisper_client import get_whisper_stats

        stats = get_whisper_stats()
        from .config import OPENAI_API_KEY

        stats["configured"] = bool(OPENAI_API_KEY)
        return stats
    except Exception:
        return {"configured": False, "error": "module_not_loaded"}


async def api_diagnostics(request: Request) -> JSONResponse:
    """GET /api/diagnostics — probe oncofiles connectivity and report health."""
    probes = [
        ("treatment_events", oncofiles_client.list_treatment_events, {"limit": 1}, "events"),
        ("research_entries", oncofiles_client.list_research_entries, {"limit": 1}, "entries"),
        ("conversations", oncofiles_client.search_conversations, {"limit": 1}, "entries"),
        ("activity_log", oncofiles_client.search_activity_log, {"limit": 1}, "entries"),
    ]

    async def _run_probe(name: str, fn, kwargs: dict, key: str) -> dict:
        try:
            t0 = time.time()
            result = await fn(**kwargs)
            ms = int((time.time() - t0) * 1000)
            count = len(_extract_list(result, key))
            return {"name": name, "ok": True, "ms": ms, "sample_count": count}
        except Exception as e:
            return {"name": name, "ok": False, "error": str(e)}

    checks = list(
        await asyncio.wait_for(
            asyncio.gather(*[_run_probe(*p) for p in probes]),
            timeout=15.0,
        )
    )

    # Check if lab_result data is stale (>48h since last lab_result event)
    lab_sync_stale = False
    te_check = next((c for c in checks if c["name"] == "treatment_events"), None)
    if te_check and te_check.get("ok"):
        try:
            diag_patient_id = _get_patient_id(request)
            diag_token = _get_token_for_patient(diag_patient_id)
            lab_events = await oncofiles_client.list_treatment_events(
                event_type="lab_result", limit=1, token=diag_token
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

    cb_status = oncofiles_client.get_circuit_breaker_status()

    return _cors_json(
        {
            "healthy": all(c["ok"] for c in checks) and cb_status["state"] == "closed",
            "checks": checks,
            "circuit_breaker": cb_status,
            "oncofiles_url": (ONCOFILES_MCP_URL[:30] + "...") if ONCOFILES_MCP_URL else "NOT SET",
            "autonomous_enabled": AUTONOMOUS_ENABLED,
            "lab_sync_stale": lab_sync_stale,
            "whisper": _get_whisper_diagnostics(),
            "suppressed_errors": get_suppressed_errors()[-10:],
        }
    )


_documents_cache: dict[str, tuple[float, JSONResponse]] = {}
_DOCUMENTS_CACHE_TTL = 120  # 2 minutes — heavy query, cache aggressively


async def api_documents(request: Request) -> JSONResponse:
    """GET /api/documents — document status matrix from oncofiles."""
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    filter_param = request.query_params.get("filter", "all")
    cache_key = _cache_key("docs", patient_id, filter_param)

    # Serve from cache if fresh
    if cache_key in _documents_cache:
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
                "summary": {"total": 0, "ocr_complete": 0, "missing_ocr": 0, "missing_metadata": 0},
                "unavailable": True,
            },
            status_code=503,
        )

    try:
        result = await _deduplicated_fetch(
            cache_key,
            lambda: asyncio.wait_for(
                oncofiles_client.call_oncofiles(
                    "get_document_status_matrix", {"filter": filter_param}, token=token
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

            screenings.append(
                {
                    "id": screening_id,
                    "name": scr["name"],
                    "interval_days": scr["interval_days"],
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


async def api_cumulative_dose(request: Request) -> JSONResponse:
    """GET /api/cumulative-dose — cumulative oxaliplatin dose tracking."""
    cb_resp = _circuit_breaker_503({"entries": [], "total": 0})
    if cb_resp:
        return cb_resp
    lang = get_lang(request)
    pt = _get_patient_for_request(request)
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    cycle = pt.current_cycle or 2
    oxa = resolve(CUMULATIVE_DOSE_THRESHOLDS["oxaliplatin"], lang)

    # Resolve per-cycle dose from patient profile (fallback)
    dose_per_cycle_fallback = oxa["dose_per_cycle"]
    for therapy in pt.active_therapies:
        for drug in therapy.get("drugs", []):
            if drug.get("name", "").lower() == "oxaliplatin":
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
                if str(drug.get("name", "")).lower() == "oxaliplatin":
                    oxa_dose = drug.get("dose_mg_m2")
                    if oxa_dose is not None:
                        with contextlib.suppress(ValueError, TypeError):
                            cycles_detail.append(
                                {
                                    "cycle": raw_meta.get("cycle"),
                                    "dose_mg_m2": float(oxa_dose),
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

    thresholds_reached = [t for t in oxa["thresholds"] if cumulative >= t["at"]]
    thresholds_upcoming = [t for t in oxa["thresholds"] if cumulative < t["at"]]
    next_threshold = thresholds_upcoming[0] if thresholds_upcoming else None
    pct_to_next = round((cumulative / next_threshold["at"]) * 100, 1) if next_threshold else 100.0

    return _cors_json(
        {
            "drug": "oxaliplatin",
            "unit": oxa["unit"],
            "dose_per_cycle": dose_per_cycle,
            "cycles_counted": cycles_counted,
            "cumulative_mg_m2": cumulative,
            "data_source": data_source,
            "cycles_detail": cycles_detail,
            "thresholds_reached": thresholds_reached,
            "next_threshold": next_threshold,
            "pct_to_next": pct_to_next,
            "all_thresholds": oxa["thresholds"],
            "max_recommended": oxa["thresholds"][-1]["at"],
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


async def api_agents(request: Request) -> JSONResponse:
    """Return agent registry with last-run status for each agent (#92, #105, #236)."""
    from .agent_registry import AGENT_REGISTRY, AgentCategory
    from .autonomous_tasks import _extract_timestamp

    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    lang = get_lang(request)

    # Build agent list (excluding system agents)
    non_system = [
        (aid, cfg) for aid, cfg in AGENT_REGISTRY.items() if cfg.category != AgentCategory.SYSTEM
    ]

    # Batch-fetch all agent states in ONE call (#236 — individual calls timeout)
    state_map: dict[str, str] = {}
    try:
        all_states = await asyncio.wait_for(
            oncofiles_client.list_agent_states(limit=200, token=token),
            timeout=10.0,
        )
        entries = _extract_list(all_states, "states") or (
            all_states if isinstance(all_states, list) else []
        )
        for entry in entries:
            key = entry.get("key", "")
            state_map[key] = _extract_timestamp(entry)
    except Exception as e:
        record_suppressed_error("api_agents", "batch_state_fetch", e)

    agents = []
    for _agent_id, config in non_system:
        ts = state_map.get(f"last_{_agent_id}:{patient_id}", "")
        agents.append(
            resolve(
                {
                    "id": config.id,
                    "name": config.name,
                    "description": config.description,
                    "category": config.category.value,
                    "model": config.model or "sonnet",
                    "schedule": config.schedule_display,
                    "cooldown_hours": config.cooldown_hours,
                    "max_turns": config.max_turns,
                    "whatsapp_enabled": config.whatsapp_enabled,
                    "last_run": ts or None,
                    "enabled": config.enabled,
                },
                lang,
            )
        )
    return _cors_json({"agents": agents, "total": len(agents)})


async def api_agent_config(request: Request) -> JSONResponse:
    """Return full config for a single agent including prompt_template (#92 Phase 4)."""
    agent_id = request.path_params.get("id", "")
    from .agent_registry import AGENT_REGISTRY

    config = AGENT_REGISTRY.get(agent_id)
    if not config:
        return _cors_json({"error": f"Agent {agent_id} not found"}, status_code=404)
    data = config.model_dump()
    # Include system prompt for full observability
    from .autonomous import build_system_prompt

    patient_id = _get_patient_id(request)
    data["system_prompt"] = build_system_prompt(patient_id)
    return _cors_json(data)


async def api_agent_runs(request: Request) -> JSONResponse:
    """Return recent run traces for a specific agent (#92)."""
    agent_id = request.path_params.get("id", "")
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    limit = _parse_limit(request, default=10)

    try:
        result = await oncofiles_client.search_conversations(
            tags=f"task:{agent_id},sys:agent-run",
            limit=limit,
            token=token,
        )
    except Exception as e:
        record_suppressed_error("api_agent_runs", f"fetch:{agent_id}", e)
        return _cors_json(
            {"agent_id": agent_id, "runs": [], "total": 0, "error": str(e)},
            status_code=502,
        )

    entries = _filter_test(_extract_list(result, "entries"), request)

    # List view: lightweight summary from tags or content header fields.
    # Full content (prompt, messages, thinking, tool outputs) via /api/detail/agent_run/{id}.
    runs = [_parse_agent_run_entry(e, default_task_name=agent_id) for e in entries]
    return _cors_json({"agent_id": agent_id, "runs": runs, "total": len(runs)})


async def api_agent_runs_all(request: Request) -> JSONResponse:
    """Return recent run traces across ALL agents — single MCP call (#113)."""
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    limit = _parse_limit(request, default=50)

    try:
        result = await oncofiles_client.search_conversations(
            tags="sys:agent-run",
            limit=limit,
            token=token,
        )
    except Exception as e:
        record_suppressed_error("api_agent_runs_all", "fetch", e)
        return _cors_json(
            {"runs": [], "total": 0, "error": str(e)},
            status_code=502,
        )

    entries = _filter_test(_extract_list(result, "entries"), request)
    runs = [_parse_agent_run_entry(e) for e in entries]
    return _cors_json({"runs": runs, "total": len(runs)})


async def api_log_whatsapp(request: Request) -> JSONResponse:
    """POST /api/internal/log-whatsapp — log WhatsApp message exchange."""
    auth = _check_api_auth(request)
    if auth:
        return auth
    try:
        body = json.loads(await request.body())
        phone = body.get("phone", "unknown")
        user_msg = body.get("user_message", "")
        bot_response = body.get("bot_response", "")

        await oncofiles_client.log_conversation(
            title=f"WhatsApp: {user_msg[:50]}",
            content=(
                f"**From**: {phone}\n**Message**: {user_msg}\n\n**Response**:\n{bot_response}"
            ),
            entry_type="whatsapp",
            tags="sys:whatsapp,src:twilio",
        )
        return _cors_json({"logged": True})
    except Exception as e:
        record_suppressed_error("api_log_whatsapp", "log", e)
        return _cors_json({"error": str(e)}, status_code=502)


_WA_THREAD_TTL = 2 * 3600  # 2 hours
_WA_THREAD_MAX_EXCHANGES = 5


def _get_patient_name_map() -> dict[str, str]:
    """Return {patient_id: display_name} for all registered patients."""
    from .patient_context import get_patient, list_patient_ids

    result = {}
    for pid in list_patient_ids():
        try:
            result[pid] = get_patient(pid).name
        except KeyError:
            continue
    return result


async def api_resolve_patient(request: Request) -> JSONResponse:
    """POST /api/internal/resolve-patient — AI-powered patient name resolution.

    Uses Claude Haiku to match free-form user input (names, nicknames,
    declined forms) to a patient slug.
    Body: {query: "eriku", allowed_ids: ["q1b", "e5g"]}
    Returns: {patient_id: "q1b", name: "Erika Fusekova"} or {patient_id: null}

    Note: auth is handled by _auth_wrap in server.py, not duplicated here.
    """
    try:
        body = json.loads(await request.body())
        query = (body.get("query") or "").strip()
        allowed_ids = body.get("allowed_ids") or []
    except Exception:
        return _cors_json({"error": "Invalid request body"}, status_code=400, request=request)

    if not query or not allowed_ids:
        return _cors_json({"patient_id": None})

    # Build patient context for Claude
    name_map = _get_patient_name_map()
    patients_desc = "\n".join(f"- {pid}: {name_map.get(pid, '?')}" for pid in allowed_ids)

    if not ANTHROPIC_API_KEY:
        return _cors_json({"patient_id": None, "error": "AI not configured"})

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Match the user input to a patient.\n\n"
                        f'User typed: "{query}"\n\n'
                        f"Available patients:\n{patients_desc}\n\n"
                        f"Reply with ONLY the patient ID (e.g. q1b) "
                        f"if you can match the input to a patient. "
                        f"Consider name variants, nicknames, declined "
                        f"forms (Slovak: Erika→Eriku/Eriky, Peter→Petra). "
                        f"Reply NONE if no match."
                    ),
                }
            ],
        )
        answer = resp.content[0].text.strip().lower()
        # Validate answer is one of the allowed IDs
        if answer in allowed_ids:
            return _cors_json({"patient_id": answer, "name": name_map.get(answer, "")})
        return _cors_json({"patient_id": None})
    except Exception as exc:
        record_suppressed_error("api_resolve_patient", "claude", exc)
        return _cors_json({"patient_id": None})


def _wa_thread_key(phone: str, patient_id: str = "q1b") -> str:
    """Hash phone for privacy — no PII in state keys. Scoped per patient."""
    import hashlib

    h = hashlib.sha256(phone.encode()).hexdigest()[:12]
    return f"wa_thread:{patient_id}:{h}"


async def _load_wa_thread(
    phone: str, token: str | None = None, patient_id: str = "q1b"
) -> list[dict[str, str]]:
    """Load conversation thread from agent_state, respecting TTL."""
    try:
        state = await asyncio.wait_for(
            oncofiles_client.get_agent_state(_wa_thread_key(phone, patient_id), token=token),
            timeout=3.0,
        )
        if not state:
            return []
        data = state if isinstance(state, dict) else {}
        # Check TTL
        updated_at = data.get("updated_at", "")
        if updated_at:
            from datetime import UTC, datetime

            try:
                ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                if (datetime.now(UTC) - ts).total_seconds() > _WA_THREAD_TTL:
                    return []  # Expired
            except (ValueError, TypeError):
                pass
        return data.get("exchanges", [])
    except Exception as e:
        record_suppressed_error("wa_thread", "load", e)
        return []


async def _save_wa_thread(
    phone: str,
    exchanges: list[dict[str, str]],
    token: str | None = None,
    patient_id: str = "q1b",
) -> None:
    """Persist conversation thread (non-blocking, fire-and-forget)."""
    from datetime import UTC, datetime

    try:
        await asyncio.wait_for(
            oncofiles_client.set_agent_state(
                _wa_thread_key(phone, patient_id),
                json.dumps(
                    {
                        "exchanges": exchanges[-_WA_THREAD_MAX_EXCHANGES:],
                        "updated_at": datetime.now(UTC).isoformat(),
                    }
                ),
                token=token,
            ),
            timeout=3.0,
        )
    except Exception as e:
        record_suppressed_error("wa_thread", "save", e)


async def api_whatsapp_chat(request: Request) -> JSONResponse:
    """POST /api/internal/whatsapp-chat — conversational Claude response."""
    auth = _check_api_auth(request)
    if auth:
        return auth
    if not _check_expensive_rate_limit():
        return _cors_json(
            {"error": "Too many AI requests. Try again in a few minutes."},
            status_code=429,
            request=request,
        )
    try:
        body = json.loads(await request.body())
        message = body.get("message", "")
        phone = body.get("phone", "unknown")
        lang = body.get("lang", "sk")
        if lang not in ("sk", "en"):
            lang = "sk"
        patient_id = body.get("patient_id", "")
        user_name = body.get("user_name", "")
        user_roles = body.get("user_roles", [])
    except Exception:
        return _cors_json({"error": "Invalid request body"}, status_code=400, request=request)

    if not _check_fup_ai_query(patient_id or "global"):
        return _cors_json(
            {"error": f"Monthly AI query limit reached ({FUP_AI_QUERIES_PER_MONTH})."},
            status_code=429,
            request=request,
        )
    try:
        # Input validation: reject empty or excessively long messages
        if not message or not message.strip():
            return _cors_json({"error": "Empty message"}, status_code=400, request=request)
        if len(message) > 2000:
            message = message[:2000]  # Truncate to avoid inflated token costs

        if not ANTHROPIC_API_KEY:
            return _cors_json({"error": "AI not configured"}, status_code=500)

        # Fail fast if oncofiles is down — don't waste API call on doomed tool use
        cb = oncofiles_client.get_circuit_breaker_status()
        if cb["state"] == "open":
            msg = (
                "Databáza je dočasne nedostupná. Skúste znova o minútu."
                if lang == "sk"
                else "Database temporarily unavailable. Try again in a minute."
            )
            return _cors_json({"response": msg, "cost": 0})

        pid = patient_id or DEFAULT_PATIENT_ID
        token = _get_token_for_patient(pid)

        # Load conversation thread (non-blocking, 3s timeout)
        thread = await _load_wa_thread(phone, token=token, patient_id=pid)

        # Build prompt with conversation context
        history_block = ""
        if thread:
            history_block = "Previous conversation:\n"
            for ex in thread:
                history_block += f"User: {ex.get('user', '')}\n"
                history_block += f"Assistant: {ex.get('assistant', '')}\n"
            history_block += "\n"

        # Build patient name map for name resolution
        patient_names = _get_patient_name_map()
        name_map_str = ", ".join(f"{k}={v}" for k, v in patient_names.items())
        current_display = patient_names.get(pid, pid)

        # Build user identity block
        user_block = ""
        if user_name:
            user_block += f"User name: {user_name}. "
        if user_roles:
            roles_str = ", ".join(user_roles) if isinstance(user_roles, list) else str(user_roles)
            user_block += f"Role: {roles_str}. "

        prompt = (
            f"{history_block}"
            f"User message via WhatsApp "
            f"(lang: {lang}, patient: {pid} = {current_display}):"
            f"\n\n{message}\n\n"
            f"# Context\n"
            f"{user_block}"
            f"Patient name map: {name_map_str}. "
            f"Currently showing: {pid} ({current_display}).\n"
            f"If user mentions another patient by name, tell them to "
            f"send 'prepni <slug>' to switch.\n\n"
            f"# Instructions\n"
            f"Respond naturally in "
            f"{'Slovak' if lang == 'sk' else 'English'}. "
            f"Address the user by name when natural. "
            f"Do NOT list available commands unless the user asks "
            f"for help. "
            f"If you cannot answer with available data, suggest ONE "
            f"specific command (e.g. 'labky'). "
            f"Max 1500 chars."
        )

        result = await run_autonomous_task(
            prompt,
            max_turns=5,
            task_name="whatsapp_chat",
            model=AUTONOMOUS_MODEL_LIGHT,
            patient_id=pid,
        )

        response_text = result.get("response", "")
        if not response_text:
            response_text = (
                "Prepáčte, nepodarilo sa spracovať správu. Skúste 'pomoc'."
                if lang == "sk"
                else "Sorry, I couldn't process that. Try 'help'."
            )

        response_text = response_text[:1500]

        # Quality signal tags for continuous improvement
        quality_tags: list[str] = [
            "wa:chat",
            f"lang:{lang}",
            f"patient:{pid}",
        ]
        if user_name:
            quality_tags.append(f"user:{user_name}")
        # Detect quality issues for audit
        response_lower = response_text.lower()
        if any(cmd in response_lower for cmd in ["labky,", "lieky,", "pomoc.", "dostupné príkazy"]):
            quality_tags.append("wa:quality:command_dump")
        if response_text == result.get("response", ""):
            pass  # normal
        else:
            quality_tags.append("wa:quality:fallback")
        if len(response_text) > 1200:
            quality_tags.append("wa:quality:long")

        # Save updated thread (non-blocking)
        thread.append({"user": message[:500], "assistant": response_text[:500]})
        asyncio.create_task(_save_wa_thread(phone, thread, token=token, patient_id=pid))

        return _cors_json(
            {
                "response": response_text,
                "cost": result.get("cost", 0),
                "thread_length": min(len(thread), _WA_THREAD_MAX_EXCHANGES),
                "quality_tags": quality_tags,
            }
        )
    except Exception as e:
        record_suppressed_error("api_whatsapp_chat", "chat", e)
        return _cors_json(
            {
                "response": "Error processing message. Try 'help'.",
                "error": str(e),
            }
        )


async def api_bug_report(request: Request) -> JSONResponse:
    """POST /api/bug-report — create a GitHub issue from dashboard bug reporter.

    Expects JSON: {description: str, url: str, route: str, viewport: str,
                    role: str, locale: str}
    """
    auth = _check_api_auth(request)
    if auth:
        return auth
    try:
        body = json.loads(await request.body())
    except (json.JSONDecodeError, Exception):
        return _cors_json({"error": "Invalid JSON"}, status_code=400)

    description = body.get("description", "").strip()
    if not description:
        return _cors_json({"error": "description is required"}, status_code=400)

    url = body.get("url", "")
    route = body.get("route", "")
    viewport = body.get("viewport", "")
    role = body.get("role", "")
    locale = body.get("locale", "")
    # page_text removed — auto-capture of DOM content is an injection risk.
    user_agent = request.headers.get("user-agent", "")[:200]

    from datetime import UTC, datetime

    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    page_file = route.strip("/") or "index"

    issue_body = (
        f"## Bug Report\n\n"
        f"**{description}**\n\n"
        f"### Context\n"
        f"| Field | Value |\n|-------|-------|\n"
        f"| Page | `{route}` |\n"
        f"| URL | {url} |\n"
        f"| Viewport | {viewport} |\n"
        f"| Role | {role} |\n"
        f"| Locale | {locale} |\n"
        f"| User Agent | {user_agent[:100]} |\n"
        f"| Reported | {now_str} |\n\n"
        f"### For Claude Code\n"
        f"- **File**: `dashboard/app/pages/{page_file}.vue`\n"
        f"- **Repro**: `{url}` as `{role}` / `{locale}`\n"
        f"- **Checklist**: [ ] Root cause [ ] Fix [ ] Test\n\n"
        f"---\n*Reported via dashboard bug reporter*\n"
    )

    try:
        from .github_client import create_issue

        result = await create_issue(
            repo="peter-fusek/oncoteam",
            title=f"Bug: {description[:80]}",
            body=issue_body,
            labels=["bug"],
        )
        return _cors_json({"created": True, **result})
    except Exception as e:
        record_suppressed_error("api_bug_report", "create_issue", e)
        return _cors_json({"error": str(e)}, status_code=502)


async def api_document_webhook(request: Request) -> JSONResponse:
    """POST /api/internal/document-webhook — triggered by oncofiles on new upload.

    Expects JSON body: {document_id: int, patient_id?: str, filename?: str,
    category?: str, uploaded_at?: str}
    Launches the document pipeline as a background task.
    """
    import asyncio

    from .autonomous_tasks import _extract_timestamp, _get_state, run_document_pipeline

    if not _check_expensive_rate_limit():
        return _cors_json(
            {"error": "Too many pipeline triggers. Try again later."},
            status_code=429,
            request=request,
        )

    try:
        body = await request.json()
    except Exception:
        return _cors_json({"error": "Invalid JSON body"}, status_code=400, request=request)

    document_id = body.get("document_id")
    if not isinstance(document_id, int) or document_id <= 0:
        return _cors_json(
            {"error": "document_id must be a positive integer"}, status_code=400, request=request
        )

    patient_id = body.get("patient_id", DEFAULT_PATIENT_ID)
    token = _get_token_for_patient(patient_id)

    # Quick dedup check before launching background task
    existing = await _get_state(f"pipeline:{document_id}", token=token)
    if _extract_timestamp(existing):
        return _cors_json(
            {"status": "already_processed", "document_id": document_id}, request=request
        )

    metadata = {
        "filename": body.get("filename", ""),
        "category": body.get("category", ""),
        "uploaded_at": body.get("uploaded_at", ""),
    }

    # Auto-fill metadata from oncofiles when webhook doesn't provide it
    if not metadata["category"]:
        try:
            doc = await asyncio.wait_for(
                oncofiles_client.get_document_by_id(document_id),
                timeout=5,
            )
            if isinstance(doc, dict):
                metadata["category"] = doc.get("category", "")
                metadata["filename"] = metadata["filename"] or doc.get("filename", "")
        except Exception as exc:
            record_suppressed_error("api_document_webhook", "get_document_by_id", exc)

    asyncio.create_task(run_document_pipeline(document_id, metadata, patient_id=patient_id))
    _logger.info("Document pipeline started for doc %d (patient=%s)", document_id, patient_id)

    return _cors_json(
        {"status": "pipeline_started", "document_id": document_id, "patient_id": patient_id},
        request=request,
    )


async def api_trigger_agent(request: Request) -> JSONResponse:
    """POST /api/internal/trigger-agent — manually trigger a full agent run.

    Expects JSON body: {agent_id: str}
    Launches the agent as a background task with full resources (no cooldown skip).
    """
    import asyncio

    from .agent_registry import AGENT_REGISTRY

    if not _check_expensive_rate_limit():
        return _cors_json(
            {"error": "Too many agent triggers. Try again later."},
            status_code=429,
            request=request,
        )

    try:
        body = await request.json()
    except Exception:
        return _cors_json({"error": "Invalid JSON body"}, status_code=400, request=request)

    agent_id = body.get("agent_id", "")
    trigger_patient_id = body.get("patient_id", "")

    if not _check_fup_agent_run(trigger_patient_id or "global"):
        return _cors_json(
            {"error": f"Monthly agent run limit reached ({FUP_AGENT_RUNS_PER_MONTH})."},
            status_code=429,
            request=request,
        )
    if agent_id not in AGENT_REGISTRY:
        return _cors_json(
            {"error": f"Unknown agent: {agent_id}", "available": list(AGENT_REGISTRY.keys())},
            status_code=400,
            request=request,
        )

    # Import task functions dynamically (same map as scheduler.py)
    from .scheduler import _get_task_functions

    task_functions = _get_task_functions()
    func = task_functions.get(agent_id)
    if func is None:
        return _cors_json(
            {"error": f"No runnable function for agent: {agent_id}"},
            status_code=400,
            request=request,
        )

    # Clear cooldown state so the agent runs unconditionally
    effective_patient_id = trigger_patient_id or DEFAULT_PATIENT_ID
    token = _get_token_for_patient(effective_patient_id)
    try:
        await oncofiles_client.set_agent_state(
            f"last_{agent_id}:{effective_patient_id}", {}, token=token
        )
        _logger.info("Cleared cooldown for %s:%s", agent_id, effective_patient_id)
    except Exception as e:
        _logger.warning("Could not clear cooldown for %s: %s", agent_id, e)

    asyncio.create_task(func(patient_id=effective_patient_id))
    _logger.info("Manually triggered agent: %s (patient=%s)", agent_id, effective_patient_id)

    return _cors_json({"status": "triggered", "agent_id": agent_id}, request=request)


_FUNNEL_STAGES = ("Excluded", "Later Line", "Watching", "Eligible Now", "Action Needed")

_FUNNEL_SYSTEM_PROMPT_TEMPLATE = """\
You are a clinical trial funnel classifier for cancer treatment management.
Classify this trial into exactly one funnel stage for the patient.

## Funnel Stages
- **Excluded**: Biomarker contraindication, eligibility hard-stop, or incompatible \
with patient's surgical history
- **Later Line**: Trial is for 2nd-line, 3rd-line, or later treatment. \
Keywords: "previously treated", "refractory", "after progression on", \
"second-line", "third-line", "2L", "3L", "salvage", "post-progression". \
Patient is currently on 1st-line — these trials are NOT yet applicable.
- **Watching**: Relevant to patient's cancer type and biomarkers, no \
contraindication, but not currently actionable (e.g. not yet recruiting, \
distant geography, phase I only, or insufficient data)
- **Eligible Now**: Patient meets known criteria, trial is recruiting, \
reachable geography (Slovakia/EU)
- **Action Needed**: Eligible AND requires immediate action (enrollment \
closing soon, limited slots)

## Patient Profile
{patient_rules}

## Patient-Specific Exclusions
Apply the patient's excluded_therapies as hard exclusion rules.
Trials requiring "treatment-naive" or "no prior surgery" are EXCLUDED if patient had prior surgery.

## Classification Rules
1. If trial mentions 2L/3L/refractory/post-progression → "Later Line"
2. If biomarker contraindication → "Excluded" with exclusion_reason
3. If trial requires no prior resection and patient had surgery → "Excluded"
4. If recruiting in EU/Slovakia and patient meets criteria → "Eligible Now"
5. Otherwise → "Watching"

You MUST respond with ONLY a valid JSON object. No markdown, no explanation:
{"stage": "<one of the 5 stages>", "exclusion_reason": "<null or string>", \
"next_step": "<1 sentence recommendation>", "deadline_note": "<null or string>"}
"""


async def api_assess_funnel(request: Request) -> JSONResponse:
    """POST /api/research/assess-funnel — AI-classify trials into funnel stages."""
    auth = _check_api_auth(request)
    if auth:
        return auth
    if not _check_expensive_rate_limit():
        return _cors_json(
            {"error": "Too many AI requests. Try again in a few minutes."},
            status_code=429,
            request=request,
        )
    try:
        body = json.loads(await request.body())
    except (json.JSONDecodeError, Exception):
        return _cors_json({"error": "Invalid JSON"}, status_code=400, request=request)

    trials = body.get("trials", [])
    if not isinstance(trials, list) or len(trials) > 50:
        return _cors_json(
            {"error": "trials must be a list of max 50 entries"},
            status_code=400,
            request=request,
        )
    if not trials:
        return _cors_json({"assessments": [], "cost_usd": 0}, request=request)

    if not ANTHROPIC_API_KEY:
        return _cors_json({"error": "AI not configured"}, status_code=500, request=request)

    from anthropic import AsyncAnthropic

    from .patient_context import build_biomarker_rules

    patient = _get_patient_for_request(request)
    patient_rules = build_biomarker_rules(patient)
    funnel_prompt = _FUNNEL_SYSTEM_PROMPT_TEMPLATE.format(patient_rules=patient_rules)

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    total_cost = 0.0
    sem = asyncio.Semaphore(5)  # 5 concurrent Haiku calls

    async def _assess_one(trial: dict) -> dict:
        nonlocal total_cost
        nct_id = trial.get("external_id", "")
        user_msg = (
            f"Trial: {nct_id}\nTitle: {trial.get('title', '')}\n"
            f"Summary: {trial.get('summary', '')[:500]}\n"
            f"Current relevance: {trial.get('relevance', '')} ({trial.get('relevance_reason', '')})"
        )
        async with sem:
            try:
                resp = await client.messages.create(
                    model=AUTONOMOUS_MODEL_LIGHT,
                    max_tokens=256,
                    system=funnel_prompt,
                    messages=[{"role": "user", "content": user_msg}],
                )
                text = resp.content[0].text if resp.content else "{}"
                cost = (resp.usage.input_tokens * 0.80 + resp.usage.output_tokens * 4.0) / 1_000_000
                total_cost += cost
                # Extract JSON from response (Haiku may wrap in markdown)
                clean = text.strip()
                if "```" in clean:
                    clean = re.sub(r"```(?:json)?\s*", "", clean).strip().rstrip("`")
                # Find first { ... } block
                start = clean.find("{")
                end = clean.rfind("}") + 1
                if start >= 0 and end > start:
                    clean = clean[start:end]
                parsed = json.loads(clean)
                stage = parsed.get("stage", "Watching")
                if stage not in _FUNNEL_STAGES:
                    stage = "Watching"
                return {
                    "nct_id": nct_id,
                    "oncofiles_id": trial.get("id"),
                    "stage": stage,
                    "exclusion_reason": parsed.get("exclusion_reason"),
                    "next_step": parsed.get("next_step", "Review trial details"),
                    "deadline_note": parsed.get("deadline_note"),
                }
            except Exception as e:
                record_suppressed_error("api_assess_funnel", f"assess_{nct_id}", e)
                return {
                    "nct_id": nct_id,
                    "oncofiles_id": trial.get("id"),
                    "stage": "Watching",
                    "exclusion_reason": None,
                    "next_step": "Assessment failed — review manually",
                    "deadline_note": None,
                }

    assessments = await asyncio.gather(*[_assess_one(t) for t in trials])

    return _cors_json(
        {
            "assessments": list(assessments),
            "model": AUTONOMOUS_MODEL_LIGHT,
            "cost_usd": round(total_cost, 4),
        },
        request=request,
    )


async def api_whatsapp_media(request: Request) -> JSONResponse:
    """POST /api/internal/whatsapp-media — process WhatsApp media attachment.

    Expects JSON body: {media_base64, content_type, filename, phone, patient_id}
    Uploads to oncofiles, triggers AI analysis, returns document_id + summary.
    """
    try:
        body = await request.json()
    except Exception:
        return _cors_json({"error": "Invalid JSON body"}, status_code=400, request=request)

    media_base64 = (body.get("media_base64") or "").strip()
    content_type = (body.get("content_type") or "").strip()
    filename = (body.get("filename") or "").strip()
    phone = (body.get("phone") or "").strip()
    patient_id = (body.get("patient_id") or "").strip()

    if not media_base64 or not content_type or not filename:
        return _cors_json(
            {"error": "media_base64, content_type, and filename are required"},
            status_code=400,
            request=request,
        )

    # Content type allowlist — prevent content injection
    allowed_types = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "application/pdf",
    }
    if content_type not in allowed_types:
        return _cors_json(
            {"error": f"Unsupported content type: {content_type}"},
            status_code=400,
            request=request,
        )

    # FUP limit check (per-patient)
    if not _check_fup_ai_query(patient_id or "global"):
        return _cors_json(
            {"error": "Monthly AI query limit exceeded"},
            status_code=429,
            request=request,
        )

    # Step 1: Upload document to oncofiles
    try:
        upload_result = await oncofiles_client.upload_document_via_mcp(
            content_base64=media_base64,
            filename=filename,
            content_type=content_type,
            patient_id=patient_id,
        )
    except Exception as exc:
        record_suppressed_error("api_whatsapp_media", "upload_document", exc)
        return _cors_json(
            {"error": f"Failed to upload document: {exc}"},
            status_code=502,
            request=request,
        )

    document_id = ""
    if isinstance(upload_result, dict):
        document_id = str(upload_result.get("document_id", upload_result.get("id", "")))

    if not document_id:
        _logger.error("upload_document returned no document_id: %s", upload_result)
        return _cors_json(
            {"error": "Upload succeeded but no document_id returned"},
            status_code=502,
            request=request,
        )

    # Step 2: Trigger OCR + AI analysis
    summary = ""
    if document_id:
        try:
            enhance_result = await oncofiles_client.enhance_document_via_mcp(document_id)
            if isinstance(enhance_result, dict):
                summary = enhance_result.get("summary", enhance_result.get("text", ""))
        except Exception as exc:
            record_suppressed_error("api_whatsapp_media", "enhance_document", exc)
            summary = "Document uploaded but analysis failed."

    # Step 3: Trigger document pipeline (lab_sync, dose_extraction, etc.)
    # Same logic as api_document_webhook but inline to avoid duplicate upload
    pipeline_status = "not_triggered"
    if document_id:
        try:
            from .autonomous_tasks import run_document_pipeline

            pid = patient_id or DEFAULT_PATIENT_ID
            doc_id_int = int(document_id)
            metadata = {
                "filename": filename,
                "category": "",
                "uploaded_at": "",
            }
            asyncio.create_task(run_document_pipeline(doc_id_int, metadata, patient_id=pid))
            pipeline_status = "started"
            _logger.info(
                "Document pipeline triggered from WhatsApp media: doc_id=%s, patient=%s",
                document_id,
                pid,
            )
        except Exception as exc:
            record_suppressed_error("api_whatsapp_media", "trigger_pipeline", exc)
            pipeline_status = "failed"

    _logger.info(
        "WhatsApp media processed: phone=%s, file=%s, doc_id=%s, pipeline=%s",
        phone[:6] + "..." if phone else "?",
        filename,
        document_id,
        pipeline_status,
    )

    return _cors_json(
        {
            "status": "ok",
            "document_id": document_id,
            "summary": summary,
            "pipeline": pipeline_status,
        },
        request=request,
    )


async def api_whatsapp_voice(request: Request) -> JSONResponse:
    """POST /api/internal/whatsapp-voice — transcribe voice note via Whisper.

    Accepts {audio_base64, content_type, phone, patient_id, lang_hint}.
    Returns {text, duration_s, cost, lang} or {error}.
    Audio is ephemeral — never stored.
    """
    # Parse body with 15MB limit (audio base64 can exceed default 1MB)
    import json as _json

    try:
        raw = await request.body()
        if len(raw) > 15_000_000:
            return _cors_json({"error": "Request too large"}, status_code=400, request=request)
        body = _json.loads(raw)
    except Exception:
        return _cors_json({"error": "Invalid JSON"}, status_code=400, request=request)

    audio_b64 = body.get("audio_base64", "")
    content_type = body.get("content_type", "audio/ogg")
    patient_id = body.get("patient_id", "q1b")
    lang_hint = body.get("lang_hint", "sk")

    if not audio_b64:
        return _cors_json({"error": "Missing audio_base64"}, status_code=400, request=request)

    import base64

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception:
        return _cors_json({"error": "Invalid base64 audio"}, status_code=400, request=request)

    # Size guards
    if len(audio_bytes) < 1024:
        return _cors_json({"error": "Audio too short"}, status_code=400, request=request)
    if len(audio_bytes) > 10 * 1024 * 1024:
        return _cors_json({"error": "Audio too large (max 10MB)"}, status_code=400, request=request)

    from .whisper_client import transcribe_audio

    result = await transcribe_audio(
        audio_bytes=audio_bytes,
        content_type=content_type,
        patient_id=patient_id,
        lang_hint=lang_hint,
    )

    if "error" in result:
        return _cors_json(result, status_code=503, request=request)

    return _cors_json(result, request=request)


async def api_patients(request: Request) -> JSONResponse:
    """GET /api/patients — list all active patients with doc counts."""
    token = _get_token_for_patient(_get_patient_id(request))
    try:
        result = await oncofiles_client.list_patients(token=token)
        patients = result if isinstance(result, list) else result.get("patients", [])
        return _cors_json({"patients": patients}, request=request)
    except Exception as exc:
        record_suppressed_error("api_patients", "list_patients", exc)
        # Fallback to local registry
        from .patient_context import get_patient, list_patient_ids

        patients = []
        for pid in list_patient_ids():
            try:
                p = get_patient(pid)
                patients.append(
                    {
                        "slug": pid,
                        "name": p.name,
                        "patient_type": (
                            "general" if p.diagnosis_code.startswith("Z") else "oncology"
                        ),
                    }
                )
            except Exception:
                continue
        return _cors_json({"patients": patients, "source": "local"}, request=request)


async def api_onboard_patient(request: Request) -> JSONResponse:
    """POST /api/internal/onboard-patient — create a new patient in oncofiles and register locally.

    Expects JSON body: {patient_id, display_name, diagnosis_summary?, preferred_lang?, phone?}
    Returns: {patient_id, bearer_token, status: "created"} or {status: "exists"} on 409.
    """
    import httpx as _httpx

    from .models import PatientProfile
    from .patient_context import register_patient

    try:
        body = await request.json()
    except Exception:
        return _cors_json({"error": "Invalid JSON body"}, status_code=400, request=request)

    patient_id = (body.get("patient_id") or "").strip()
    # Accept both field name variants (frontend sends patient_name)
    display_name = (body.get("display_name") or body.get("patient_name") or "").strip()
    if not patient_id or not display_name:
        return _cors_json(
            {"error": "patient_id and display_name are required"},
            status_code=400,
            request=request,
        )

    diagnosis_summary = body.get("diagnosis_summary", body.get("diagnosis", ""))
    preferred_lang = body.get("preferred_lang", body.get("lang", "sk"))

    try:
        result = await oncofiles_client.create_patient_via_api(
            patient_id=patient_id,
            display_name=display_name,
            diagnosis_summary=diagnosis_summary,
            preferred_lang=preferred_lang,
            caregiver_email="",
        )
    except _httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            _logger.info("Patient %s already exists in oncofiles", patient_id)
            return _cors_json(
                {"patient_id": patient_id, "status": "exists"},
                request=request,
            )
        record_suppressed_error("api_onboard_patient", "create_patient", exc)
        return _cors_json(
            {"error": f"Oncofiles error: {exc.response.status_code}"},
            status_code=502,
            request=request,
        )
    except Exception as exc:
        record_suppressed_error("api_onboard_patient", "create_patient", exc)
        return _cors_json(
            {"error": f"Failed to create patient: {exc}"},
            status_code=502,
            request=request,
        )

    # Register in oncoteam's in-memory patient registry
    bearer_token = result.get("bearer_token", "")
    profile = PatientProfile(
        patient_id=patient_id,
        name=display_name,
        diagnosis_code="",
        diagnosis_description=diagnosis_summary,
        tumor_site="",
        treatment_regimen="",
    )
    try:
        register_patient(patient_id=patient_id, token=bearer_token, profile=profile)
    except Exception as exc:
        record_suppressed_error("api_onboard_patient", "register_patient", exc)
        # Non-fatal — patient was created in oncofiles, just not registered locally

    # Persist token for reload after restart (#265)
    if bearer_token:
        asyncio.ensure_future(_persist_patient_token(patient_id, bearer_token))

    _logger.info("Onboarded patient %s", patient_id)

    return _cors_json(
        {
            "patient_id": patient_id,
            "bearer_token": bearer_token,
            "status": "created",
        },
        request=request,
    )


async def api_onboarding_status(request: Request) -> JSONResponse:
    """POST /api/internal/onboarding-status — check onboarding state for a phone number.

    Expects JSON body: {phone}
    Returns: {status: "unknown"} — placeholder for #137 state machine.
    """
    try:
        body = await request.json()
    except Exception:
        return _cors_json({"error": "Invalid JSON body"}, status_code=400, request=request)

    phone = (body.get("phone") or "").strip()
    if not phone:
        return _cors_json({"error": "phone is required"}, status_code=400, request=request)

    # Check if the phone is in the approved set (includes oncofiles-persisted phones)
    approved = is_phone_approved(phone)
    return _cors_json(
        {
            "phone": phone,
            "status": "approved" if approved else "unknown",
            "approved": approved,
            "patient_id": _phone_patient_map.get(phone, ""),
        },
        request=request,
    )


# In-memory set of admin-approved WhatsApp phone numbers (#141)
_approved_phones: set[str] = set()
_approved_phones_loaded = False
_phone_patient_map: dict[str, str] = {}  # phone → patient_id


def is_phone_approved(phone: str) -> bool:
    """Check if a phone number has been approved by an admin."""
    return phone in _approved_phones


async def load_approved_phones() -> None:
    """Load approved phones from oncofiles on startup. Safe to call multiple times."""
    global _approved_phones_loaded
    if _approved_phones_loaded:
        return
    try:
        result = await oncofiles_client.get_agent_state(key="phones", agent_id="approved_phones")
        phones = []
        if isinstance(result, dict):
            # The state value may be nested under "value" or "state"
            data = result.get("value") or result.get("state") or result
            if isinstance(data, str):
                data = json.loads(data)
            if isinstance(data, dict):
                phones = data.get("phones", [])
            elif isinstance(data, list):
                phones = data
        for p in phones:
            if isinstance(p, str) and p.strip():
                _approved_phones.add(p.strip())
        _approved_phones_loaded = True
        if _approved_phones:
            _logger.info("Loaded %d approved phones from oncofiles", len(_approved_phones))
    except Exception as exc:
        record_suppressed_error("load_approved_phones", "get_agent_state", exc)
        _logger.warning("Failed to load approved phones from oncofiles: %s", exc)


async def load_patient_tokens() -> None:
    """Restore patient tokens from oncofiles agent_state on startup."""
    from .patient_context import _patient_tokens

    try:
        raw = await oncofiles_client.get_agent_state(
            key="tokens", agent_id="patient_token_registry"
        )
        if isinstance(raw, dict):
            data = raw.get("value") or raw.get("state") or raw
            if isinstance(data, dict):
                tokens = data.get("tokens", {})
                for pid, tok in tokens.items():
                    if tok and pid not in _patient_tokens:
                        _patient_tokens[pid] = tok
                        _logger.info("Restored token for patient %s from agent_state", pid)
    except Exception as exc:
        _logger.warning("Failed to load patient tokens from agent_state: %s", exc)


async def _persist_approved_phones() -> None:
    """Persist the current approved phones set to oncofiles."""
    try:
        await oncofiles_client.set_agent_state(
            key="phones",
            value={"phones": sorted(_approved_phones)},
            agent_id="approved_phones",
        )
    except Exception as exc:
        record_suppressed_error("_persist_approved_phones", "set_agent_state", exc)
        _logger.warning("Failed to persist approved phones to oncofiles: %s", exc)


async def _persist_patient_token(patient_id: str, token: str) -> None:
    """Persist a patient's oncofiles bearer token to agent_state for reload."""
    from datetime import UTC
    from datetime import datetime as _dt

    try:
        raw = await oncofiles_client.get_agent_state(
            key="tokens", agent_id="patient_token_registry"
        )
        registry: dict[str, str] = {}
        if isinstance(raw, dict):
            data = raw.get("value") or raw.get("state") or raw
            if isinstance(data, dict):
                registry = data.get("tokens", {})
        registry[patient_id] = token
        await oncofiles_client.set_agent_state(
            key="tokens",
            value={
                "tokens": registry,
                "updated_at": _dt.now(UTC).isoformat(),
            },
            agent_id="patient_token_registry",
        )
    except Exception as exc:
        _logger.warning("Failed to persist patient token for %s: %s", patient_id, exc)


async def api_approve_user(request: Request) -> JSONResponse:
    """POST /api/internal/approve-user — admin approves a new WhatsApp user.

    Expects JSON body: {phone}
    Stores phone in the in-memory approved set and persists to oncofiles.
    Returns: {status: "approved", phone: str}
    """
    try:
        body = await request.json()
    except Exception:
        return _cors_json({"error": "Invalid JSON body"}, status_code=400, request=request)

    phone = (body.get("phone") or "").strip()
    if not phone:
        return _cors_json({"error": "phone is required"}, status_code=400, request=request)

    _approved_phones.add(phone)

    # Optionally link phone to a patient_id (#265)
    patient_id_for_phone = (body.get("patient_id") or "").strip()
    if patient_id_for_phone:
        _phone_patient_map[phone] = patient_id_for_phone

    _logger.info("Admin approved WhatsApp user: %s", phone)

    # Persist to oncofiles (fire-and-forget, don't block response)
    asyncio.ensure_future(_persist_approved_phones())

    return _cors_json({"status": "approved", "phone": phone}, request=request)


# ---------------------------------------------------------------------------
# Access rights (ROLE_MAP in database)
# ---------------------------------------------------------------------------

_access_rights_cache: dict[str, object] = {}
_access_rights_ts: float = 0.0
_ACCESS_RIGHTS_TTL = 60.0


async def _load_access_rights() -> dict[str, object]:
    """Load access rights from oncofiles agent_state, with 60s cache."""
    global _access_rights_cache, _access_rights_ts
    now = time.monotonic()
    if _access_rights_cache and (now - _access_rights_ts) < _ACCESS_RIGHTS_TTL:
        return _access_rights_cache
    try:
        raw = await oncofiles_client.get_agent_state(key="role_map", agent_id="access_rights")
        if isinstance(raw, dict):
            data = raw.get("value") or raw.get("state") or raw
            if isinstance(data, str):
                data = json.loads(data)
            if isinstance(data, dict):
                role_map = data.get("role_map", data)
                _access_rights_cache = role_map
                _access_rights_ts = now
                return role_map
    except Exception as exc:
        record_suppressed_error("_load_access_rights", "get_agent_state", exc)
        _logger.warning("Failed to load access rights: %s", exc)
    return _access_rights_cache


async def api_access_rights_get(request: Request) -> JSONResponse:
    """GET /api/internal/access-rights — read the role map from database."""
    role_map = await _load_access_rights()
    return _cors_json({"role_map": role_map}, request=request)


async def api_access_rights_set(request: Request) -> JSONResponse:
    """POST /api/internal/access-rights — update the role map in database.

    Expects JSON body: {role_map: {...}}
    """
    global _access_rights_cache, _access_rights_ts
    try:
        body = await request.json()
    except Exception:
        return _cors_json({"error": "Invalid JSON body"}, status_code=400, request=request)

    role_map = body.get("role_map")
    if not isinstance(role_map, dict):
        return _cors_json(
            {"error": "role_map must be a JSON object"}, status_code=400, request=request
        )

    from datetime import UTC
    from datetime import datetime as _dt

    try:
        await oncofiles_client.set_agent_state(
            key="role_map",
            value={
                "role_map": role_map,
                "updated_at": _dt.now(UTC).isoformat(),
            },
            agent_id="access_rights",
        )
        _access_rights_cache = role_map
        _access_rights_ts = time.monotonic()
        _logger.info("Access rights updated: %d entries", len(role_map))
        return _cors_json({"status": "updated", "entries": len(role_map)}, request=request)
    except Exception as exc:
        record_suppressed_error("api_access_rights_set", "set_agent_state", exc)
        return _cors_json({"error": f"Failed to persist: {exc}"}, status_code=500, request=request)


async def api_whatsapp_status(request: Request) -> JSONResponse:
    """GET /api/whatsapp/status — WhatsApp integration status.

    Returns: approved phones count, active onboarding sessions,
    recent message stats, and circuit breaker state.
    """
    # Approved phones
    if not _approved_phones_loaded:
        await load_approved_phones()

    # Recent WhatsApp conversations (last 24h)
    recent_count = 0
    try:
        result = await asyncio.wait_for(
            oncofiles_client.search_conversations(
                query="sys:whatsapp",
                limit=100,
            ),
            timeout=8,
        )
        entries = _extract_list(result, "entries")
        recent_count = len(entries)
    except Exception as exc:
        record_suppressed_error("api_whatsapp_status", "search_conversations", exc)

    cb_status = oncofiles_client.get_circuit_breaker_status()

    return _cors_json(
        {
            "status": "ok" if cb_status["state"] == "closed" else "degraded",
            "approved_phones": len(_approved_phones),
            "phone_patient_map": {p: pid for p, pid in _phone_patient_map.items()},
            "recent_conversations": recent_count,
            "circuit_breaker_state": cb_status["state"],
        },
        request=request,
    )


async def api_cors_preflight(request: Request) -> JSONResponse:
    """OPTIONS handler for CORS preflight on all /api/* routes."""
    return _cors_json({}, request=request)
