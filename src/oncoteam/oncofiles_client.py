from __future__ import annotations

import asyncio
import collections
import json
import logging
import re
import time

import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from .config import ONCOFILES_MCP_TOKEN, ONCOFILES_MCP_URL

_logger = logging.getLogger("oncoteam.oncofiles_client")


def _get_correlation_id() -> str:
    """Get the current request correlation ID."""
    from .request_context import get_correlation_id

    return get_correlation_id()


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
# calls fail-fast for CIRCUIT_BREAKER_COOLDOWN seconds.
# Per-token state: each patient token gets its own circuit breaker.
# Global breaker: if 3+ per-token breakers are open, treat as global failure.
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_COOLDOWN = 30  # seconds
CIRCUIT_BREAKER_GLOBAL_OPEN_COUNT = 3

_circuit_state: dict[str, dict] = {}  # token_key → {"failures": int, "open_until": float}

# Legacy global counters kept for backward-compat with health/diagnostics.
_circuit_failures: int = 0
_circuit_open_until: float = 0.0


def _circuit_key(token: str | None) -> str:
    """Derive circuit breaker key from token."""
    return (token or "")[:16] or "default"


def _get_circuit(token: str | None) -> dict:
    """Get or create per-token circuit state."""
    key = _circuit_key(token)
    if key not in _circuit_state:
        _circuit_state[key] = {"failures": 0, "open_until": 0.0}
    return _circuit_state[key]


def _is_globally_open() -> bool:
    """True if 3+ per-token breakers are open (global failure)."""
    now = time.monotonic()
    open_count = sum(1 for s in _circuit_state.values() if s["open_until"] > now)
    return open_count >= CIRCUIT_BREAKER_GLOBAL_OPEN_COUNT


# Per-call timeout (seconds) — prevents indefinite hangs when oncofiles is slow.
# Normal calls get 10s; heavy queries (search_conversations, search_documents) get 20s.
CALL_TIMEOUT = 10.0
CALL_TIMEOUT_HEAVY = 20.0
# Max time to wait for a semaphore slot before rejecting the request (#173).
# Prevents zombie queue buildup when timed-out proxy requests keep holding slots.
SEMAPHORE_WAIT_TIMEOUT = 8.0

# ── Concurrency limiter ─────────────────────────────────────────────────
# Two priority lanes: "express" (dashboard reads) and "normal" (agent writes).
# Express gets 2 slots, normal gets 1 — dashboard never waits for agents.
MAX_CONCURRENT_CALLS = 3  # legacy reference for diagnostics
_dashboard_semaphore: asyncio.Semaphore | None = None  # express: 2 slots
_agent_semaphore: asyncio.Semaphore | None = None  # normal: 1 slot

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
_rss_history: collections.deque[dict] = collections.deque(maxlen=60)  # ~1h at 60s interval


def _get_semaphore(priority: str = "express") -> asyncio.Semaphore:
    global _dashboard_semaphore, _agent_semaphore
    if priority == "normal":
        if _agent_semaphore is None:
            _agent_semaphore = asyncio.Semaphore(1)
        return _agent_semaphore
    if _dashboard_semaphore is None:
        _dashboard_semaphore = asyncio.Semaphore(2)
    return _dashboard_semaphore


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
                    _rss_history.append({"ts": time.time(), "mb": round(rss, 1)})
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
    is_open = _circuit_open_until > now or _is_globally_open()
    rss_backing_off = _rss_backoff_until > now
    sem = _get_semaphore("express")
    # Per-token breakdown
    per_token: dict[str, dict] = {}
    for key, st in _circuit_state.items():
        tok_open = st["open_until"] > now
        per_token[key] = {
            "state": "open" if tok_open else "closed",
            "failures": st["failures"],
            "cooldown_remaining_s": (round(max(0, st["open_until"] - now), 1) if tok_open else 0),
        }
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
        "rss_history": list(_rss_history),
        "rss_backoff_active": rss_backing_off,
        "rss_backoff_remaining_s": (
            round(max(0, _rss_backoff_until - now), 1) if rss_backing_off else 0
        ),
        "per_token": per_token,
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


# #432: bound how long we'll wait for an MCP session handshake. When
# oncofiles restarts, its side drops the SSE/streamable-HTTP session but
# fastmcp.Client holds the dead reference indefinitely — `ready_event.wait()`
# inside `__aenter__` hangs forever. Without this timeout, every subsequent
# call queues on the persistent-client lock, saturates the oncofiles
# semaphores, and /imaging etc. return 502 until oncoteam itself is
# restarted. See docs/incidents/2026-04-23-stale-mcp-client.md.
CONNECT_TIMEOUT = 5.0


async def _get_client(token: str | None = None) -> Client:
    """Return a persistent client for the given token, creating if necessary.

    Each unique token gets its own MCP connection (different patient data).
    Default token (None) uses ONCOFILES_MCP_TOKEN → Erika's data.

    Handshake is bounded by CONNECT_TIMEOUT. When the handshake times out
    (oncofiles peer is dead, SSE stream never became ready) we raise so
    the caller can treat this as a transient failure — no more indefinite
    hangs that saturate the semaphores. The caller's existing retry path
    in `_call_with_retry` will reconnect on the next attempt via the
    `_invalidate_client` hook.
    """
    key = token or ""
    async with _get_lock():
        if key not in _persistent_clients:
            c = Client(_make_transport(token))
            try:
                await asyncio.wait_for(c.__aenter__(), timeout=CONNECT_TIMEOUT)
            except TimeoutError:
                # Best-effort cleanup: if the transport is in a half-open
                # state, try to close it so we don't leak a background task.
                import contextlib as _cl

                with _cl.suppress(TimeoutError, Exception):
                    await asyncio.wait_for(c.__aexit__(None, None, None), timeout=1.0)
                raise TimeoutError(
                    f"oncofiles MCP handshake timed out after {CONNECT_TIMEOUT}s — "
                    "peer likely down or just restarted"
                ) from None
            _persistent_clients[key] = c
            tok_label = key[:8] if key else "default"
            _logger.debug("Opened oncofiles connection (token=%s...)", tok_label)
        return _persistent_clients[key]


async def _invalidate_client(token: str | None = None) -> None:
    """Close and discard a persistent client so the next call reconnects.

    Idempotent. Safe to call even when the client is mid-handshake or
    already closed — we wrap the __aexit__ in a 1s timeout so cleanup
    never blocks the caller.
    """
    key = token or ""
    async with _get_lock():
        client = _persistent_clients.pop(key, None)
        if client is not None:
            try:
                await asyncio.wait_for(client.__aexit__(None, None, None), timeout=1.0)
            except TimeoutError:
                from .activity_logger import record_suppressed_error

                record_suppressed_error(
                    "oncofiles_client",
                    "close_connection_timeout",
                    TimeoutError("__aexit__ > 1s, abandoning"),
                )
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


_MAX_RETRIES = 2  # 2 attempts total (initial + 1 retry)
_RETRY_BACKOFF = [0.5]  # seconds between retries

# Upstream-breaker signal: oncofiles raises RuntimeError("Circuit breaker
# open — DB unavailable, retry in {N}s") when its own Turso breaker is
# tripped. That RuntimeError propagates through MCP as the tool-call error
# string. Match the canonical phrase so transient timeouts / network blips
# do NOT trip our local breaker — only explicit upstream-open signals do.
# See oncofiles#469 + oncoteam#424 Task 2.
_UPSTREAM_BREAKER_MARKERS = (
    "Circuit breaker open",
    "Database briefly unavailable",
    "Database temporarily unavailable",
)
_UPSTREAM_COOLDOWN_RE = re.compile(r"retry in[ ~]*(\d+)\s*s", re.IGNORECASE)


def _parse_upstream_breaker_signal(exc: BaseException) -> tuple[bool, float | None]:
    """Detect an upstream-breaker-open error and its declared cooldown.

    Returns (is_breaker_open, cooldown_seconds). When the upstream supplied
    a retry hint like ``retry in 30s`` we use it verbatim for our local
    cooldown, otherwise we fall back to CIRCUIT_BREAKER_COOLDOWN. Any other
    exception returns (False, None) and MUST NOT trip the local breaker —
    double-breaker amplification (oncoteam#424) is the explicit bug here.
    """
    msg = str(exc) if exc else ""
    if not any(marker in msg for marker in _UPSTREAM_BREAKER_MARKERS):
        return False, None
    m = _UPSTREAM_COOLDOWN_RE.search(msg)
    if m:
        try:
            return True, float(m.group(1))
        except ValueError:
            pass
    return True, None


async def _call_with_retry(tool_name: str, arguments: dict, token: str | None) -> dict | list | str:
    """Execute an MCP call with retries and exponential backoff.

    Retries up to _MAX_RETRIES times with increasing delays to handle
    transient 502s during oncofiles restarts (memory leak recovery).
    Total worst-case: 10s + 0.5s + 10s = 20.5s (normal) or 20s + 0.5s + 20s = 40.5s (heavy).
    Heavy tools only retry once but get longer per-call timeout.

    Breaker semantics (oncoteam#424): a terminal failure increments local
    failure counters ONLY when the upstream exception is an explicit
    breaker-open signal from oncofiles. Plain timeouts / transient 5xx are
    retried within the attempt budget but never trip the local breaker —
    oncofiles now surfaces its own breaker via 503 + Retry-After and has
    internal recovery for the rest. Counting every generic error here was
    the root cause of the false-alarm "Database under load" banner.
    """
    global _circuit_failures, _circuit_open_until, _total_errors, _total_circuit_trips
    circuit = _get_circuit(token)
    timeout = CALL_TIMEOUT_HEAVY if tool_name in _HEAVY_TOOLS else CALL_TIMEOUT
    # Heavy tools: no retry (single 20s attempt stays within 25s proxy).
    # One exception added for #432: a handshake-timeout failure (5s fast-fail
    # from _get_client against a dead peer) gets ONE extra attempt regardless
    # of tool class, because without it /imaging returns 502 every time
    # oncofiles restarts. Worst-case budget: 5s handshake timeout + 0.5s
    # backoff + 20s heavy call = 25.5s, right at Railway's 25s proxy edge —
    # acceptable given the alternative is indefinite 502s.
    max_attempts = 1 if tool_name in _HEAVY_TOOLS else _MAX_RETRIES
    handshake_retry_granted = False
    last_exc: Exception | None = None
    attempt = 0
    while attempt < max_attempts:
        try:
            client = await _get_client(token)
            result = await asyncio.wait_for(
                client.call_tool(tool_name, arguments),
                timeout=timeout,
            )
            _circuit_failures = 0
            circuit["failures"] = 0
            return _parse_result(result)
        except Exception as exc:
            last_exc = exc
            # #432: handshake timeout from _get_client means the persistent
            # MCP client is dead (peer restarted). Grant ONE extra attempt
            # regardless of tool class, because without it /imaging returns
            # 502 every time oncofiles restarts until oncoteam itself reboots.
            is_handshake_timeout = isinstance(exc, TimeoutError) and "handshake timed out" in str(
                exc
            )
            has_budget = attempt < max_attempts - 1
            extend_for_handshake = (
                is_handshake_timeout and not has_budget and not handshake_retry_granted
            )
            if extend_for_handshake:
                handshake_retry_granted = True
                max_attempts += 1
                has_budget = True

            if has_budget:
                await _invalidate_client(token)
                backoff = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
                _logger.debug(
                    "oncofiles %s attempt %d failed, retrying in %.1fs: %s",
                    tool_name,
                    attempt + 1,
                    backoff,
                    exc,
                )
                await asyncio.sleep(backoff)
                attempt += 1
                continue
            _total_errors += 1
            upstream_open, upstream_cooldown = _parse_upstream_breaker_signal(exc)
            if upstream_open:
                cooldown = upstream_cooldown or CIRCUIT_BREAKER_COOLDOWN
                _circuit_failures += 1
                circuit["failures"] += 1
                circuit["open_until"] = time.monotonic() + cooldown
                _circuit_open_until = time.monotonic() + cooldown
                _total_circuit_trips += 1
                _logger.warning(
                    "oncofiles circuit breaker OPEN (upstream signal) — blocking calls for %.0fs",
                    cooldown,
                )
            else:
                _logger.debug(
                    "oncofiles %s failed transiently (no breaker trip): %s",
                    tool_name,
                    exc,
                )
            raise
    raise last_exc or RuntimeError("_call_with_retry: unreachable")


async def call_oncofiles(
    tool_name: str,
    arguments: dict,
    *,
    token: str | None = None,
    priority: str = "express",
) -> dict | list | str:
    """Call an oncofiles MCP tool, reusing a persistent connection.

    Args:
        token: Optional patient-specific bearer token. None = default (Erika).
               Each token scopes all data to one patient automatically.
        priority: "express" (dashboard reads, 2 slots) or "normal"
                  (agent writes, 1 slot).

    Includes RSS backoff, concurrency limiter, heavy-query gate,
    circuit breaker, per-call timeout, and retry with backoff.
    """
    global _circuit_failures, _circuit_open_until, _total_calls, _total_errors
    global _total_circuit_trips, _total_queued

    _total_calls += 1

    # Circuit breaker — fail fast when oncofiles is known to be down.
    now = time.monotonic()
    # Check per-token breaker first, then global legacy breaker
    circuit = _get_circuit(token)
    if circuit["open_until"] > now or _circuit_open_until > now or _is_globally_open():
        _total_errors += 1
        remaining = max(circuit["open_until"] - now, _circuit_open_until - now, 0)
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
    sem = _get_semaphore(priority)
    is_heavy = tool_name in _HEAVY_TOOLS
    if sem.locked():
        _total_queued += 1
        cid = _get_correlation_id()
        _logger.debug("oncofiles call queued (%s, priority=%s) [%s]", tool_name, priority, cid)

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
    *,
    token: str | None = None,
) -> dict:
    args: dict = {"text": text}
    if category:
        args["category"] = category
    if limit is not None:
        args["limit"] = limit
    return await call_oncofiles("search_documents", args, token=token)


async def list_documents(
    limit: int = 50,
    offset: int = 0,
    *,
    token: str | None = None,
) -> dict:
    """List all stored medical documents for the token's patient.

    Used by the backup pipeline (`scripts/backup_oncofiles_db.py`) which needs
    every document for a patient without filtering — search_documents requires
    a text term and would leave gaps.
    """
    return await call_oncofiles("list_documents", {"limit": limit, "offset": offset}, token=token)


def _validate_id(value: str | int, name: str = "id") -> str:
    """Validate document/file IDs at the boundary before sending to oncofiles."""
    s = str(value).strip()
    if not s or len(s) > 200:
        raise ValueError(f"Invalid {name}: must be 1-200 chars")
    return s


async def view_document(file_id: str, *, token: str | None = None) -> dict:
    return await call_oncofiles(
        "view_document", {"file_id": _validate_id(file_id, "file_id")}, token=token
    )


async def analyze_labs(
    file_id: str | None = None, limit: int = 10, *, token: str | None = None
) -> dict:
    args: dict = {"limit": limit}
    if file_id:
        args["file_id"] = file_id
    return await call_oncofiles("analyze_labs", args, token=token)


async def compare_labs(file_id_a: str, file_id_b: str, *, token: str | None = None) -> dict:
    return await call_oncofiles(
        "compare_labs", {"file_id_a": file_id_a, "file_id_b": file_id_b}, token=token
    )


async def get_document(document_id: int, *, token: str | None = None) -> dict:
    doc_id = int(_validate_id(document_id, "doc_id"))
    return await call_oncofiles("get_document_by_id", {"doc_id": doc_id}, token=token)


async def set_agent_state(
    key: str, value: dict, agent_id: str = "oncoteam", *, token: str | None = None
) -> dict:
    return await call_oncofiles(
        "set_agent_state",
        {"key": key, "value": json.dumps(value), "agent_id": agent_id},
        token=token,
    )


async def get_agent_state(
    key: str, agent_id: str = "oncoteam", *, token: str | None = None
) -> dict:
    return await call_oncofiles("get_agent_state", {"key": key, "agent_id": agent_id}, token=token)


async def get_patient_context(*, token: str | None = None) -> dict:
    return await call_oncofiles("get_patient_context", {}, token=token)


async def update_patient_context(updates_json: str, *, token: str | None = None) -> dict:
    return await call_oncofiles(
        "update_patient_context", {"updates_json": updates_json}, token=token
    )


async def add_research_entry(
    source: str,
    external_id: str,
    title: str,
    summary: str = "",
    tags: list[str] | None = None,
    raw_data: str = "",
    *,
    token: str | None = None,
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
        token=token,
    )


async def search_research(
    text: str, source: str | None = None, limit: int = 20, *, token: str | None = None
) -> dict:
    args: dict = {"text": text, "limit": limit}
    if source:
        args["source"] = source
    return await call_oncofiles("search_research", args, token=token)


async def add_treatment_event(
    event_date: str,
    event_type: str,
    title: str,
    notes: str = "",
    metadata: dict | None = None,
    *,
    token: str | None = None,
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
        token=token,
    )


async def list_treatment_events(
    event_type: str | None = None, limit: int = 50, *, token: str | None = None
) -> dict:
    args: dict = {"limit": limit}
    if event_type:
        args["event_type"] = event_type
    return await call_oncofiles("list_treatment_events", args, token=token)


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
    *,
    token: str | None = None,
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
    return await call_oncofiles("add_activity_log", args, token=token)


async def search_activity_log(
    session_id: str | None = None,
    agent_id: str | None = None,
    tool_name: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    *,
    token: str | None = None,
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
    return await call_oncofiles("search_activity_log", args, token=token)


# ── Additional v0.8 wrappers ─────────────────────


async def list_agent_states(
    agent_id: str = "oncoteam", limit: int = 20, *, token: str | None = None
) -> dict:
    # Note: oncofiles list_agent_states does not accept 'limit' param.
    # We fetch all and truncate client-side.
    result = await call_oncofiles("list_agent_states", {"agent_id": agent_id}, token=token)
    if limit:
        if isinstance(result, dict):
            states = result.get("states", [])
            if len(states) > limit:
                result["states"] = states[:limit]
        elif isinstance(result, list) and len(result) > limit:
            result = result[:limit]
    return result


async def get_treatment_event(event_id: int, *, token: str | None = None) -> dict:
    return await call_oncofiles("get_treatment_event", {"event_id": event_id}, token=token)


async def list_research_entries(
    source: str | None = None, limit: int = 20, *, token: str | None = None
) -> dict:
    args: dict = {"limit": limit}
    if source:
        args["source"] = source
    return await call_oncofiles("list_research_entries", args, token=token)


async def get_activity_stats(
    agent_id: str = "oncoteam",
    date_from: str | None = None,
    date_to: str | None = None,
    *,
    token: str | None = None,
) -> dict:
    args: dict = {"agent_id": agent_id}
    if date_from:
        args["date_from"] = date_from
    if date_to:
        args["date_to"] = date_to
    return await call_oncofiles("get_activity_stats", args, token=token)


async def get_research_entry(entry_id: int, *, token: str | None = None) -> dict:
    return await call_oncofiles("get_research_entry", {"entry_id": entry_id}, token=token)


async def get_conversation(entry_id: int, *, token: str | None = None) -> dict:
    return await call_oncofiles("get_conversation", {"entry_id": entry_id}, token=token)


# ── Conversation wrappers ──────────────────────


async def log_conversation(
    title: str,
    content: str,
    entry_type: str = "note",
    participant: str = "oncoteam",
    tags: str | None = None,
    document_ids: str | None = None,
    *,
    token: str | None = None,
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
    return await call_oncofiles("log_conversation", args, token=token)


async def search_conversations(
    text: str | None = None,
    entry_type: str | None = None,
    participant: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    tags: str | None = None,
    limit: int = 20,
    *,
    token: str | None = None,
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
    return await call_oncofiles("search_conversations", args, token=token)


async def store_lab_values(
    document_id: int,
    lab_date: str,
    values_json: str,
    *,
    token: str | None = None,
) -> dict:
    return await call_oncofiles(
        "store_lab_values",
        {
            "document_id": document_id,
            "lab_date": lab_date,
            "values": values_json,
        },
        token=token,
    )


async def get_lab_trends_data(
    parameter: str | None = None,
    limit: int = 20,
    *,
    token: str | None = None,
) -> dict:
    args: dict = {"limit": limit}
    if parameter:
        args["parameter"] = parameter
    return await call_oncofiles("get_lab_trends", args, token=token)


async def get_journey_timeline(
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    *,
    token: str | None = None,
) -> dict:
    args: dict = {"limit": limit}
    if date_from:
        args["date_from"] = date_from
    if date_to:
        args["date_to"] = date_to
    return await call_oncofiles("get_journey_timeline", args, token=token)


async def upload_document_via_mcp(
    content_base64: str,
    filename: str,
    content_type: str,
    patient_id: str = "",
    *,
    token: str | None = None,
) -> dict:
    """Upload a document to oncofiles via MCP (base64-encoded content)."""
    args: dict = {
        "content_base64": content_base64,
        "filename": filename,
        "content_type": content_type,
    }
    if patient_id:
        args["patient_id"] = patient_id
    return await call_oncofiles("upload_document", args, token=token)


async def enhance_document_via_mcp(document_id: str, *, token: str | None = None) -> dict:
    """Trigger OCR + AI analysis on a document via oncofiles MCP."""
    return await call_oncofiles("enhance_documents", {"document_id": document_id}, token=token)


async def get_related_documents(doc_id: int, *, token: str | None = None) -> dict:
    """Get cross-referenced documents (same visit, shared diagnoses, follow-ups)."""
    return await call_oncofiles("get_related_documents", {"doc_id": doc_id}, token=token)


async def get_document_group(group_id: str, *, token: str | None = None) -> dict:
    """Get all documents in a logical group (split siblings or consolidated parts)."""
    return await call_oncofiles("get_document_group", {"group_id": group_id}, token=token)


async def get_lab_safety_check(*, token: str | None = None) -> dict:
    """Pre-cycle lab safety check against mFOLFOX6 thresholds."""
    return await call_oncofiles("get_lab_safety_check", {}, token=token)


async def get_precycle_checklist(cycle_number: int = 3, *, token: str | None = None) -> dict:
    """Full pre-cycle checklist: lab safety + toxicity + VTE + general assessment."""
    return await call_oncofiles(
        "get_precycle_checklist", {"cycle_number": cycle_number}, token=token
    )


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


async def list_patients(*, token: str | None = None) -> dict:
    """List all active patients via oncofiles MCP."""
    return await call_oncofiles("list_patients", {}, token=token)


async def select_patient(patient_slug: str, *, token: str | None = None) -> dict:
    """Switch active patient for the current oncofiles connection."""
    return await call_oncofiles("select_patient", {"patient_slug": patient_slug}, token=token)


async def get_doc_detail(doc_id: int, *, token: str | None = None) -> dict:
    """Fetch rich document detail via oncofiles REST API.

    Returns metadata, preview_url, and per-page OCR text in a single call.
    """
    if not ONCOFILES_MCP_URL:
        raise RuntimeError("ONCOFILES_MCP_URL not configured")

    base = ONCOFILES_MCP_URL.removesuffix("/mcp")
    url = f"{base}/api/doc-detail/{doc_id}"

    bearer = token or ONCOFILES_MCP_TOKEN
    headers: dict[str, str] = {}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"

    async with httpx.AsyncClient(timeout=15) as http:
        resp = await http.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()
