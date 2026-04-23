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
        assert any(f.rule == "KRAS_anti_EGFR" for f in result.flags)

    def test_panitumumab_excluded(self):
        result = check_eligibility(_trial(["Panitumumab"]), PATIENT)
        assert not result.eligible

    def test_anti_egfr_in_eligibility_text(self):
        result = check_eligibility(
            _trial(["Drug X"], eligibility_criteria="Must be cetuximab-naive"),
            PATIENT,
        )
        assert any(f.rule == "KRAS_anti_EGFR" for f in result.flags)


class TestKRASG12C:
    def test_sotorasib_excluded(self):
        result = check_eligibility(_trial(["Sotorasib"]), PATIENT)
        assert not result.eligible
        assert any(f.rule == "KRAS_not_G12C" for f in result.flags)

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


class TestOncopanelAwareEligibility:
    """#398 — eligibility rules now respect patient biomarker specifics via
    structured oncopanel helpers (with flat-dict fallback). Regression tests
    pinning behavior for patients whose biomarker status diverges from q1b.
    """

    def _patient_with_oncopanel(self, **panel_kw):
        """Build a test patient carrying an oncopanel with given panel fields."""
        from datetime import date

        from oncoteam.models import Oncopanel

        default_panel = {
            "panel_id": "test_panel",
            "patient_id": "test",
            "report_date": date(2026, 1, 1),
            "variants": [],
            "cnvs": [],
            "msi_status": "MSS",
        }
        default_panel.update(panel_kw)
        return PatientProfile(
            patient_id="test",
            name="Test",
            diagnosis_code="C18.9",
            diagnosis_description="mCRC",
            tumor_site="colon",
            treatment_regimen="FOLFOX",
            oncopanel_history=[Oncopanel(**default_panel)],
        )

    def test_g12c_patient_eligible_for_sotorasib(self):
        """A KRAS G12C patient must NOT be excluded from G12C inhibitors —
        before #398 migration, the rule fired for everyone. Now it respects
        the patient's allele."""
        from oncoteam.models import OncopanelVariant

        g12c_patient = self._patient_with_oncopanel(
            variants=[
                OncopanelVariant(
                    gene="KRAS",
                    protein_short="G12C",
                    significance="pathogenic",
                )
            ],
        )
        result = check_eligibility(_trial(["Sotorasib"]), g12c_patient)
        # No KRAS_not_G12C exclusion for a G12C patient
        assert not any(f.rule == "KRAS_not_G12C" for f in result.flags)

    def test_kras_wt_patient_eligible_for_anti_egfr(self):
        """KRAS wild-type patient (oncopanel-confirmed) must NOT be excluded
        from anti-EGFR therapy — pre-#398, the rule fired for all patients
        regardless of KRAS status."""
        # KRAS WT = oncopanel with no pathogenic KRAS variant
        wt_patient = self._patient_with_oncopanel(variants=[])
        result = check_eligibility(_trial(["Cetuximab", "FOLFIRI"]), wt_patient)
        assert not any(f.rule == "KRAS_anti_EGFR" for f in result.flags)

    def test_msi_high_patient_eligible_for_checkpoint_mono(self):
        """MSI-H/dMMR patient must NOT be excluded from checkpoint monotherapy
        — this is exactly the class they're indicated for."""
        msi_h_patient = self._patient_with_oncopanel(msi_status="MSI-H", mmr_status="dMMR")
        result = check_eligibility(_trial(["Pembrolizumab"]), msi_h_patient)
        assert not any(f.rule == "pMMR_MSS_checkpoint_mono" for f in result.flags)

    def test_her2_positive_patient_eligible_for_trastuzumab(self):
        """HER2-positive patient (via CNV amplification) must NOT be excluded
        from HER2-targeted therapy."""
        from oncoteam.models import CopyNumberVariant

        her2_pos = self._patient_with_oncopanel(
            cnvs=[CopyNumberVariant(gene="ERBB2", alteration="amplification", copies=12)],
        )
        result = check_eligibility(_trial(["Trastuzumab"]), her2_pos)
        assert not any(f.rule == "HER2_negative" for f in result.flags)

    def test_braf_v600e_patient_eligible_for_encorafenib(self):
        """BRAF V600E patient must NOT be excluded from BRAF inhibitor — this
        is their indicated targeted therapy."""
        from oncoteam.models import OncopanelVariant

        v600e = self._patient_with_oncopanel(
            variants=[
                OncopanelVariant(
                    gene="BRAF",
                    protein_short="V600E",
                    significance="pathogenic",
                )
            ],
        )
        result = check_eligibility(_trial(["Encorafenib"]), v600e)
        assert not any(f.rule == "BRAF_wildtype" for f in result.flags)

    def test_q1b_behavior_unchanged(self):
        """Regression pin: for q1b (KRAS G12S / MSS / BRAF WT / HER2-neg) every
        existing exclusion still fires — migration didn't silently drop rules."""
        assert not check_eligibility(_trial(["Cetuximab"]), PATIENT).eligible  # KRAS mutant
        assert not check_eligibility(_trial(["Sotorasib"]), PATIENT).eligible  # not G12C
        assert not check_eligibility(_trial(["Pembrolizumab"]), PATIENT).eligible  # MSS
        assert not check_eligibility(_trial(["Trastuzumab"]), PATIENT).eligible  # HER2-neg
        assert not check_eligibility(_trial(["Encorafenib"]), PATIENT).eligible  # BRAF WT
