"""Tests for /api/protocol and /api/briefings dashboard endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import _briefing_summary, api_briefings, api_protocol


def _make_request(query_string: str = "") -> object:
    from starlette.datastructures import Headers, QueryParams

    class FakeRequest:
        def __init__(self, query: str):
            self.query_params = QueryParams(query)
            self.headers = Headers({"origin": "https://dashboard.oncoteam.cloud"})

    return FakeRequest(query_string)


# ── /api/protocol ────────────────────────────────


@pytest.mark.anyio
async def test_api_protocol_returns_all_sections():
    request = _make_request()
    response = await api_protocol(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert "lab_thresholds" in data
    assert "dose_modifications" in data
    assert "milestones" in data
    assert "monitoring_schedule" in data
    assert "safety_flags" in data
    assert "second_line_options" in data
    assert "watched_trials" in data
    assert "current_cycle" in data


@pytest.mark.anyio
async def test_api_protocol_has_cors():
    request = _make_request()
    response = await api_protocol(request)
    assert response.headers["access-control-allow-origin"] == "https://dashboard.oncoteam.cloud"


@pytest.mark.anyio
async def test_api_protocol_lab_thresholds_structure():
    request = _make_request()
    response = await api_protocol(request)
    data = json.loads(response.body)

    assert "ANC" in data["lab_thresholds"]
    assert data["lab_thresholds"]["ANC"]["min"] == 1500
    assert "PLT" in data["lab_thresholds"]


@pytest.mark.anyio
async def test_api_protocol_milestones_structure():
    request = _make_request()
    response = await api_protocol(request)
    data = json.loads(response.body)

    assert isinstance(data["milestones"], list)
    assert len(data["milestones"]) > 0
    assert "cycle" in data["milestones"][0]
    assert "action" in data["milestones"][0]
    assert "description" in data["milestones"][0]


@pytest.mark.anyio
async def test_api_protocol_includes_cycle_delay_rules():
    request = _make_request()
    response = await api_protocol(request)
    data = json.loads(response.body)

    assert "cycle_delay_rules" in data
    assert isinstance(data["cycle_delay_rules"], list)
    assert len(data["cycle_delay_rules"]) == 9
    assert "condition" in data["cycle_delay_rules"][0]
    assert "action" in data["cycle_delay_rules"][0]


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_lab_trends_data",
    new_callable=AsyncMock,
    return_value={"values": []},
)
async def test_api_protocol_computes_milestone_expected_dates(_trends, mock_events):
    """#375 — /api/protocol returns cycle_1_date, cycle_interval_days, and
    every milestone carries an expected_date computed from the regimen cadence.
    """

    # list_treatment_events is called twice (limit=1 for labs + limit=20 for
    # all events). The fallback side_effect handles both shapes.
    async def _events(**kwargs):
        if kwargs.get("event_type") == "lab_result":
            return {"events": []}
        return {
            "events": [
                {
                    "id": 1,
                    "event_type": "chemotherapy",
                    "event_date": "2026-02-13",
                    "title": "Cycle 1 mFOLFOX6",
                },
                {
                    "id": 2,
                    "event_type": "chemotherapy",
                    "event_date": "2026-02-27",
                    "title": "Cycle 2 mFOLFOX6",
                },
            ]
        }

    mock_events.side_effect = _events

    import oncoteam.dashboard_api as mod

    mod._protocol_cache.clear()

    request = _make_request()
    response = await api_protocol(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["cycle_1_date"] == "2026-02-13"
    # q1b on mFOLFOX6 → q2w → 14 day cycle
    assert data["cycle_interval_days"] == 14

    # Every milestone with a numeric cycle gets an expected_date.
    milestones = data["milestones"]
    assert len(milestones) > 0
    with_dates = [m for m in milestones if m.get("expected_date")]
    assert len(with_dates) == sum(1 for m in milestones if isinstance(m.get("cycle"), int))

    # Sanity check: a C3 milestone should land at 2026-02-13 + 2 * 14d = 2026-03-13
    c3 = next((m for m in milestones if m.get("cycle") == 3), None)
    if c3:
        assert c3["expected_date"] == "2026-03-13"


@pytest.mark.anyio
async def test_api_protocol_safety_flags_structure():
    request = _make_request()
    response = await api_protocol(request)
    data = json.loads(response.body)

    assert "anti_egfr_kras_mutant" in data["safety_flags"]
    assert "rule" in data["safety_flags"]["anti_egfr_kras_mutant"]


# ── /api/briefings ───────────────────────────────


MOCK_BRIEFINGS = {
    "entries": [
        {
            "id": 1,
            "title": "Pre-cycle check C2",
            "content": "## Pre-Cycle Check\n\nAll labs within range.",
            "created_at": "2026-03-06T07:00:00Z",
            "tags": ["autonomous", "pre_cycle_check"],
        },
        {
            "id": 2,
            "title": "Weekly briefing",
            "content": "## Weekly Summary\n\n3 new PubMed articles.",
            "created_at": "2026-03-03T06:00:00Z",
            "tags": ["autonomous", "weekly_briefing"],
        },
    ]
}


def _briefings_side_effect(**kwargs):
    """Mock side_effect for search_conversations: briefings + alerts calls."""
    if kwargs.get("entry_type") == "cost_alert":
        return {"entries": []}
    return MOCK_BRIEFINGS


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_conversations", new_callable=AsyncMock)
async def test_api_briefings_returns_entries(mock_search):
    mock_search.side_effect = _briefings_side_effect
    request = _make_request()
    response = await api_briefings(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 2
    assert data["briefings"][0]["title"] == "Pre-cycle check C2"
    assert data["briefings"][0]["content"].startswith("## Pre-Cycle")
    assert "summary" in data["briefings"][0]
    assert "action_count" in data["briefings"][0]


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_conversations", new_callable=AsyncMock)
async def test_api_briefings_with_limit(mock_search):
    mock_search.return_value = {"entries": []}
    request = _make_request("limit=5")
    await api_briefings(request)
    assert mock_search.call_count == 2  # briefings + alerts


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_conversations", new_callable=AsyncMock)
async def test_api_briefings_handles_error(mock_search):
    mock_search.side_effect = Exception("connection refused")
    request = _make_request()
    response = await api_briefings(request)
    data = json.loads(response.body)

    # asyncio.gather with return_exceptions=True means errors become empty lists
    assert response.status_code == 200
    assert data["briefings"] == []
    assert data["total"] == 0


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_conversations", new_callable=AsyncMock)
async def test_api_briefings_filters_test_data(mock_search):
    def _filter_side_effect(**kwargs):
        if kwargs.get("entry_type") == "cost_alert":
            return {"entries": []}
        return {
            "entries": [
                {
                    "id": 1,
                    "title": "Real briefing",
                    "content": "content",
                    "created_at": "2026-03-06T07:00:00Z",
                    "tags": ["autonomous"],
                },
                {
                    "id": 2,
                    "title": "e2e-test-briefing",
                    "content": "test",
                    "created_at": "2026-03-06T06:00:00Z",
                    "tags": ["e2e-test"],
                },
            ]
        }

    mock_search.side_effect = _filter_side_effect
    request = _make_request()
    response = await api_briefings(request)
    data = json.loads(response.body)

    assert data["total"] == 1
    assert data["briefings"][0]["title"] == "Real briefing"


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_conversations", new_callable=AsyncMock)
async def test_api_briefings_has_cors(mock_search):
    mock_search.return_value = {"entries": []}
    request = _make_request()
    response = await api_briefings(request)
    assert response.headers["access-control-allow-origin"] == "https://dashboard.oncoteam.cloud"


# ── _briefing_summary unit tests ─────────────────────────────────


class TestBriefingSummary:
    def test_extracts_summary_lines(self):
        content = "## Title\nFirst finding.\nSecond finding.\nThird line."
        result = _briefing_summary(content)
        assert "First finding." in result["summary"]
        assert "Second finding." in result["summary"]

    def test_counts_action_items(self):
        content = (
            "## Summary\nSome findings.\n"
            "## Questions for oncologist\n"
            "- Ask about dose\n"
            "- Check neuropathy\n"
            "- Review labs\n"
        )
        result = _briefing_summary(content)
        assert result["action_count"] == 3

    def test_empty_content(self):
        result = _briefing_summary("")
        assert result["summary"] == ""
        assert result["action_count"] == 0

    def test_no_actions_section(self):
        content = "## Report\nAll stable. No concerns."
        result = _briefing_summary(content)
        assert result["action_count"] == 0
        assert "All stable" in result["summary"]

    def test_summary_truncated(self):
        content = "A" * 300
        result = _briefing_summary(content)
        assert len(result["summary"]) <= 200

    def test_returns_summary_and_action_count_in_api(self):
        """Briefing entries from api_briefings include summary fields."""
        # This is a structural test — _briefing_summary is used in api_briefings
        content = "## Check\nLabs stable.\n## Actions\n- Follow up\n"
        result = _briefing_summary(content)
        assert "summary" in result
        assert "action_count" in result
