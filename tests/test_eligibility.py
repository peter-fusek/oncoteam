"""Tests for eligibility checker module."""

from __future__ import annotations

from oncoteam.eligibility import assess_research_relevance, check_eligibility
from oncoteam.models import ClinicalTrial, PatientProfile
from oncoteam.patient_context import PATIENT


def _trial(interventions: list[str], eligibility_criteria: str = "") -> ClinicalTrial:
    return ClinicalTrial(
        nct_id="NCT99999",
        title="Test Trial",
        status="RECRUITING",
        conditions=["Colorectal Cancer"],
        interventions=interventions,
        eligibility_criteria=eligibility_criteria,
    )


class TestAntiEGFR:
    def test_cetuximab_excluded(self):
        result = check_eligibility(_trial(["Cetuximab", "FOLFIRI"]), PATIENT)
        assert not result.eligible
        assert any(f.rule == "KRAS_G12S_anti_EGFR" for f in result.flags)

    def test_panitumumab_excluded(self):
        result = check_eligibility(_trial(["Panitumumab"]), PATIENT)
        assert not result.eligible

    def test_anti_egfr_in_eligibility_text(self):
        result = check_eligibility(
            _trial(["Drug X"], eligibility_criteria="Must be cetuximab-naive"),
            PATIENT,
        )
        assert any(f.rule == "KRAS_G12S_anti_EGFR" for f in result.flags)


class TestKRASG12C:
    def test_sotorasib_excluded(self):
        result = check_eligibility(_trial(["Sotorasib"]), PATIENT)
        assert not result.eligible
        assert any(f.rule == "KRAS_G12S_not_G12C" for f in result.flags)

    def test_adagrasib_excluded(self):
        result = check_eligibility(_trial(["Adagrasib"]), PATIENT)
        assert not result.eligible


class TestCheckpointInhibitors:
    def test_pembrolizumab_mono_excluded(self):
        result = check_eligibility(_trial(["Pembrolizumab"]), PATIENT)
        assert not result.eligible
        assert any(f.rule == "pMMR_MSS_checkpoint_mono" for f in result.flags)

    def test_checkpoint_plus_chemo_allowed(self):
        result = check_eligibility(_trial(["Pembrolizumab", "FOLFOX"]), PATIENT)
        # Should NOT be excluded — combination is acceptable
        excluded_flags = [f for f in result.flags if f.status == "excluded"]
        assert not any(f.rule == "pMMR_MSS_checkpoint_mono" for f in excluded_flags)
        assert len(result.warnings) > 0  # But should have a warning


class TestHER2:
    def test_trastuzumab_excluded(self):
        result = check_eligibility(_trial(["Trastuzumab"]), PATIENT)
        assert not result.eligible
        assert any(f.rule == "HER2_negative" for f in result.flags)


class TestBRAF:
    def test_encorafenib_excluded(self):
        result = check_eligibility(_trial(["Encorafenib"]), PATIENT)
        assert not result.eligible
        assert any(f.rule == "BRAF_wildtype" for f in result.flags)


class TestBevacizumabVTE:
    def test_bevacizumab_warning(self):
        result = check_eligibility(_trial(["Bevacizumab", "FOLFOX"]), PATIENT)
        # Should be eligible but with warnings (VTE is warning, not exclusion)
        assert any(f.rule == "VTE_bevacizumab" and f.status == "warning" for f in result.flags)
        assert len(result.warnings) > 0

    def test_bevacizumab_no_vte_no_warning(self):
        patient_no_vte = PatientProfile(
            name="Test",
            diagnosis_code="C18.7",
            diagnosis_description="CRC",
            tumor_site="Colon",
            treatment_regimen="FOLFOX",
            comorbidities=[],
        )
        result = check_eligibility(_trial(["Bevacizumab"]), patient_no_vte)
        assert not any(f.rule == "VTE_bevacizumab" for f in result.flags)


class TestCleanTrial:
    def test_no_flags_when_clean(self):
        result = check_eligibility(_trial(["FOLFOX"]), PATIENT)
        assert result.eligible
        assert result.flags == []
        assert result.warnings == []
        assert "No biomarker contraindications" in result.summary

    def test_multiple_exclusions(self):
        result = check_eligibility(
            _trial(["Cetuximab", "Sotorasib", "Trastuzumab"]),
            PATIENT,
        )
        assert not result.eligible
        assert len([f for f in result.flags if f.status == "excluded"]) == 3


class TestResearchRelevance:
    """Tests for assess_research_relevance()."""

    def test_anti_egfr_not_applicable(self):
        rel = assess_research_relevance("Cetuximab in wild-type KRAS mCRC")
        assert rel.score == "not_applicable"
        assert "KRAS" in rel.reason

    def test_panitumumab_not_applicable(self):
        rel = assess_research_relevance("Panitumumab plus FOLFIRI")
        assert rel.score == "not_applicable"

    def test_g12c_inhibitor_not_applicable(self):
        rel = assess_research_relevance("Sotorasib in KRAS G12C CRC")
        assert rel.score == "not_applicable"
        assert "G12C" in rel.reason

    def test_adagrasib_not_applicable(self):
        rel = assess_research_relevance("Adagrasib phase 2 trial")
        assert rel.score == "not_applicable"

    def test_her2_targeted_not_applicable(self):
        rel = assess_research_relevance("Trastuzumab deruxtecan in CRC")
        assert rel.score == "not_applicable"
        assert "HER2" in rel.reason

    def test_kras_g12s_high(self):
        rel = assess_research_relevance("KRAS G12S mutation in colorectal")
        assert rel.score == "high"

    def test_kras_mutant_high(self):
        rel = assess_research_relevance("KRAS mutant mCRC treatment options")
        assert rel.score == "high"

    def test_folfox_mcrc_high(self):
        rel = assess_research_relevance("FOLFOX in metastatic colorectal cancer")
        assert rel.score == "high"

    def test_pan_kras_high(self):
        rel = assess_research_relevance("Pan-KRAS inhibitor RMC-6236 trial")
        assert rel.score == "high"

    def test_colorectal_medium(self):
        rel = assess_research_relevance("New biomarkers in colorectal cancer")
        assert rel.score == "medium"

    def test_liver_metastasis_medium(self):
        rel = assess_research_relevance("Liver metastasis management")
        assert rel.score == "medium"

    def test_unrelated_low(self):
        rel = assess_research_relevance("Immunotherapy in melanoma")
        assert rel.score == "low"

    def test_general_oncology_low(self):
        rel = assess_research_relevance("General oncology review 2026")
        assert rel.score == "low"

    def test_summary_used_for_scoring(self):
        """Summary text is included in relevance assessment."""
        rel = assess_research_relevance(
            "Phase 2 study",
            summary="FOLFOX in mCRC patients",
        )
        assert rel.score == "high"

    def test_checkpoint_mss_mono_not_applicable(self):
        rel = assess_research_relevance("Pembrolizumab monotherapy in MSS colorectal cancer")
        assert rel.score == "not_applicable"

    def test_checkpoint_combo_not_flagged(self):
        """Checkpoint + chemo combination should not be not_applicable."""
        rel = assess_research_relevance("Pembrolizumab plus FOLFOX in colorectal cancer")
        assert rel.score != "not_applicable"
