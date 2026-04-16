"""Research API handlers — extracted from dashboard_api.py."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import oncofiles_client
from .activity_logger import record_suppressed_error
from .config import ANTHROPIC_API_KEY, AUTONOMOUS_MODEL_LIGHT
from .eligibility import assess_research_relevance
from .request_context import get_token_for_patient as _get_token_for_patient

_logger = logging.getLogger("oncoteam.api_research")

# ---------------------------------------------------------------------------
# Lazy imports from dashboard_api to avoid circular dependency
# ---------------------------------------------------------------------------


def _cors_json(data: dict, status_code: int = 200, request: Request | None = None) -> JSONResponse:
    from .dashboard_api import _cors_json as _cj

    return _cj(data, status_code=status_code, request=request)


def _get_patient_id(request: Request) -> str:
    from .dashboard_api import _get_patient_id as _gpi

    return _gpi(request)


def _get_patient_for_request(request: Request):
    from .dashboard_api import _get_patient_for_request as _gpfr

    return _gpfr(request)


def _extract_list(result: dict | list | str, key: str) -> list[dict]:
    from .dashboard_api import _extract_list as _el

    return _el(result, key)


def _filter_test(entries: list[dict], request: Request) -> list[dict]:
    from .dashboard_api import _filter_test as _ft

    return _ft(entries, request)


def _parse_limit(request: Request, default: int = 50, max_val: int = 500) -> int:
    from .dashboard_api import _parse_limit as _pl

    return _pl(request, default=default, max_val=max_val)


def _circuit_breaker_503(fallback_data: dict) -> JSONResponse | None:
    from .dashboard_api import _circuit_breaker_503 as _cb

    return _cb(fallback_data)


def _build_external_url(source: str, external_id: str, raw_data: str = "") -> str | None:
    from .dashboard_api import _build_external_url as _beu

    return _beu(source, external_id, raw_data)


def _build_source_ref(entry: dict, entry_type: str) -> dict:
    from .dashboard_api import _build_source_ref as _bsr

    return _bsr(entry, entry_type)


def _check_expensive_rate_limit() -> bool:
    from .dashboard_api import _check_expensive_rate_limit as _cerl

    return _cerl()


def _parse_json_body(request: Request):
    from .dashboard_api import _parse_json_body as _pjb

    return _pjb(request)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RELEVANCE_SORT_ORDER = {"high": 0, "medium": 1, "low": 2, "not_applicable": 3}

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
{{"stage": "<one of the 5 stages>", "exclusion_reason": "<null or string>", \
"next_step": "<1 sentence recommendation>", "deadline_note": "<null or string>"}}
"""


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


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


async def api_assess_funnel(request: Request) -> JSONResponse:
    """POST /api/research/assess-funnel — AI-classify trials into funnel stages."""
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


async def api_funnel_stages_get(request: Request) -> JSONResponse:
    """GET /api/research/funnel-stages — load persisted funnel stage assignments."""
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    try:
        result = await oncofiles_client.get_agent_state(f"funnel_stages:{patient_id}", token=token)
        value = result.get("result") or result.get("value") or {}
        if isinstance(value, str):
            value = json.loads(value)
        return _cors_json({"stages": value}, request=request)
    except Exception as exc:
        record_suppressed_error("api_funnel_stages_get", "fetch", exc)
        return _cors_json({"stages": {}}, request=request)


async def api_funnel_stages_save(request: Request) -> JSONResponse:
    """POST /api/research/funnel-stages — persist funnel stage assignments."""
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    body = await _parse_json_body(request)
    stages = body.get("stages", {})
    if not isinstance(stages, dict):
        return _cors_json({"error": "stages must be a dict"}, status_code=400, request=request)
    try:
        await oncofiles_client.set_agent_state(f"funnel_stages:{patient_id}", stages, token=token)
        return _cors_json({"ok": True, "count": len(stages)}, request=request)
    except Exception as exc:
        record_suppressed_error("api_funnel_stages_save", "save", exc)
        return _cors_json({"error": str(exc)}, status_code=500, request=request)
