"""Tests for /api/toxicity and /api/labs dashboard endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import _normalize_lab_values, api_labs, api_toxicity


class FakeRequest:
    """Minimal Starlette Request stub with method and body support."""

    def __init__(self, method: str = "GET", query: str = "", body: bytes = b""):
        from starlette.datastructures import QueryParams

        self.method = method
        self.query_params = QueryParams(query)
        self._body = body

    async def body(self) -> bytes:
        return self._body


# ── /api/toxicity GET ────────────────────────────


MOCK_TOXICITY_EVENTS = [
    {
        "id": 1,
        "event_date": "2026-03-01",
        "event_type": "toxicity_log",
        "title": "Toxicity log 2026-03-01",
        "notes": "Mild neuropathy in fingers",
        "metadata": {"neuropathy": 1, "fatigue": 2, "weight_kg": 65},
    },
]


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_toxicity_get_returns_entries(mock_list):
    mock_list.return_value = MOCK_TOXICITY_EVENTS
    request = FakeRequest("GET")
    response = await api_toxicity(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 1
    assert data["entries"][0]["date"] == "2026-03-01"
    assert data["entries"][0]["metadata"]["neuropathy"] == 1
    mock_list.assert_called_once_with(event_type="toxicity_log", limit=50)


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_toxicity_get_handles_error(mock_list):
    mock_list.side_effect = Exception("fail")
    request = FakeRequest("GET")
    response = await api_toxicity(request)
    assert response.status_code == 502


# ── /api/toxicity POST ───────────────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.add_treatment_event",
    new_callable=AsyncMock,
)
async def test_api_toxicity_post_creates_entry(mock_add):
    mock_add.return_value = {"id": 99}
    body = json.dumps(
        {
            "date": "2026-03-07",
            "neuropathy": 1,
            "fatigue": 2,
            "notes": "Tingling in toes",
        }
    ).encode()
    request = FakeRequest("POST", body=body)
    response = await api_toxicity(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["created"] is True
    mock_add.assert_called_once()
    call_kwargs = mock_add.call_args[1]
    assert call_kwargs["event_date"] == "2026-03-07"
    assert call_kwargs["event_type"] == "toxicity_log"
    assert call_kwargs["metadata"]["neuropathy"] == 1
    assert call_kwargs["metadata"]["fatigue"] == 2


@pytest.mark.anyio
async def test_api_toxicity_post_requires_date():
    body = json.dumps({"neuropathy": 1}).encode()
    request = FakeRequest("POST", body=body)
    response = await api_toxicity(request)
    assert response.status_code == 400


@pytest.mark.anyio
async def test_api_toxicity_post_rejects_invalid_json():
    request = FakeRequest("POST", body=b"not json")
    response = await api_toxicity(request)
    assert response.status_code == 400


# ── /api/labs GET ────────────────────────────────


MOCK_LAB_EVENTS = [
    {
        "id": 10,
        "event_date": "2026-03-01",
        "event_type": "lab_result",
        "title": "Lab results 2026-03-01",
        "notes": "",
        "metadata": {"ANC": 2100, "PLT": 180000, "CEA": 12.5, "CA_19_9": 45.0},
    },
    {
        "id": 11,
        "event_date": "2026-02-15",
        "event_type": "lab_result",
        "title": "Lab results 2026-02-15",
        "notes": "Low platelets",
        "metadata": {"ANC": 800, "PLT": 60000},
    },
]


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_labs_get_returns_entries_with_alerts(mock_list):
    mock_list.return_value = MOCK_LAB_EVENTS
    request = FakeRequest("GET")
    response = await api_labs(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 2

    # First entry: all values safe
    assert data["entries"][0]["values"]["CEA"] == 12.5
    assert data["entries"][0]["alerts"] == []

    # Second entry: ANC < 1500 and PLT < 75000 -> 2 alerts
    assert len(data["entries"][1]["alerts"]) == 2
    alert_params = [a["param"] for a in data["entries"][1]["alerts"]]
    assert "ANC" in alert_params
    assert "PLT" in alert_params


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_labs_get_handles_string_metadata(mock_list):
    """Metadata may come as JSON string from oncofiles."""
    mock_list.return_value = [
        {
            "id": 1,
            "event_date": "2026-03-01",
            "event_type": "lab_result",
            "title": "Lab",
            "notes": "",
            "metadata": '{"ANC": 2000, "PLT": 100000}',
        }
    ]
    request = FakeRequest("GET")
    response = await api_labs(request)
    data = json.loads(response.body)

    assert data["entries"][0]["values"]["ANC"] == 2000
    assert data["entries"][0]["alerts"] == []


# ── /api/labs POST ───────────────────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.add_treatment_event",
    new_callable=AsyncMock,
)
async def test_api_labs_post_creates_entry(mock_add):
    mock_add.return_value = {"id": 20}
    body = json.dumps(
        {
            "date": "2026-03-07",
            "values": {"ANC": 2500, "PLT": 160000, "CEA": 10.2},
            "notes": "Pre-cycle labs",
        }
    ).encode()
    request = FakeRequest("POST", body=body)
    response = await api_labs(request)
    data = json.loads(response.body)

    assert data["created"] is True
    call_kwargs = mock_add.call_args[1]
    assert call_kwargs["event_type"] == "lab_result"
    assert call_kwargs["metadata"]["ANC"] == 2500


@pytest.mark.anyio
async def test_api_labs_post_requires_date():
    body = json.dumps({"values": {"ANC": 2000}}).encode()
    request = FakeRequest("POST", body=body)
    response = await api_labs(request)
    assert response.status_code == 400


# ── Labs analyze_labs fallback ─────────────────


# ── /api/labs reference ranges ──────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_labs_includes_reference_ranges(mock_list):
    mock_list.return_value = MOCK_LAB_EVENTS
    request = FakeRequest("GET")
    response = await api_labs(request)
    data = json.loads(response.body)

    assert "reference_ranges" in data
    assert "ANC" in data["reference_ranges"]
    assert data["reference_ranges"]["ANC"]["min"] == 1800
    assert data["reference_ranges"]["ANC"]["max"] == 7700


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_labs_value_statuses(mock_list):
    """Values outside reference range get status field."""
    mock_list.return_value = MOCK_LAB_EVENTS
    request = FakeRequest("GET")
    response = await api_labs(request)
    data = json.loads(response.body)

    # First entry: ANC=2100 (normal 1800-7700), PLT=180000 (normal), CEA=12.5 (high >5.0)
    statuses = data["entries"][0]["value_statuses"]
    assert statuses["ANC"] == "normal"
    assert statuses["PLT"] == "normal"
    assert statuses["CEA"] == "high"
    assert statuses["CA_19_9"] == "high"  # 45.0 > 37.0

    # Second entry: ANC=800 (low <1800), PLT=60000 (low <150000)
    statuses2 = data["entries"][1]["value_statuses"]
    assert statuses2["ANC"] == "low"
    assert statuses2["PLT"] == "low"


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_labs_reference_ranges_match_protocol(mock_list):
    """Reference ranges in response should match clinical_protocol data."""
    from oncoteam.clinical_protocol import LAB_REFERENCE_RANGES

    mock_list.return_value = []
    request = FakeRequest("GET")
    response = await api_labs(request)
    data = json.loads(response.body)

    assert data["reference_ranges"] == LAB_REFERENCE_RANGES


# ── Labs analyze_labs fallback ─────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_lab_trends_data",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_labs_fallback_to_lab_trends(mock_list, mock_trends):
    """When no lab_result events exist, fallback to lab_values table."""
    mock_list.return_value = []
    mock_trends.return_value = {
        "values": [
            {"lab_date": "2026-03-01", "parameter": "ANC", "value": 2500, "document_id": 5},
            {"lab_date": "2026-03-01", "parameter": "PLT", "value": 180000, "document_id": 5},
            {"lab_date": "2026-02-15", "parameter": "ANC", "value": 1800, "document_id": 3},
            {"lab_date": "2026-02-15", "parameter": "CEA", "value": 12.5, "document_id": 3},
        ],
        "total": 4,
    }

    request = FakeRequest("GET")
    response = await api_labs(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 2
    # Sorted descending
    assert data["entries"][0]["date"] == "2026-03-01"
    assert data["entries"][0]["values"]["ANC"] == 2500
    assert data["entries"][0]["values"]["PLT"] == 180000
    assert data["entries"][1]["date"] == "2026-02-15"
    assert data["entries"][1]["values"]["CEA"] == 12.5
    mock_trends.assert_called_once()


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.analyze_labs",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_lab_trends_data",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_labs_fallback_to_analyze_labs(mock_list, mock_trends, mock_analyze):
    """When both treatment_events and lab_trends empty, fall to analyze_labs."""
    mock_list.return_value = []
    mock_trends.return_value = {"values": [], "total": 0}
    mock_analyze.return_value = {
        "lab_results": [
            {"date": "2026-02-20", "ANC": 3200, "PLT": 200000, "notes": "Pre-chemo"},
            {"date": "2026-03-05", "ANC": 1800, "PLT": 120000},
        ]
    }

    request = FakeRequest("GET")
    response = await api_labs(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 2
    assert data["entries"][0]["date"] == "2026-03-05"
    assert data["entries"][1]["date"] == "2026-02-20"
    mock_analyze.assert_called_once()


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.analyze_labs",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_lab_trends_data",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_labs_fallback_skipped_when_events_exist(mock_list, mock_trends, mock_analyze):
    """Fallback should not be called when structured events exist."""
    mock_list.return_value = MOCK_LAB_EVENTS
    request = FakeRequest("GET")
    response = await api_labs(request)
    data = json.loads(response.body)

    assert data["total"] == 2
    mock_trends.assert_not_called()
    mock_analyze.assert_not_called()


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.analyze_labs",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_lab_trends_data",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_labs_fallback_error_handled(mock_list, mock_trends, mock_analyze):
    """If all fallbacks fail, return empty gracefully."""
    mock_list.return_value = []
    mock_trends.side_effect = Exception("lab_trends unreachable")
    mock_analyze.side_effect = Exception("oncofiles unreachable")

    request = FakeRequest("GET")
    response = await api_labs(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 0


# ── _normalize_lab_values unit tests ─────────────


def test_normalize_maps_abs_neut_to_anc():
    """ABS_NEUT should be renamed to ANC."""
    meta = {"ABS_NEUT": 2400, "PLT": 180000}
    result = _normalize_lab_values(meta)
    assert "ANC" in result
    assert "ABS_NEUT" not in result
    assert result["ANC"] == 2400


def test_normalize_converts_gl_to_ul():
    """ANC in G/L (< 30) should be multiplied by 1000 to get /µL."""
    meta = {"ANC": 1.15}
    result = _normalize_lab_values(meta)
    assert result["ANC"] == 1150


def test_normalize_leaves_ul_unchanged():
    """ANC already in /µL (>= 30) should not be changed."""
    meta = {"ANC": 2400}
    result = _normalize_lab_values(meta)
    assert result["ANC"] == 2400


def test_normalize_abs_neut_gl_combined():
    """ABS_NEUT in G/L should be renamed AND converted."""
    meta = {"ABS_NEUT": 3.5}
    result = _normalize_lab_values(meta)
    assert "ANC" in result
    assert "ABS_NEUT" not in result
    assert result["ANC"] == 3500


def test_normalize_does_not_overwrite_existing_anc():
    """If both ABS_NEUT and ANC exist, keep ANC."""
    meta = {"ABS_NEUT": 1.5, "ANC": 2400}
    result = _normalize_lab_values(meta)
    assert result["ANC"] == 2400
    assert "ABS_NEUT" in result  # not removed since ANC already existed
