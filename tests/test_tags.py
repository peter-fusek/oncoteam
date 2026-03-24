"""Tests for tag taxonomy normalization."""

from __future__ import annotations

from oncoteam.tags import (
    ADJACENT_COUNTRIES,
    AUTONOMOUS,
    COST_ALERT,
    DAILY_BRIEFING,
    EU_TRIALS,
    SESSION,
    TAG_MIGRATION,
    normalize_tags,
    tag,
)


class TestTagFunction:
    def test_builds_prefixed_tag(self):
        assert tag("sys", "autonomous") == "sys:autonomous"

    def test_constants_use_prefix_format(self):
        assert AUTONOMOUS == "sys:autonomous"
        assert COST_ALERT == "sys:cost-alert"
        assert SESSION == "sys:session"
        assert DAILY_BRIEFING == "task:daily-briefing"
        assert ADJACENT_COUNTRIES == "res:adjacent-countries"
        assert EU_TRIALS == "res:eu-trials"


class TestNormalizeTags:
    def test_removes_sid_tags(self):
        result = normalize_tags(["sys:autonomous", "sid:abc123"])
        assert result == ["sys:autonomous"]

    def test_removes_date_tags(self):
        result = normalize_tags(["sys:cost-alert", "date:2026-03-17"])
        assert result == ["sys:cost-alert"]

    def test_removes_patient_name(self):
        result = normalize_tags(["task:daily-briefing", "patient_name"])
        assert result == ["task:daily-briefing"]

    def test_applies_migration_mapping(self):
        result = normalize_tags(["autonomous", "daily_briefing", "adjacent_countries"])
        assert result == ["sys:autonomous", "task:daily-briefing", "res:adjacent-countries"]

    def test_deduplicates(self):
        result = normalize_tags(["autonomous", "sys:autonomous"])
        assert result == ["sys:autonomous"]

    def test_preserves_already_canonical(self):
        result = normalize_tags(["sys:session", "res:eu-trials"])
        assert result == ["sys:session", "res:eu-trials"]

    def test_preserves_unknown_tags(self):
        result = normalize_tags(["colorectal cancer", "KRAS"])
        assert result == ["colorectal cancer", "KRAS"]

    def test_empty_list(self):
        assert normalize_tags([]) == []

    def test_all_noise_tags_removed(self):
        result = normalize_tags(["sid:xyz", "date:2026-01-01", "patient_name"])
        assert result == []

    def test_migration_mapping_covers_known_legacy_tags(self):
        legacy_tags = [
            "autonomous",
            "cost_alert",
            "budget_low",
            "session",
            "daily_briefing",
            "adjacent_countries",
            "eu_trials",
            "daily-scan",
            "document-scan",
            "document_scan",
            "trial_monitor",
            "weekly-briefing",
        ]
        for t in legacy_tags:
            assert t in TAG_MIGRATION, f"Legacy tag {t!r} missing from TAG_MIGRATION"
            assert ":" in TAG_MIGRATION[t], f"Canonical tag for {t!r} missing prefix"
