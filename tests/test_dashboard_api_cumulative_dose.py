"""Tests for /api/cumulative-dose dashboard endpoint."""

from __future__ import annotations

import json

import pytest

from oncoteam.dashboard_api import api_cumulative_dose


class FakeRequest:
    def __init__(self, query: str = ""):
        from starlette.datastructures import QueryParams

        self.query_params = QueryParams(query)


@pytest.mark.anyio
async def test_cumulative_dose_returns_correct_dose():
    """Cumulative dose uses patient's actual dose (76.5 mg/m² at 90%)."""
    request = FakeRequest()
    response = await api_cumulative_dose(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["drug"] == "oxaliplatin"
    assert data["dose_per_cycle"] == 76.5
    assert data["cumulative_mg_m2"] == data["cycles_counted"] * 76.5


@pytest.mark.anyio
async def test_cumulative_dose_flags_thresholds():
    """With cycle 6 (459 mg/m² at 76.5/cycle), should reach the 400 threshold."""
    from oncoteam.patient_context import PATIENT

    original_cycle = PATIENT.current_cycle
    try:
        PATIENT.current_cycle = 6
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
    request = FakeRequest()
    response = await api_cumulative_dose(request)
    data = json.loads(response.body)

    assert len(data["all_thresholds"]) == 4
    assert data["max_recommended"] == 850
