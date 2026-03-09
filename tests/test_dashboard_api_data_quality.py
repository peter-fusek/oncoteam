"""Tests for data quality functions: timeline dedup, session relevance filtering."""

from __future__ import annotations

from oncoteam.dashboard_api import (
    _deduplicate_timeline,
    _extract_cycle_number,
    _is_oncology_session,
)

# ── _extract_cycle_number ─────────────────────────


def test_extract_cycle_c_prefix():
    assert _extract_cycle_number("FOLFOX C2") == 2


def test_extract_cycle_word():
    assert _extract_cycle_number("Cycle 5 FOLFOX") == 5


def test_extract_cycle_cyklus():
    assert _extract_cycle_number("2. cyklus FOLFOX") == 2


def test_extract_cycle_none():
    assert _extract_cycle_number("Blood draw") is None


def test_extract_cycle_large_number():
    assert _extract_cycle_number("FOLFOX C12 day 1") == 12


# ── _deduplicate_timeline ─────────────────────────


def test_dedup_merges_same_date_cycle():
    events = [
        {"event_date": "2026-03-01", "title": "FOLFOX C2", "notes": "short", "id": 1},
        {
            "event_date": "2026-03-01",
            "title": "Cycle 2 infusion",
            "notes": "longer notes here",
            "id": 2,
        },
    ]
    result = _deduplicate_timeline(events)
    assert len(result) == 1
    # Keeps the one with longer notes
    assert result[0]["id"] == 2


def test_dedup_keeps_different_dates():
    events = [
        {"event_date": "2026-03-01", "title": "FOLFOX C2", "notes": "", "id": 1},
        {"event_date": "2026-03-15", "title": "FOLFOX C3", "notes": "", "id": 2},
    ]
    result = _deduplicate_timeline(events)
    assert len(result) == 2


def test_dedup_no_cycle_events_preserved():
    events = [
        {"event_date": "2026-03-01", "title": "Blood draw", "notes": "", "id": 1},
        {"event_date": "2026-03-01", "title": "CT scan", "notes": "", "id": 2},
    ]
    result = _deduplicate_timeline(events)
    assert len(result) == 2


def test_dedup_mixed_events():
    events = [
        {"event_date": "2026-03-01", "title": "FOLFOX C2", "notes": "a", "id": 1},
        {"event_date": "2026-03-01", "title": "Cycle 2", "notes": "abc", "id": 2},
        {"event_date": "2026-03-01", "title": "Blood draw", "notes": "", "id": 3},
    ]
    result = _deduplicate_timeline(events)
    # 1 merged cycle + 1 blood draw
    assert len(result) == 2


def test_dedup_sorted_descending():
    events = [
        {"event_date": "2026-02-01", "title": "FOLFOX C1", "notes": "", "id": 1},
        {"event_date": "2026-03-01", "title": "Blood draw", "notes": "", "id": 2},
    ]
    result = _deduplicate_timeline(events)
    assert result[0]["event_date"] == "2026-03-01"
    assert result[1]["event_date"] == "2026-02-01"


def test_dedup_empty_list():
    assert _deduplicate_timeline([]) == []


# ── _is_oncology_session ──────────────────────────


def test_oncology_session_positive():
    entry = {"title": "Session: FOLFOX cycle 2 review", "content": "Lab results discussed."}
    assert _is_oncology_session(entry) is True


def test_oncology_session_filters_accounting():
    entry = {"title": "Accounting Q1 2026", "content": "Invoice processing."}
    assert _is_oncology_session(entry) is False


def test_oncology_session_filters_instarea():
    entry = {"title": "Instarea sprint review", "content": "Project updates."}
    assert _is_oncology_session(entry) is False


def test_oncology_session_filters_by_content():
    entry = {
        "title": "Weekly sync",
        "content": "contacts refiner integration progress and billing review.",
    }
    assert _is_oncology_session(entry) is False


def test_oncology_session_case_insensitive():
    entry = {"title": "ACCOUNTING Report", "content": ""}
    assert _is_oncology_session(entry) is False


def test_oncology_session_empty_entry():
    assert _is_oncology_session({}) is True


def test_oncology_session_homegrif():
    entry = {"title": "Homegrif schedule", "content": ""}
    assert _is_oncology_session(entry) is False


def test_oncology_session_shift_rotation():
    entry = {"title": "Shift rotation planning", "content": ""}
    assert _is_oncology_session(entry) is False
