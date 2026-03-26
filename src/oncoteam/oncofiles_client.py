from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from .config import ONCOFILES_MCP_TOKEN, ONCOFILES_MCP_URL

_logger = logging.getLogger("oncoteam.oncofiles_client")

if not ONCOFILES_MCP_URL:
    _logger.warning("ONCOFILES_MCP_URL not set — oncofiles calls will fail")
if ONCOFILES_MCP_URL and not ONCOFILES_MCP_TOKEN:
    _logger.warning("ONCOFILES_MCP_TOKEN not set — connecting to oncofiles without auth")

# Persistent connections — one per patient token. Reused to avoid per-call overhead.
# Key: token string (or "" for default). Value: MCP Client.
_persistent_clients: dict[str, Client] = {}
_client_lock: asyncio.Lock | None = None

# ── Circuit breaker ──────────────────────────────────────────────────────
# After CIRCUIT_BREAKER_THRESHOLD consecutive failures within the window,
# all calls fail-fast for CIRCUIT_BREAKER_COOLDOWN seconds.
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_COOLDOWN = 30  # seconds
_circuit_failures: int = 0
_circuit_open_until: float = 0.0

# Per-call timeout (seconds) — prevents indefinite hangs when oncofiles is slow.
CALL_TIMEOUT = 20.0
# Max time to wait for a semaphore slot before rejecting the request (#173).
# Prevents zombie queue buildup when timed-out proxy requests keep holding slots.
SEMAPHORE_WAIT_TIMEOUT = 8.0

# ── Concurrency limiter ─────────────────────────────────────────────────
# Limits parallel oncofiles calls to prevent OOM on the server side.
# Excess calls queue behind the semaphore rather than piling on.
MAX_CONCURRENT_CALLS = 3
_concurrency_semaphore: asyncio.Semaphore | None = None

# Heavy queries (search_conversations, search_documents) get their own
# stricter semaphore — max 1 concurrent to avoid server OOM.
_HEAVY_TOOLS = frozenset({"search_conversations", "search_documents"})
_heavy_semaphore: asyncio.Semaphore | None = None

# ── RSS-based backoff ──────────────────────────────────────────────────
# Check oncofiles /health before calls; back off if memory is high.
RSS_WARN_MB = 400  # wait 30s before retry
RSS_CRITICAL_MB = 450  # back off 2 min
RSS_CHECK_INTERVAL = 60  # seconds between health checks (avoid per-call overhead)
_rss_backoff_until: float = 0.0
_rss_last_checked: float = 0.0
_total_rss_backoffs: int = 0


def _get_semaphore() -> asyncio.Semaphore:
    global _concurrency_semaphore
    if _concurrency_semaphore is None:
        _concurrency_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CALLS)
    return _concurrency_semaphore


def _get_heavy_semaphore() -> asyncio.Semaphore:
    global _heavy_semaphore
    if _heavy_semaphore is None:
        _heavy_semaphore = asyncio.Semaphore(1)
    return _heavy_semaphore


# ── Telemetry ────────────────────────────────────────────────────────────
_total_calls: int = 0
_total_errors: int = 0
_total_circuit_trips: int = 0
_total_queued: int = 0
_last_rss_mb: float | None = None


async def _check_rss_backoff() -> None:
    """Check oncofiles /health RSS and set backoff if memory is high.

    Throttled to once per RSS_CHECK_INTERVAL (60s) to avoid adding
    an HTTP roundtrip to every single oncofiles call.
    """
    global _rss_backoff_until, _total_rss_backoffs, _last_rss_mb, _rss_last_checked

    now = time.monotonic()
    if _rss_backoff_until > now:
        remaining = _rss_backoff_until - now
        raise ConnectionError(
            f"oncofiles RSS backoff — waiting {remaining:.0f}s (last RSS: {_last_rss_mb}MB)"
        )

    # Skip health check if we checked recently
    if now - _rss_last_checked < RSS_CHECK_INTERVAL:
        return

    if not ONCOFILES_MCP_URL:
        return

    _rss_last_checked = now
    base = ONCOFILES_MCP_URL.rsplit("/", 1)[0] if "/" in ONCOFILES_MCP_URL else ONCOFILES_MCP_URL
    try:
        async with httpx.AsyncClient(timeout=5) as http:
            resp = await http.get(f"{base}/health")
            if resp.status_code == 200:
                data = resp.json()
                rss = data.get("memory_rss_mb")
                if rss is not None:
                    _last_rss_mb = rss
                    if rss >= RSS_CRITICAL_MB:
                        _rss_backoff_until = now + 120
                        _total_rss_backoffs += 1
                        _logger.warning(
                            "oncofiles RSS %dMB >= %dMB — backing off 2min",
                            rss,
                            RSS_CRITICAL_MB,
                        )
                        raise ConnectionError(f"oncofiles RSS {rss}MB critical — backing off 120s")
                    elif rss >= RSS_WARN_MB:
                        _rss_backoff_until = now + 30
                        _total_rss_backoffs += 1
                        _logger.warning(
                            "oncofiles RSS %dMB >= %dMB — backing off 30s",
                            rss,
                            RSS_WARN_MB,
                        )
                        raise ConnectionError(f"oncofiles RSS {rss}MB high — backing off 30s")
    except ConnectionError:
        raise
    except Exception as e:
        _logger.debug("RSS check failed (non-blocking): %s", e)


def get_circuit_breaker_status() -> dict:
    """Return circuit breaker + concurrency + RSS state for health/diagnostics."""
    now = time.monotonic()
    is_open = _circuit_open_until > now
    rss_backing_off = _rss_backoff_until > now
    sem = _get_semaphore()
    return {
        "state": "open" if is_open else "closed",
        "consecutive_failures": _circuit_failures,
        "threshold": CIRCUIT_BREAKER_THRESHOLD,
        "cooldown_remaining_s": round(max(0, _circuit_open_until - now), 1) if is_open else 0,
        "total_calls": _total_calls,
        "total_errors": _total_errors,
        "total_circuit_trips": _total_circuit_trips,
        "total_queued": _total_queued,
        "total_rss_backoffs": _total_rss_backoffs,
        "call_timeout_s": CALL_TIMEOUT,
        "max_concurrent": MAX_CONCURRENT_CALLS,
        "available_slots": sem._value if hasattr(sem, "_value") else None,
        "oncofiles_rss_mb": _last_rss_mb,
        "rss_backoff_active": rss_backing_off,
        "rss_backoff_remaining_s": (
            round(max(0, _rss_backoff_until - now), 1) if rss_backing_off else 0
        ),
    }


def _get_lock() -> asyncio.Lock:
    global _client_lock
    if _client_lock is None:
        _client_lock = asyncio.Lock()
    return _client_lock


def _make_transport(token: str | None = None) -> StreamableHttpTransport:
    if not ONCOFILES_MCP_URL:
        raise RuntimeError(
            "ONCOFILES_MCP_URL not configured. Set the env var to connect to oncofiles."
        )
    auth = token or ONCOFILES_MCP_TOKEN or None
    return StreamableHttpTransport(ONCOFILES_MCP_URL, auth=auth)


async def _get_client(token: str | None = None) -> Client:
    """Return a persistent client for the given token, creating if necessary.

    Each unique token gets its own MCP connection (different patient data).
    Default token (None) uses ONCOFILES_MCP_TOKEN → Erika's data.
    """
    key = token or ""
    async with _get_lock():
        if key not in _persistent_clients:
            c = Client(_make_transport(token))
            await c.__aenter__()
            _persistent_clients[key] = c
            tok_label = key[:8] if key else "default"
            _logger.debug("Opened oncofiles connection (token=%s...)", tok_label)
        return _persistent_clients[key]


async def _invalidate_client(token: str | None = None) -> None:
    """Close and discard a persistent client so the next call reconnects."""
    key = token or ""
    async with _get_lock():
        client = _persistent_clients.pop(key, None)
        if client is not None:
            try:
                await client.__aexit__(None, None, None)
            except Exception as e:
                from .activity_logger import record_suppressed_error

                record_suppressed_error("oncofiles_client", "close_connection", e)
            tok_label = key[:8] if key else "default"
            _logger.debug("Closed oncofiles connection (token=%s...)", tok_label)


def _parse_result(result: object) -> dict | list | str:
    content = getattr(result, "content", None)
    if content and len(content) > 0 and hasattr(content[0], "text"):
        try:
            return json.loads(content[0].text)
        except (json.JSONDecodeError, TypeError):
            return content[0].text
    return str(result)


async def _call_with_retry(tool_name: str, arguments: dict, token: str | None) -> dict | list | str:
    """Execute an MCP call with one retry on failure."""
    global _circuit_failures, _circuit_open_until, _total_errors, _total_circuit_trips
    for attempt in range(2):
        try:
            client = await _get_client(token)
            result = await asyncio.wait_for(
                client.call_tool(tool_name, arguments),
                timeout=CALL_TIMEOUT,
            )
            _circuit_failures = 0
            return _parse_result(result)
        except Exception:
            if attempt == 0:
                await _invalidate_client(token)
                await asyncio.sleep(0.5)
                continue
            _total_errors += 1
            _circuit_failures += 1
            if _circuit_failures >= CIRCUIT_BREAKER_THRESHOLD:
                _circuit_open_until = time.monotonic() + CIRCUIT_BREAKER_COOLDOWN
                _total_circuit_trips += 1
                _logger.error(
                    "oncofiles circuit breaker OPEN after %d failures — blocking calls for %ds",
                    _circuit_failures,
                    CIRCUIT_BREAKER_COOLDOWN,
                )
            raise
    raise RuntimeError("_call_with_retry: unreachable")


async def call_oncofiles(
    tool_name: str, arguments: dict, *, token: str | None = None
) -> dict | list | str:
    """Call an oncofiles MCP tool, reusing a persistent connection.

    Args:
        token: Optional patient-specific bearer token. None = default (Erika).
               Each token scopes all data to one patient automatically.

    Includes RSS backoff, concurrency limiter, heavy-query gate,
    circuit breaker, per-call timeout, and retry with backoff.
    """
    global _circuit_failures, _circuit_open_until, _total_calls, _total_errors
    global _total_circuit_trips, _total_queued

    _total_calls += 1

    # Circuit breaker — fail fast when oncofiles is known to be down.
    now = time.monotonic()
    if _circuit_open_until > now:
        _total_errors += 1
        remaining = _circuit_open_until - now
        raise ConnectionError(
            f"oncofiles circuit breaker open — retrying in {remaining:.0f}s "
            f"(after {CIRCUIT_BREAKER_THRESHOLD} consecutive failures)"
        )

    # RSS-based backoff — don't pile on when oncofiles memory is high.
    try:
        await _check_rss_backoff()
    except ConnectionError:
        _total_errors += 1
        raise

    # Concurrency limiter — queue excess calls with timeout (#173).
    # Timeout prevents zombie queue buildup when proxy-cancelled requests hold slots.
    sem = _get_semaphore()
    is_heavy = tool_name in _HEAVY_TOOLS
    if sem.locked():
        _total_queued += 1
        _logger.debug("oncofiles call queued (%s) — max %d", tool_name, MAX_CONCURRENT_CALLS)

    try:
        await asyncio.wait_for(sem.acquire(), timeout=SEMAPHORE_WAIT_TIMEOUT)
    except TimeoutError:
        _total_errors += 1
        raise TimeoutError(
            f"oncofiles queue full for {tool_name} — rejected after {SEMAPHORE_WAIT_TIMEOUT}s wait"
        ) from None
    try:
        # Heavy queries get an extra gate — max 1 concurrent.
        if is_heavy:
            heavy_sem = _get_heavy_semaphore()
            try:
                await asyncio.wait_for(heavy_sem.acquire(), timeout=SEMAPHORE_WAIT_TIMEOUT)
            except TimeoutError:
                _total_errors += 1
                raise TimeoutError(
                    f"oncofiles heavy-query queue full for {tool_name} — rejected after "
                    f"{SEMAPHORE_WAIT_TIMEOUT}s wait"
                ) from None
            try:
                return await _call_with_retry(tool_name, arguments, token)
            finally:
                heavy_sem.release()
        else:
            return await _call_with_retry(tool_name, arguments, token)
    finally:
        sem.release()


async def search_documents(
    text: str,
    category: str | None = None,
    limit: int | None = None,
) -> dict:
    args: dict = {"text": text}
    if category:
        args["category"] = category
    if limit is not None:
        args["limit"] = limit
    return await call_oncofiles("search_documents", args)


def _validate_id(value: str | int, name: str = "id") -> str:
    """Validate document/file IDs at the boundary before sending to oncofiles."""
    s = str(value).strip()
    if not s or len(s) > 200:
        raise ValueError(f"Invalid {name}: must be 1-200 chars")
    return s


async def view_document(file_id: str) -> dict:
    return await call_oncofiles("view_document", {"file_id": _validate_id(file_id, "file_id")})


async def analyze_labs(file_id: str | None = None, limit: int = 10) -> dict:
    args: dict = {"limit": limit}
    if file_id:
        args["file_id"] = file_id
    return await call_oncofiles("analyze_labs", args)


async def compare_labs(file_id_a: str, file_id_b: str) -> dict:
    return await call_oncofiles("compare_labs", {"file_id_a": file_id_a, "file_id_b": file_id_b})


async def get_document(document_id: int) -> dict:
    doc_id = int(_validate_id(document_id, "doc_id"))
    return await call_oncofiles("get_document_by_id", {"doc_id": doc_id})


async def set_agent_state(key: str, value: dict, agent_id: str = "oncoteam") -> dict:
    return await call_oncofiles(
        "set_agent_state",
        {"key": key, "value": json.dumps(value), "agent_id": agent_id},
    )


async def get_agent_state(key: str, agent_id: str = "oncoteam") -> dict:
    return await call_oncofiles("get_agent_state", {"key": key, "agent_id": agent_id})


async def add_research_entry(
    source: str,
    external_id: str,
    title: str,
    summary: str = "",
    tags: list[str] | None = None,
    raw_data: str = "",
) -> dict:
    return await call_oncofiles(
        "add_research_entry",
        {
            "source": source,
            "external_id": external_id,
            "title": title,
            "summary": summary,
            "tags": json.dumps(tags or []),
            "raw_data": raw_data,
        },
    )


async def search_research(text: str, source: str | None = None, limit: int = 20) -> dict:
    args: dict = {"text": text, "limit": limit}
    if source:
        args["source"] = source
    return await call_oncofiles("search_research", args)


async def add_treatment_event(
    event_date: str,
    event_type: str,
    title: str,
    notes: str = "",
    metadata: dict | None = None,
) -> dict:
    return await call_oncofiles(
        "add_treatment_event",
        {
            "event_date": event_date,
            "event_type": event_type,
            "title": title,
            "notes": notes,
            "metadata": json.dumps(metadata or {}),
        },
    )


async def list_treatment_events(event_type: str | None = None, limit: int = 50) -> dict:
    args: dict = {"limit": limit}
    if event_type:
        args["event_type"] = event_type
    return await call_oncofiles("list_treatment_events", args)


# ── Activity log wrappers ──────────────────────


async def add_activity_log(
    session_id: str,
    agent_id: str,
    tool_name: str,
    input_summary: str | None = None,
    output_summary: str | None = None,
    duration_ms: int | None = None,
    status: str = "ok",
    error_message: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    args: dict = {
        "session_id": session_id,
        "agent_id": agent_id,
        "tool_name": tool_name,
        "status": status,
    }
    if input_summary:
        args["input_summary"] = input_summary
    if output_summary:
        args["output_summary"] = output_summary
    if duration_ms is not None:
        args["duration_ms"] = duration_ms
    if error_message:
        args["error_message"] = error_message
    if tags:
        args["tags"] = json.dumps(tags)
    return await call_oncofiles("add_activity_log", args)


async def search_activity_log(
    session_id: str | None = None,
    agent_id: str | None = None,
    tool_name: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> dict:
    args: dict = {"limit": limit}
    if session_id:
        args["session_id"] = session_id
    if agent_id:
        args["agent_id"] = agent_id
    if tool_name:
        args["tool_name"] = tool_name
    if status:
        args["status"] = status
    if date_from:
        args["date_from"] = date_from
    if date_to:
        args["date_to"] = date_to
    return await call_oncofiles("search_activity_log", args)


# ── Additional v0.8 wrappers ─────────────────────


async def list_agent_states(agent_id: str = "oncoteam", limit: int = 20) -> dict:
    return await call_oncofiles("list_agent_states", {"agent_id": agent_id, "limit": limit})


async def get_treatment_event(event_id: int) -> dict:
    return await call_oncofiles("get_treatment_event", {"event_id": event_id})


async def list_research_entries(source: str | None = None, limit: int = 20) -> dict:
    args: dict = {"limit": limit}
    if source:
        args["source"] = source
    return await call_oncofiles("list_research_entries", args)


async def get_activity_stats(
    agent_id: str = "oncoteam",
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    args: dict = {"agent_id": agent_id}
    if date_from:
        args["date_from"] = date_from
    if date_to:
        args["date_to"] = date_to
    return await call_oncofiles("get_activity_stats", args)


async def get_research_entry(entry_id: int) -> dict:
    return await call_oncofiles("get_research_entry", {"entry_id": entry_id})


async def get_conversation(entry_id: int) -> dict:
    return await call_oncofiles("get_conversation", {"entry_id": entry_id})


# ── Conversation wrappers ──────────────────────


async def log_conversation(
    title: str,
    content: str,
    entry_type: str = "note",
    participant: str = "oncoteam",
    tags: str | None = None,
    document_ids: str | None = None,
) -> dict:
    args: dict = {
        "title": title,
        "content": content,
        "entry_type": entry_type,
        "participant": participant,
    }
    if tags:
        args["tags"] = tags
    if document_ids:
        args["document_ids"] = document_ids
    return await call_oncofiles("log_conversation", args)


async def search_conversations(
    text: str | None = None,
    entry_type: str | None = None,
    participant: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    tags: str | None = None,
    limit: int = 20,
) -> dict:
    args: dict = {"limit": limit}
    if text:
        args["text"] = text
    if entry_type:
        args["entry_type"] = entry_type
    if participant:
        args["participant"] = participant
    if date_from:
        args["date_from"] = date_from
    if date_to:
        args["date_to"] = date_to
    if tags:
        args["tags"] = tags
    return await call_oncofiles("search_conversations", args)


async def store_lab_values(
    document_id: int,
    lab_date: str,
    values_json: str,
) -> dict:
    return await call_oncofiles(
        "store_lab_values",
        {
            "document_id": document_id,
            "lab_date": lab_date,
            "values": values_json,
        },
    )


async def get_lab_trends_data(
    parameter: str | None = None,
    limit: int = 20,
) -> dict:
    args: dict = {"limit": limit}
    if parameter:
        args["parameter"] = parameter
    return await call_oncofiles("get_lab_trends", args)


async def get_journey_timeline(
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> dict:
    args: dict = {"limit": limit}
    if date_from:
        args["date_from"] = date_from
    if date_to:
        args["date_to"] = date_to
    return await call_oncofiles("get_journey_timeline", args)


async def upload_document_via_mcp(
    content_base64: str,
    filename: str,
    content_type: str,
    patient_id: str = "",
) -> dict:
    """Upload a document to oncofiles via MCP (base64-encoded content)."""
    args: dict = {
        "content_base64": content_base64,
        "filename": filename,
        "content_type": content_type,
    }
    if patient_id:
        args["patient_id"] = patient_id
    return await call_oncofiles("upload_document", args)


async def enhance_document_via_mcp(document_id: str) -> dict:
    """Trigger OCR + AI analysis on a document via oncofiles MCP."""
    return await call_oncofiles("enhance_documents", {"document_id": document_id})


async def get_related_documents(doc_id: int) -> dict:
    """Get cross-referenced documents (same visit, shared diagnoses, follow-ups)."""
    return await call_oncofiles("get_related_documents", {"doc_id": doc_id})


async def get_lab_safety_check() -> dict:
    """Pre-cycle lab safety check against mFOLFOX6 thresholds."""
    return await call_oncofiles("get_lab_safety_check", {})


async def get_precycle_checklist(cycle_number: int = 3) -> dict:
    """Full pre-cycle checklist: lab safety + toxicity + VTE + general assessment."""
    return await call_oncofiles("get_precycle_checklist", {"cycle_number": cycle_number})


# ── REST API wrappers (non-MCP) ──────────────────


async def create_patient_via_api(
    patient_id: str,
    display_name: str,
    diagnosis_summary: str = "",
    preferred_lang: str = "sk",
    caregiver_email: str = "",
) -> dict:
    """Create a new patient via oncofiles REST API (not MCP).

    Returns dict with ``patient`` and ``bearer_token`` on success.
    Raises ``httpx.HTTPStatusError`` on 409 (patient already exists) or other errors.
    """
    if not ONCOFILES_MCP_URL:
        raise RuntimeError("ONCOFILES_MCP_URL not configured")

    # Derive REST base URL: replace /mcp suffix with /api/patients
    base = ONCOFILES_MCP_URL.removesuffix("/mcp")
    url = f"{base}/api/patients"

    payload = {
        "patient_id": patient_id,
        "display_name": display_name,
        "diagnosis_summary": diagnosis_summary,
        "preferred_lang": preferred_lang,
        "caregiver_email": caregiver_email,
    }

    headers: dict[str, str] = {}
    if ONCOFILES_MCP_TOKEN:
        headers["Authorization"] = f"Bearer {ONCOFILES_MCP_TOKEN}"

    async with httpx.AsyncClient(timeout=15) as http:
        resp = await http.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()
