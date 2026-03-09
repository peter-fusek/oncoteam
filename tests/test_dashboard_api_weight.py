"""Tests for /api/weight dashboard endpoint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_weight


class FakeRequest:
    def __init__(self, method: str = "GET", query: str = ""):
        from starlette.datastructures import QueryParams

        self.method = method
        self.query_params = QueryParams(query)


MOCK_WEIGHT_EVENTS = [
    {
        "id": 1,
        "event_date": "2026-03-01",
        "event_type": "weight_measurement",
        "title": "Weight 2026-03-01",
        "notes": "",
        "metadata": {"weight_kg": 70.5, "appetite": 3},
    },
]

MOCK_TOXICITY_EVENTS = [
    {
        "id": 10,
        "event_date": "2026-02-25",
        "event_type": "toxicity_log",
        "title": "Toxicity log",
        "notes": "",
        "metadata": {"weight_kg": 71.0, "neuropathy": 1},
    },
]


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_weight_get_returns_entries(mock_list):
    # First call: weight_measurement, second call: toxicity_log
    mock_list.side_effect = [MOCK_WEIGHT_EVENTS, []]
    request = FakeRequest("GET")
    response = await api_weight(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 1
    assert data["entries"][0]["weight_kg"] == 70.5
    assert data["baseline_weight_kg"] == 72.0


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_weight_merges_toxicity_weights(mock_list):
    mock_list.side_effect = [MOCK_WEIGHT_EVENTS, MOCK_TOXICITY_EVENTS]
    request = FakeRequest("GET")
    response = await api_weight(request)
    data = json.loads(response.body)

    assert data["total"] == 2
    dates = [e["date"] for e in data["entries"]]
    assert "2026-02-25" in dates
    assert "2026-03-01" in dates


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_weight_calculates_loss_pct(mock_list):
    mock_list.side_effect = [
        [
            {
                "id": 1,
                "event_date": "2026-03-01",
                "event_type": "weight_measurement",
                "metadata": {"weight_kg": 70.0},
            }
        ],
        [],
    ]
    request = FakeRequest("GET")
    response = await api_weight(request)
    data = json.loads(response.body)

    # 72 baseline -> 70 = -2.8%
    entry = data["entries"][0]
    assert entry["pct_change"] == -2.8
    assert entry["alert"] is False


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_weight_flags_5pct_loss(mock_list):
    # 72 baseline -> 68 = -5.6%
    mock_list.side_effect = [
        [
            {
                "id": 1,
                "event_date": "2026-03-01",
                "event_type": "weight_measurement",
                "metadata": {"weight_kg": 68.0},
            }
        ],
        [],
    ]
    request = FakeRequest("GET")
    response = await api_weight(request)
    data = json.loads(response.body)

    assert data["entries"][0]["alert"] is True
    assert len(data["alerts"]) == 1
    assert data["alerts"][0]["loss_pct"] == 5.6


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_weight_7pct_loss_gets_dietitian_referral(mock_list):
    """7% loss should get dietitian referral action."""
    # 72 baseline -> 66.96 = -7.0%
    mock_list.side_effect = [
        [
            {
                "id": 1,
                "event_date": "2026-03-01",
                "event_type": "weight_measurement",
                "metadata": {"weight_kg": 66.96},
            }
        ],
        [],
    ]
    request = FakeRequest("GET", query="lang=en")
    response = await api_weight(request)
    data = json.loads(response.body)

    assert len(data["alerts"]) == 1
    assert "Dietitian referral" in data["alerts"][0]["action"]
    assert data["alerts"][0]["severity"] == "warning"


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_weight_10pct_loss_gets_enteral_nutrition(mock_list):
    """10% loss should get enteral nutrition action."""
    # 72 baseline -> 64.8 = -10.0%
    mock_list.side_effect = [
        [
            {
                "id": 1,
                "event_date": "2026-03-01",
                "event_type": "weight_measurement",
                "metadata": {"weight_kg": 64.8},
            }
        ],
        [],
    ]
    request = FakeRequest("GET", query="lang=en")
    response = await api_weight(request)
    data = json.loads(response.body)

    assert len(data["alerts"]) == 1
    assert "enteral nutrition" in data["alerts"][0]["action"]
    assert data["alerts"][0]["severity"] == "critical"


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_weight_includes_nutrition_escalation(mock_list):
    """Weight response should include nutrition_escalation rules."""
    mock_list.side_effect = [[], []]
    request = FakeRequest("GET")
    response = await api_weight(request)
    data = json.loads(response.body)

    assert "nutrition_escalation" in data
    assert len(data["nutrition_escalation"]) == 4
    assert data["nutrition_escalation"][0]["loss_pct"] == 5


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_weight_handles_error(mock_list):
    """When both gather calls fail, entries should be empty."""
    mock_list.side_effect = Exception("fail")
    request = FakeRequest("GET")
    response = await api_weight(request)
    data = json.loads(response.body)
    # return_exceptions=True means top-level doesn't raise — just empty entries
    assert response.status_code == 200
    assert data["entries"] == []
    assert data["baseline_weight_kg"] == 72.0


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.add_treatment_event",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_toxicity_post_accepts_nutrition_fields(mock_list, mock_add):
    """Toxicity POST should accept appetite and oral_intake."""
    from oncoteam.dashboard_api import api_toxicity

    class FakePostRequest:
        method = "POST"

        def __init__(self):
            from starlette.datastructures import QueryParams

            self.query_params = QueryParams("")

        async def body(self):
            return json.dumps(
                {
                    "date": "2026-03-08",
                    "appetite": 2,
                    "oral_intake": 60,
                    "weight_kg": 70,
                }
            ).encode()

    mock_add.return_value = {"id": 99}
    request = FakePostRequest()
    response = await api_toxicity(request)
    data = json.loads(response.body)

    assert data["created"] is True
    meta = mock_add.call_args[1]["metadata"]
    assert meta["appetite"] == 2
    assert meta["oral_intake"] == 60
    assert meta["weight_kg"] == 70
