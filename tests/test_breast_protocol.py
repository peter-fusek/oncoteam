"""Tests for diagnosis-driven breast protocol dispatch (Sprint 90 #370)."""

from __future__ import annotations

import pytest

from oncoteam.breast_protocol import (
    BREAST_LAB_SAFETY_THRESHOLDS,
    BREAST_REGIMENS,
    is_breast_patient,
    resolve_breast_protocol,
)
from oncoteam.clinical_protocol import LAB_REFERENCE_RANGES, PARAMETER_HEALTH_DIRECTION


@pytest.fixture
def cleanup_test_patient():
    """Register a test breast patient and ensure it's removed from the
    module-level registry after the test. Prevents scheduler job count drift
    and cross-test pollution."""
    registered_ids: list[str] = []

    def _register(pid: str):
        from datetime import date

        from oncoteam.models import PatientProfile
        from oncoteam.patient_context import _patient_registry, register_patient

        if pid in _patient_registry:
            return
        register_patient(
            pid,
            "",
            PatientProfile(
                patient_id=pid,
                name="Test Breast",
                diagnosis_code="C50.9",
                diagnosis_description="Test breast cancer",
                tumor_site="Breast",
                diagnosis_date=date(2020, 1, 1),
                staging="IV",
                biomarkers={"HR": "positive", "HER2": "negative", "ER": "positive"},
                excluded_therapies={},
                treatment_regimen="CDK4/6 + AI",
                hospitals=[],
                treating_physician="",
                notes="",
                agent_whitelist=["keepalive_ping"],
            ),
        )
        registered_ids.append(pid)

    yield _register

    from oncoteam.patient_context import (
        _patient_recipients,
        _patient_registry,
        _patient_research_terms,
        _patient_tokens,
    )

    for pid in registered_ids:
        _patient_registry.pop(pid, None)
        _patient_tokens.pop(pid, None)
        _patient_research_terms.pop(pid, None)
        _patient_recipients.pop(pid, None)


def test_breast_tumor_markers_in_reference_ranges():
    """CA 15-3 and CA 27-29 must be defined with breast-specific ULN values."""
    assert "CA_15_3" in LAB_REFERENCE_RANGES
    assert "CA_27_29" in LAB_REFERENCE_RANGES
    assert LAB_REFERENCE_RANGES["CA_15_3"]["max"] == 30.0
    assert LAB_REFERENCE_RANGES["CA_27_29"]["max"] == 38.0


def test_breast_tumor_markers_health_direction_lower_is_better():
    """Both breast markers should follow 'lower_is_better' — rising = worsening."""
    assert PARAMETER_HEALTH_DIRECTION["CA_15_3"] == "lower_is_better"
    assert PARAMETER_HEALTH_DIRECTION["CA_27_29"] == "lower_is_better"


def test_is_breast_patient_accepts_c50_prefix():
    assert is_breast_patient("C50.9") is True
    assert is_breast_patient("C50.1") is True
    assert is_breast_patient("c50.9") is True  # case-insensitive


def test_is_breast_patient_rejects_non_c50():
    assert is_breast_patient("C18.7") is False
    assert is_breast_patient("Z00.0") is False
    assert is_breast_patient("") is False
    assert is_breast_patient(None) is False


def test_resolve_breast_protocol_returns_regimens_not_folfox():
    """Breast protocol must expose breast regimens and NOT leak mFOLFOX6 keys."""
    data = resolve_breast_protocol("en")
    assert data["tumor_type"] == "breast"
    assert "CDK46_AI" in data["regimens"]
    assert "TCHP" in data["regimens"]
    # Cumulative dose not applicable for CDK4/6-driven breast regimens
    assert data["cumulative_dose"] == {}


def test_breast_lab_thresholds_include_cdk46_anc_min():
    """CDK4/6 threshold: ANC ≥1000 (vs FOLFOX ≥1500). Source: FDA palbociclib label."""
    assert BREAST_LAB_SAFETY_THRESHOLDS["ANC"]["min"] == 1000
    assert "source" in BREAST_LAB_SAFETY_THRESHOLDS["ANC"]


def test_breast_regimens_cover_all_key_subtypes():
    """Every major HR+/HER2-/HER2+/TN subtype and BRCA must have at least one regimen."""
    assert "CDK46_AI" in BREAST_REGIMENS  # HR+/HER2- 1L
    assert "fulvestrant_CDK46" in BREAST_REGIMENS  # HR+/HER2- 2L
    assert "TCHP" in BREAST_REGIMENS  # HER2+
    assert "T-DXd" in BREAST_REGIMENS  # HER2+/HER2-low
    assert "PARP" in BREAST_REGIMENS  # BRCA


def test_build_system_prompt_breast_vs_colorectal_branches(cleanup_test_patient):
    """System prompt must switch content based on diagnosis prefix."""
    from oncoteam.autonomous import build_system_prompt

    pid = "test_c50"
    cleanup_test_patient(pid)

    breast_prompt = build_system_prompt(pid)
    # Breast prompt must NOT contain mFOLFOX6-specific markers
    assert "mFOLFOX6" not in breast_prompt
    assert "oxaliplatin" not in breast_prompt.lower() or "CDK4/6" in breast_prompt
    # Breast prompt must mention breast-specific tumor markers
    assert "CA 15-3" in breast_prompt or "CA_15_3" in breast_prompt
    # Colorectal prompt (q1b) must still be colorectal
    crc_prompt = build_system_prompt("q1b")
    assert "mFOLFOX6" in crc_prompt or "oxaliplatin" in crc_prompt.lower()


def test_breast_eligibility_blocks_parp_without_brca():
    """PARP inhibitor trials must flag a warning for BRCA-unknown patients."""
    from datetime import date

    from oncoteam.eligibility import check_eligibility
    from oncoteam.models import ClinicalTrial, PatientProfile

    patient = PatientProfile(
        patient_id="test_c50_brca",
        name="Test",
        diagnosis_code="C50.9",
        diagnosis_description="Test",
        tumor_site="Breast",
        diagnosis_date=date(2020, 1, 1),
        staging="IV",
        biomarkers={"HR": "positive", "HER2": "negative", "BRCA1": "unknown", "BRCA2": "unknown"},
        excluded_therapies={},
        treatment_regimen="CDK4/6 + AI",
        hospitals=[],
        treating_physician="",
        notes="",
    )
    trial = ClinicalTrial(
        nct_id="NCT99999999",
        title="Olaparib in breast cancer",
        status="Recruiting",
        phase="III",
        conditions=["Breast Cancer"],
        interventions=["Olaparib"],
        eligibility_criteria="HR-positive metastatic breast cancer",
        locations=["Slovakia"],
        sponsor="Test",
    )
    result = check_eligibility(trial, patient)
    assert any(f.rule == "BRCA_PARP" for f in result.flags)


def test_breast_eligibility_excludes_her2_targeted_for_her2_negative():
    """Trastuzumab trial must be excluded for HER2-negative patients."""
    from datetime import date

    from oncoteam.eligibility import check_eligibility
    from oncoteam.models import ClinicalTrial, PatientProfile

    patient = PatientProfile(
        patient_id="test_c50_her2neg",
        name="Test",
        diagnosis_code="C50.9",
        diagnosis_description="Test",
        tumor_site="Breast",
        diagnosis_date=date(2020, 1, 1),
        staging="IV",
        biomarkers={"HR": "positive", "HER2": "negative"},
        excluded_therapies={},
        treatment_regimen="CDK4/6 + AI",
        hospitals=[],
        treating_physician="",
        notes="",
    )
    trial = ClinicalTrial(
        nct_id="NCT88888888",
        title="Trastuzumab monotherapy",
        status="Recruiting",
        phase="III",
        conditions=["Breast Cancer"],
        interventions=["Trastuzumab"],
        eligibility_criteria="HER2-positive breast cancer",
        locations=["Slovakia"],
        sponsor="Test",
    )
    result = check_eligibility(trial, patient)
    assert result.eligible is False
    assert any(f.rule == "HER2_negative" for f in result.flags)


def test_assess_research_relevance_breast_not_colorectal():
    """For breast patient, KRAS-G12S reason strings must NOT leak."""
    from datetime import date

    from oncoteam.eligibility import assess_research_relevance
    from oncoteam.models import PatientProfile

    patient = PatientProfile(
        patient_id="test_c50_rel",
        name="Test",
        diagnosis_code="C50.9",
        diagnosis_description="Test",
        tumor_site="Breast",
        diagnosis_date=date(2020, 1, 1),
        staging="IV",
        biomarkers={"HR": "positive", "HER2": "negative"},
        excluded_therapies={},
        treatment_regimen="CDK4/6 + AI",
        hospitals=[],
        treating_physician="",
        notes="",
    )
    result = assess_research_relevance(
        "CDK4/6 inhibitor in HR-positive metastatic breast cancer",
        patient=patient,
    )
    assert result.score == "high"
    assert "KRAS" not in result.reason
    assert (
        "breast" in result.reason.lower()
        or "cdk" in result.reason.lower()
        or "hr+" in result.reason.lower()
    )
