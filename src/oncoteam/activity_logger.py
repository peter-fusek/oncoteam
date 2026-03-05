"""Activity logging: automatic tool-call audit trail and diary helpers."""

from __future__ import annotations

import contextlib
import inspect
import json
import time
from datetime import date
from functools import wraps
from uuid import uuid4

from . import oncofiles_client

_session_id: str | None = None


def get_session_id() -> str:
    """Generate once per process: '20260305-a1b2c3d4'."""
    global _session_id
    if _session_id is None:
        _session_id = f"{date.today():%Y%m%d}-{uuid4().hex[:8]}"
    return _session_id


def log_activity(fn):
    """Decorator for @mcp.tool() functions. Fire-and-forget logging."""

    @wraps(fn)
    async def wrapper(*args, **kwargs):
        start = time.monotonic()
        try:
            result = await fn(*args, **kwargs)
            elapsed = int((time.monotonic() - start) * 1000)
            bound = _bind_args(fn, args, kwargs)
            with contextlib.suppress(Exception):
                await _write_tool_log(fn.__name__, bound, result, elapsed, "ok")
            return result
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            bound = _bind_args(fn, args, kwargs)
            with contextlib.suppress(Exception):
                await _write_tool_log(fn.__name__, bound, None, elapsed, "error", str(exc))
            raise

    return wrapper


def _bind_args(fn, args: tuple, kwargs: dict) -> dict:
    """Bind positional and keyword args to parameter names."""
    try:
        sig = inspect.signature(fn)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)
    except Exception:
        return kwargs


async def _write_tool_log(
    tool_name: str,
    inputs: dict,
    output: str | None,
    duration_ms: int,
    status: str,
    error: str | None = None,
) -> None:
    await oncofiles_client.add_activity_log(
        session_id=get_session_id(),
        agent_id="oncoteam",
        tool_name=tool_name,
        input_summary=_summarize_input(tool_name, inputs),
        output_summary=_summarize_output(tool_name, output),
        duration_ms=duration_ms,
        status=status,
        error_message=error,
    )


# ── Input summarizers ──────────────────────────


def _summarize_input(tool_name: str, inputs: dict) -> str:
    """One-liner summary of tool inputs."""
    if not inputs:
        return ""
    builders: dict[str, object] = {
        "search_pubmed": lambda d: f"query={d.get('query')!r}, max_results={d.get('max_results')}",
        "search_clinical_trials": lambda d: _kv_summary(d, ["condition", "intervention"]),
        "daily_briefing": lambda d: "",
        "get_lab_trends": lambda d: f"limit={d.get('limit')}",
        "search_documents": lambda d: _kv_summary(d, ["text", "category"]),
        "get_patient_context": lambda d: "",
        "view_document": lambda d: f"file_id={d.get('file_id')!r}",
        "analyze_labs": lambda d: f"file_id={d.get('file_id')!r}, limit={d.get('limit')}",
        "compare_labs": lambda d: (
            f"file_id_a={d.get('file_id_a')!r}, file_id_b={d.get('file_id_b')!r}"
        ),
        "log_research_decision": lambda d: f"decision={d.get('decision', '')[:60]!r}",
        "log_session_note": lambda d: f"note={d.get('note', '')[:60]!r}",
        "summarize_session": lambda d: f"summary={d.get('summary', '')[:60]!r}",
    }
    builder = builders.get(tool_name)
    if builder:
        return builder(inputs)
    # Generic fallback
    return ", ".join(f"{k}={v!r}" for k, v in inputs.items() if v is not None)[:200]


def _kv_summary(d: dict, keys: list[str]) -> str:
    parts = [f"{k}={d[k]!r}" for k in keys if d.get(k) is not None]
    return ", ".join(parts)


# ── Output summarizers ─────────────────────────


def _summarize_output(tool_name: str, output: str | None) -> str:
    """One-liner summary of tool output."""
    if output is None:
        return ""
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return str(output)[:100]

    builders: dict[str, object] = {
        "search_pubmed": lambda d: f"{d.get('count', 0)} articles found",
        "search_clinical_trials": lambda d: f"{d.get('count', 0)} trials found",
        "daily_briefing": lambda d: (
            f"{d.get('pubmed_articles', 0)} articles, {d.get('clinical_trials', 0)} trials"
        ),
        "get_lab_trends": lambda d: (
            f"{len(d.get('lab_documents', {}).get('documents', []))} lab documents"
        ),
        "search_documents": lambda d: (
            f"{len(d.get('results', {}).get('documents', []))} documents found"
        ),
        "get_patient_context": lambda d: "patient profile returned",
        "view_document": lambda d: "document content returned",
        "analyze_labs": lambda d: "lab analysis returned",
        "compare_labs": lambda d: "lab comparison returned",
    }
    builder = builders.get(tool_name)
    if builder:
        return builder(data)
    return str(output)[:100]


# ── Diary helper ───────────────────────────────


async def log_to_diary(
    title: str,
    content: str,
    entry_type: str = "note",
    tags: list[str] | None = None,
) -> None:
    """Write to conversation_entries via existing log_conversation tool."""
    await oncofiles_client.log_conversation(
        title=title,
        content=content,
        entry_type=entry_type,
        participant="oncoteam",
        tags=",".join(tags) if tags else None,
    )
