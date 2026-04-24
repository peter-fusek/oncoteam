"""Tests for POST /api/research/assess-funnel endpoint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oncoteam.api_research import api_assess_funnel


def _make_post_request(body: dict, query_string: str = "patient_id=q1b") -> object:
    from starlette.datastructures import Headers, QueryParams

    class FakeRequest:
        def __init__(self, b: dict, query: str):
            self.query_params = QueryParams(query)
            self.headers = Headers(
                {
                    "origin": "https://dashboard.oncoteam.cloud",
                    "content-type": "application/json",
                    "content-length": str(len(json.dumps(b))),
                }
            )
            self._body = json.dumps(b).encode()

        async def body(self):
            return self._body

    return FakeRequest(body, query_string)


def _mock_anthropic_response(payload: dict, input_tokens: int = 100, output_tokens: int = 50):
    """Build a mock Anthropic messages.create return value."""
    resp = MagicMock()
    resp.content = [MagicMock(text=json.dumps(payload))]
    resp.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    return resp


@pytest.fixture
def _patch_rate_limit():
    """Default: rate limit allows requests."""
    with patch("oncoteam.api_research._check_expensive_rate_limit", return_value=True) as m:
        yield m


@pytest.fixture
def _anthropic_key(monkeypatch):
    monkeypatch.setattr("oncoteam.api_research.ANTHROPIC_API_KEY", "sk-ant-test")


@pytest.mark.anyio
async def test_assess_funnel_rate_limited():
    """Returns 429 when rate limit exhausted."""
    with patch("oncoteam.api_research._check_expensive_rate_limit", return_value=False):
        resp = await api_assess_funnel(_make_post_request({"trials": []}))
    assert resp.status_code == 429
    assert "Too many" in json.loads(resp.body)["error"]


@pytest.mark.anyio
@pytest.mark.usefixtures("_patch_rate_limit")
async def test_assess_funnel_invalid_json():
    """Returns 400 on invalid JSON body."""

    class BadBodyRequest:
        from starlette.datastructures import Headers, QueryParams

        query_params = QueryParams("")
        headers = Headers({"origin": "https://dashboard.oncoteam.cloud"})

        async def body(self):
            return b"not-json-{"

    resp = await api_assess_funnel(BadBodyRequest())
    assert resp.status_code == 400


@pytest.mark.anyio
@pytest.mark.usefixtures("_patch_rate_limit")
async def test_assess_funnel_rejects_non_list_trials():
    """trials field must be a list — returns 400 otherwise."""
    resp = await api_assess_funnel(_make_post_request({"trials": "not-a-list"}))
    assert resp.status_code == 400
    assert "trials must be a list" in json.loads(resp.body)["error"]


@pytest.mark.anyio
@pytest.mark.usefixtures("_patch_rate_limit")
async def test_assess_funnel_rejects_over_50_trials():
    """Caps at 50 trials per request."""
    many = [{"external_id": f"NCT{i:05d}", "title": "t"} for i in range(51)]
    resp = await api_assess_funnel(_make_post_request({"trials": many}))
    assert resp.status_code == 400


@pytest.mark.anyio
@pytest.mark.usefixtures("_patch_rate_limit")
async def test_assess_funnel_empty_list_returns_zero_cost():
    """Empty list: no Anthropic call, empty assessments, 0 cost."""
    resp = await api_assess_funnel(_make_post_request({"trials": []}))
    assert resp.status_code == 200
    data = json.loads(resp.body)
    assert data["assessments"] == []
    assert data["cost_usd"] == 0


@pytest.mark.anyio
@pytest.mark.usefixtures("_patch_rate_limit")
async def test_assess_funnel_no_api_key_returns_500(monkeypatch):
    """Returns 500 when ANTHROPIC_API_KEY is unset."""
    monkeypatch.setattr("oncoteam.api_research.ANTHROPIC_API_KEY", "")
    resp = await api_assess_funnel(
        _make_post_request({"trials": [{"external_id": "NCT1", "title": "t"}]})
    )
    assert resp.status_code == 500
    assert "AI not configured" in json.loads(resp.body)["error"]


@pytest.mark.anyio
@pytest.mark.usefixtures("_patch_rate_limit", "_anthropic_key")
async def test_assess_funnel_happy_path():
    """Anthropic returns a valid stage → passed through in response."""
    trial = {
        "external_id": "NCT12345",
        "id": 42,
        "title": "pan-KRAS inhibitor trial",
        "summary": "Phase II study",
        "relevance": "relevant",
        "relevance_reason": "KRAS G12S biomarker match",
    }

    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(
        return_value=_mock_anthropic_response(
            {
                "stage": "Watching",
                "exclusion_reason": None,
                "next_step": "Confirm enrollment criteria",
                "deadline_note": "Enrolls through 2026",
            }
        )
    )

    with patch("anthropic.AsyncAnthropic", return_value=fake_client):
        resp = await api_assess_funnel(_make_post_request({"trials": [trial]}))

    assert resp.status_code == 200
    data = json.loads(resp.body)
    assert len(data["assessments"]) == 1
    a = data["assessments"][0]
    assert a["nct_id"] == "NCT12345"
    assert a["oncofiles_id"] == 42
    assert a["stage"] == "Watching"
    assert a["next_step"] == "Confirm enrollment criteria"
    assert data["cost_usd"] > 0


@pytest.mark.anyio
@pytest.mark.usefixtures("_patch_rate_limit", "_anthropic_key")
async def test_assess_funnel_unknown_stage_falls_back_to_watching():
    """An out-of-vocabulary stage from Anthropic falls back to 'Watching'."""
    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(
        return_value=_mock_anthropic_response({"stage": "Hallucinated Stage"})
    )

    with patch("anthropic.AsyncAnthropic", return_value=fake_client):
        resp = await api_assess_funnel(
            _make_post_request({"trials": [{"external_id": "NCT1", "title": "t"}]})
        )

    assert json.loads(resp.body)["assessments"][0]["stage"] == "Watching"


@pytest.mark.anyio
@pytest.mark.usefixtures("_patch_rate_limit", "_anthropic_key")
async def test_assess_funnel_handles_markdown_wrapped_json():
    """Haiku sometimes wraps JSON in ```json fences — parser must strip them."""
    wrapped = MagicMock()
    wrapped.content = [
        MagicMock(text='```json\n{"stage": "Excluded", "exclusion_reason": "biomarker"}\n```')
    ]
    wrapped.usage = MagicMock(input_tokens=50, output_tokens=20)

    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(return_value=wrapped)

    with patch("anthropic.AsyncAnthropic", return_value=fake_client):
        resp = await api_assess_funnel(
            _make_post_request({"trials": [{"external_id": "NCT2", "title": "t"}]})
        )

    a = json.loads(resp.body)["assessments"][0]
    assert a["stage"] == "Excluded"
    assert a["exclusion_reason"] == "biomarker"


@pytest.mark.anyio
@pytest.mark.usefixtures("_patch_rate_limit", "_anthropic_key")
async def test_assess_funnel_per_trial_exception_falls_back_gracefully():
    """One trial failing doesn't kill the batch — returns Watching + 'Assessment failed' note."""
    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(side_effect=RuntimeError("api down"))

    with patch("anthropic.AsyncAnthropic", return_value=fake_client):
        resp = await api_assess_funnel(
            _make_post_request(
                {
                    "trials": [
                        {"external_id": "NCT-A", "id": 1, "title": "t"},
                        {"external_id": "NCT-B", "id": 2, "title": "t"},
                    ]
                }
            )
        )

    assert resp.status_code == 200
    data = json.loads(resp.body)
    assert len(data["assessments"]) == 2
    for a in data["assessments"]:
        assert a["stage"] == "Watching"
        assert "Assessment failed" in a["next_step"]
