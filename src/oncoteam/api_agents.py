"""Agent & autonomous API handlers — extracted from dashboard_api.py."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import oncofiles_client
from .activity_logger import get_suppressed_errors, record_suppressed_error
from .config import (
    ANTHROPIC_BUDGET_ALERT_THRESHOLD,
    ANTHROPIC_CREDIT_BALANCE,
    AUTONOMOUS_COST_LIMIT,
    AUTONOMOUS_ENABLED,
    ONCOFILES_MCP_URL,
)
from .locale import get_lang, resolve
from .request_context import get_token_for_patient as _get_token_for_patient

_logger = logging.getLogger("oncoteam.api_agents")

# ---------------------------------------------------------------------------
# Lazy imports from dashboard_api to avoid circular dependency
# ---------------------------------------------------------------------------


def _cors_json(data: dict, status_code: int = 200, request: Request | None = None) -> JSONResponse:
    from .dashboard_api import _cors_json as _cj

    return _cj(data, status_code=status_code, request=request)


def _get_patient_id(request: Request) -> str:
    from .dashboard_api import _get_patient_id as _gpi

    return _gpi(request)


def _extract_list(result: dict | list | str, key: str) -> list[dict]:
    from .dashboard_api import _extract_list as _el

    return _el(result, key)


def _filter_test(entries: list[dict], request: Request) -> list[dict]:
    from .dashboard_api import _filter_test as _ft

    return _ft(entries, request)


def _parse_limit(request: Request, default: int = 50, max_val: int = 500) -> int:
    from .dashboard_api import _parse_limit as _pl

    return _pl(request, default=default, max_val=max_val)


def _check_expensive_rate_limit() -> bool:
    from .dashboard_api import _check_expensive_rate_limit as _cerl

    return _cerl()


def _check_fup_agent_run(patient_id: str = "") -> bool:
    from .dashboard_api import _check_fup_agent_run as _cfar

    return _cfar(patient_id)


def _get_fup_status() -> dict:
    from .dashboard_api import _get_fup_status as _gfs

    return _gfs()


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

# Last trigger result (for debugging via /api/autonomous?last_trigger=1)
_last_trigger_result: dict | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# API Handlers
# ---------------------------------------------------------------------------


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
