"""Canonical tag vocabulary for oncoteam.

All tags should use prefix:value format. This module provides
constants and a normalize function for migration.
"""

from __future__ import annotations

# Tag prefixes
SYS = "sys"  # System: autonomous, cost_alert, session
CLIN = "clin"  # Clinical: labs, toxicity, imaging
BIO = "bio"  # Biomarker: kras_g12s, mss, her2_neg
TX = "tx"  # Treatment: folfox6, bevacizumab, cycle_3
RES = "res"  # Research: pubmed, clinical_trials, eu_trials
TASK = "task"  # Task type: daily_research, trial_monitor
SAFETY = "safety"  # Safety: neutropenia, vte, dose_hold
SRC = "src"  # Source: nou, pubmed, clinicaltrials


def tag(prefix: str, value: str) -> str:
    """Build a canonical tag from prefix and value."""
    return f"{prefix}:{value}"


# Common tags
AUTONOMOUS = tag(SYS, "autonomous")
COST_ALERT = tag(SYS, "cost-alert")
BUDGET_LOW = tag(SYS, "budget-low")
SESSION = tag(SYS, "session")

DAILY_BRIEFING = tag(TASK, "daily-briefing")
DAILY_RESEARCH = tag(TASK, "daily-research")
TRIAL_MONITOR = tag(TASK, "trial-monitor")
WEEKLY_BRIEFING = tag(TASK, "weekly-briefing")
DOCUMENT_SCAN = tag(TASK, "document-scan")
DOCUMENT_PIPELINE = tag(TASK, "document-pipeline")
PIPELINE_STEP = tag(TASK, "pipeline-step")

ADJACENT_COUNTRIES = tag(RES, "adjacent-countries")
EU_TRIALS = tag(RES, "eu-trials")

# Migration mapping: old tag -> new canonical tag
TAG_MIGRATION: dict[str, str] = {
    "autonomous": "sys:autonomous",
    "cost_alert": "sys:cost-alert",
    "budget_low": "sys:budget-low",
    "session": "sys:session",
    "daily_briefing": "task:daily-briefing",
    "adjacent_countries": "res:adjacent-countries",
    "eu_trials": "res:eu-trials",
    "daily-scan": "task:daily-research",
    "document-scan": "task:document-scan",
    "document_scan": "task:document-scan",
    "trial_monitor": "task:trial-monitor",
    "weekly-briefing": "task:weekly-briefing",
}


def normalize_tags(tags: list[str]) -> list[str]:
    """Normalize legacy tags to canonical format.

    - Applies TAG_MIGRATION mapping
    - Strips session IDs (sid:*) -- these are metadata, not tags
    - Strips date tags (date:*) -- these are metadata
    - Strips patient name tags -- single-patient system
    """
    result: list[str] = []
    for t in tags:
        # Skip noise tags
        if t.startswith("sid:") or t.startswith("date:") or t == "patient_name":
            continue
        # Apply migration
        canonical = TAG_MIGRATION.get(t, t)
        if canonical not in result:
            result.append(canonical)
    return result
