"""Tests for clinical protocol data and helper functions."""

from __future__ import annotations

from oncoteam.clinical_protocol import (
    DOSE_MODIFICATION_RULES,
    LAB_SAFETY_THRESHOLDS,
    MONITORING_SCHEDULE,
    SAFETY_FLAGS,
    SECOND_LINE_OPTIONS,
    TREATMENT_MILESTONES,
    WATCHED_TRIALS,
    check_lab_safety,
    format_pre_cycle_checklist,
    get_dose_modification,
    get_milestones_for_cycle,
)


class TestLabSafetyThresholds:
    def test_all_thresholds_have_action(self):
        for name, threshold in LAB_SAFETY_THRESHOLDS.items():
            assert "action" in threshold, f"{name} missing action"

    def test_anc_safe(self):
        result = check_lab_safety("ANC", 2000)
        assert result["safe"] is True

    def test_anc_unsafe(self):
        result = check_lab_safety("ANC", 1200)
        assert result["safe"] is False
        assert result["action"] == "hold_chemo"

    def test_plt_safe(self):
        result = check_lab_safety("PLT", 150000)
        assert result["safe"] is True

    def test_plt_unsafe(self):
        result = check_lab_safety("PLT", 60000)
        assert result["safe"] is False
        assert result["action"] == "hold_chemo"

    def test_plt_anticoag_threshold(self):
        result = check_lab_safety("PLT_anticoag", 45000)
        assert result["safe"] is False
        assert result["action"] == "flag_hematology"

    def test_plt_anticoag_safe(self):
        result = check_lab_safety("PLT_anticoag", 55000)
        assert result["safe"] is True

    def test_unknown_lab(self):
        result = check_lab_safety("UNKNOWN_LAB", 100)
        assert result["safe"] is True
        assert "No threshold" in result["message"]

    def test_boundary_anc_exact_min(self):
        result = check_lab_safety("ANC", 1500)
        assert result["safe"] is True

    def test_boundary_anc_just_below(self):
        result = check_lab_safety("ANC", 1499)
        assert result["safe"] is False


class TestDoseModification:
    def test_neuropathy_grade_2(self):
        rule = get_dose_modification("neuropathy_grade_2")
        assert rule is not None
        assert "75%" in rule

    def test_neuropathy_grade_3(self):
        rule = get_dose_modification("neuropathy_grade_3")
        assert rule is not None
        assert "HOLD" in rule

    def test_neuropathy_grade_4(self):
        rule = get_dose_modification("neuropathy_grade_4")
        assert rule is not None
        assert "DISCONTINUE" in rule

    def test_unknown_toxicity(self):
        assert get_dose_modification("unknown") is None

    def test_all_rules_are_bilingual_dicts(self):
        for key, value in DOSE_MODIFICATION_RULES.items():
            assert isinstance(value, dict), f"{key} is not a bilingual dict"
            assert "sk" in value and "en" in value, f"{key} missing sk/en keys"


class TestTreatmentMilestones:
    def test_milestones_exist(self):
        assert len(TREATMENT_MILESTONES) >= 6

    def test_first_milestone_is_cycle_3(self):
        assert TREATMENT_MILESTONES[0]["cycle"] == 3

    def test_milestones_for_cycle_3(self):
        milestones = get_milestones_for_cycle(3)
        assert len(milestones) >= 1
        actions = [m["action"] for m in milestones]
        assert "first_response_ct" in actions

    def test_milestones_for_cycle_5(self):
        # cycle 5 should pick up cycle 6 milestones (cycle+1)
        milestones = get_milestones_for_cycle(5)
        actions = [m["action"] for m in milestones]
        assert "neuropathy_cumulative" in actions

    def test_milestones_for_cycle_100(self):
        milestones = get_milestones_for_cycle(100)
        assert milestones == []


class TestPreCycleChecklist:
    def test_format_basic(self):
        text = format_pre_cycle_checklist(3)
        assert "Pre-Cycle 3" in text
        assert "ANC >= 1,500" in text
        assert "Clexane" in text

    def test_format_with_milestones(self):
        text = format_pre_cycle_checklist(
            4,
            milestones="- CT scan due",
            questions="- Is neuropathy progressing?",
        )
        assert "CT scan due" in text
        assert "neuropathy progressing" in text


class TestProtocolData:
    def test_monitoring_schedule_complete(self):
        expected = [
            "pre_cycle_labs",
            "tumor_markers",
            "response_imaging",
            "neuropathy_grade",
            "vte_check",
            "ecog_assessment",
        ]
        for key in expected:
            assert key in MONITORING_SCHEDULE

    def test_watched_trials_not_empty(self):
        assert len(WATCHED_TRIALS) >= 5

    def test_second_line_options_have_regimen(self):
        for opt in SECOND_LINE_OPTIONS:
            assert "regimen" in opt
            assert "evidence" in opt

    def test_safety_flags_have_source(self):
        for key, flag in SAFETY_FLAGS.items():
            assert "rule" in flag, f"{key} missing rule"
            assert "source" in flag, f"{key} missing source"
