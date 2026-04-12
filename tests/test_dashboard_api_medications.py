"""Tests for /api/medications dashboard endpoint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_medications


class FakeRequest:
    def __init__(self, method: str = "GET", query: str = "", body: bytes = b""):
        from starlette.datastructures import QueryParams

        self.method = method
        self.query_params = QueryParams(query)
        self._body = body

    async def body(self) -> bytes:
        return self._body


MOCK_MEDICATION_EVENTS = [
    {
        "id": 1,
        "event_date": "2026-03-07",
        "event_type": "medication_log",
        "title": "Clexane 2026-03-07",
        "notes": "Morning dose",
        "metadata": {
            "name": "Clexane",
            "dose": "0.6ml SC",
            "frequency": "2x/day",
            "active": True,
        },
    },
]


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_medications_get_returns_entries(mock_list):
    mock_list.side_effect = [MOCK_MEDICATION_EVENTS, []]  # medication_log + adherence
    request = FakeRequest("GET")
    response = await api_medications(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 1
    assert data["medications"][0]["name"] == "Clexane"
    assert data["medications"][0]["dose"] == "0.6ml SC"


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_medications_get_includes_defaults(mock_list):
    mock_list.side_effect = [[], []]  # medication_log + adherence
    request = FakeRequest("GET")
    response = await api_medications(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert len(data["default_medications"]) == 0  # no hardcoded defaults


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_medications_get_handles_error(mock_list):
    mock_list.side_effect = Exception("fail")
    request = FakeRequest("GET")
    response = await api_medications(request)
    # return_exceptions=True means gather catches the error, returns empty lists
    assert response.status_code == 200
    data = json.loads(response.body)
    assert len(data["default_medications"]) == 0
    assert data["medications"] == []


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.add_treatment_event",
    new_callable=AsyncMock,
)
async def test_api_medications_post_creates_entry(mock_add):
    mock_add.return_value = {"id": 99}
    body = json.dumps({"date": "2026-03-07", "name": "Clexane", "dose": "0.6ml SC"}).encode()
    request = FakeRequest("POST", body=body)
    response = await api_medications(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["created"] is True
    call_kwargs = mock_add.call_args[1]
    assert call_kwargs["event_type"] == "medication_log"
    assert call_kwargs["metadata"]["name"] == "Clexane"


@pytest.mark.anyio
async def test_api_medications_post_requires_date_and_name():
    body = json.dumps({"name": "Clexane"}).encode()
    request = FakeRequest("POST", body=body)
    response = await api_medications(request)
    assert response.status_code == 400

    body2 = json.dumps({"date": "2026-03-07"}).encode()
    request2 = FakeRequest("POST", body=body2)
    response2 = await api_medications(request2)
    assert response2.status_code == 400


@pytest.mark.anyio
async def test_api_medications_post_rejects_invalid_json():
    request = FakeRequest("POST", body=b"not json")
    response = await api_medications(request)
    assert response.status_code == 400


# ── Medication adherence ──────────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.add_treatment_event",
    new_callable=AsyncMock,
)
async def test_api_medications_adherence_post_creates_event(mock_add):
    mock_add.return_value = {"id": 100}
    body = json.dumps(
        {
            "date": "2026-03-08",
            "medications": {"Clexane": True, "Ondansetron": False},
        }
    ).encode()
    request = FakeRequest("POST", body=body)
    response = await api_medications(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["created"] is True
    assert data["event_type"] == "medication_adherence"
    call_kwargs = mock_add.call_args[1]
    assert call_kwargs["event_type"] == "medication_adherence"
    assert call_kwargs["metadata"]["medications"]["Clexane"] is True
    assert call_kwargs["metadata"]["medications"]["Ondansetron"] is False


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_medications_get_includes_adherence(mock_list):
    """GET should include adherence data with compliance calculation."""
    mock_list.side_effect = [
        MOCK_MEDICATION_EVENTS,  # medication_log
        [  # medication_adherence
            {
                "id": 50,
                "event_date": "2026-03-07",
                "event_type": "medication_adherence",
                "metadata": {"medications": {"Clexane": True, "Ondansetron": True}},
            },
            {
                "id": 51,
                "event_date": "2026-03-06",
                "event_type": "medication_adherence",
                "metadata": {"medications": {"Clexane": True, "Ondansetron": False}},
            },
        ],
    ]
    request = FakeRequest("GET")
    response = await api_medications(request)
    data = json.loads(response.body)

    assert "adherence" in data
    assert len(data["adherence"]["last_7_days"]) == 2
    assert data["adherence"]["compliance_pct"] == 75.0  # 3/4 = 75%
    assert len(data["adherence"]["missed"]) == 1
    assert data["adherence"]["missed"][0]["medication"] == "Ondansetron"


@pytest.mark.anyio
async def test_api_medications_adherence_post_requires_date():
    body = json.dumps({"medications": {"Clexane": True}}).encode()
    request = FakeRequest("POST", body=body)
    response = await api_medications(request)
    assert response.status_code == 400


# ── Patient token threading ──────────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
@patch("oncoteam.dashboard_api.get_patient_token", return_value="tok_jan_123")
async def test_api_medications_passes_patient_token(mock_get_token, mock_list):
    """Non-q1b patient_id causes a different token to be passed to oncofiles."""
    mock_list.return_value = []
    request = FakeRequest("GET", query="patient_id=jan")
    response = await api_medications(request)

    assert response.status_code == 200
    mock_get_token.assert_called_with("jan")
    # Medications endpoint calls list_treatment_events twice (medication_log + adherence)
    assert mock_list.call_count >= 1
    token_calls = [c for c in mock_list.call_args_list if c.kwargs.get("token") == "tok_jan_123"]
    assert len(token_calls) >= 1
