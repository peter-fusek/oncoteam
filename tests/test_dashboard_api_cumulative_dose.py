"""Tests for /api/cumulative-dose dashboard endpoint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_cumulative_dose


class FakeRequest:
    def __init__(self, query: str = "patient_id=q1b"):
        from starlette.datastructures import QueryParams

        self.query_params = QueryParams(query)


def _mock_chemo_events(entries=None):
    """Patch list_treatment_events to return given entries (default: empty)."""
    return patch(
        "oncoteam.oncofiles_client.list_treatment_events",
        new_callable=AsyncMock,
        return_value={"entries": entries or [], "total": len(entries or [])},
    )


@pytest.mark.anyio
async def test_cumulative_dose_calculated_fallback():
    """With no extracted data, uses patient's actual dose (76.5 mg/m² at 90%)."""
    with _mock_chemo_events():
        request = FakeRequest()
        response = await api_cumulative_dose(request)
        data = json.loads(response.body)

    assert response.status_code == 200
    assert data["drug"] == "oxaliplatin"
    assert data["dose_per_cycle"] == 76.5
    assert data["data_source"] == "calculated"
    assert data["cumulative_mg_m2"] == data["cycles_counted"] * 76.5


@pytest.mark.anyio
async def test_cumulative_dose_uses_extracted_data():
    """With extracted chemo events, sums actual per-cycle doses."""
    entries = [
        {
            "event_date": "2026-02-13",
            "metadata": {
                "cycle": 1,
                "drugs": [{"name": "oxaliplatin", "dose_mg_m2": 85.0, "dose_reduction_pct": 0}],
            },
        },
        {
            "event_date": "2026-02-27",
            "metadata": {
                "cycle": 2,
                "drugs": [{"name": "oxaliplatin", "dose_mg_m2": 76.5, "dose_reduction_pct": 10}],
            },
        },
    ]
    with _mock_chemo_events(entries):
        request = FakeRequest()
        response = await api_cumulative_dose(request)
        data = json.loads(response.body)

    assert data["data_source"] == "extracted"
    assert data["cycles_counted"] == 2
    assert data["cumulative_mg_m2"] == 161.5  # 85.0 + 76.5
    assert data["dose_per_cycle"] == 76.5  # most recent cycle's dose
    assert len(data["cycles_detail"]) == 2


@pytest.mark.anyio
async def test_cumulative_dose_flags_thresholds():
    """With cycle 6 (459 mg/m² at 76.5/cycle), should reach the 400 threshold."""
    from oncoteam.patient_context import PATIENT

    original_cycle = PATIENT.current_cycle
    try:
        PATIENT.current_cycle = 6
        with _mock_chemo_events():
            request = FakeRequest()
            response = await api_cumulative_dose(request)
            data = json.loads(response.body)
    finally:
        PATIENT.current_cycle = original_cycle

    assert data["cumulative_mg_m2"] == 459.0
    assert len(data["thresholds_reached"]) == 1
    assert data["thresholds_reached"][0]["at"] == 400
    assert data["next_threshold"]["at"] == 550


@pytest.mark.anyio
async def test_cumulative_dose_next_threshold():
    """Should return the next upcoming threshold."""
    with _mock_chemo_events():
        request = FakeRequest()
        response = await api_cumulative_dose(request)
        data = json.loads(response.body)

    assert data["next_threshold"] is not None
    assert "at" in data["next_threshold"]
    assert "action" in data["next_threshold"]
    assert data["pct_to_next"] <= 100.0


@pytest.mark.anyio
async def test_cumulative_dose_all_thresholds_present():
    """Should return all 4 thresholds."""
    with _mock_chemo_events():
        request = FakeRequest()
        response = await api_cumulative_dose(request)
        data = json.loads(response.body)

    assert len(data["all_thresholds"]) == 4
    assert data["max_recommended"] == 850
