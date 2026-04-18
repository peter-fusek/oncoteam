"""Tests for #398 structured oncopanel — models, helpers, q1b seed."""

from __future__ import annotations

from datetime import date

import pytest

from oncoteam.eligibility import (
    count_pathogenic_variants,
    get_latest_oncopanel,
    get_variants_for_gene,
    is_biallelic_loss,
    is_ddr_deficient,
)
from oncoteam.models import (
    CopyNumberVariant,
    Oncopanel,
    OncopanelVariant,
    PatientProfile,
)


def _profile(oncopanels: list[Oncopanel] | None = None) -> PatientProfile:
    return PatientProfile(
        patient_id="test",
        name="Test",
        diagnosis_code="C18.7",
        diagnosis_description="test",
        tumor_site="sigmoid",
        treatment_regimen="FOLFOX",
        oncopanel_history=oncopanels or [],
    )


def _variant(gene: str, **kw) -> OncopanelVariant:
    defaults = {
        "gene": gene,
        "variant_type": "SNV",
        "significance": "likely_pathogenic",
        "classification": "somatic",
    }
    defaults.update(kw)
    return OncopanelVariant(**defaults)


def _panel(panel_id: str, report_date: date, variants: list[OncopanelVariant]) -> Oncopanel:
    return Oncopanel(
        panel_id=panel_id,
        patient_id="test",
        report_date=report_date,
        variants=variants,
        msi_status="MSS",
        tmb_category="low",
    )


class TestOncopanelVariantModel:
    def test_minimal_variant(self):
        v = OncopanelVariant(gene="KRAS")
        assert v.gene == "KRAS"
        assert v.variant_type == "SNV"  # default
        assert v.significance == "unknown"  # default
        assert v.vaf is None
        assert v.reviewed_status == "unreviewed"

    def test_full_variant(self):
        v = OncopanelVariant(
            gene="KRAS",
            ref_seq="NM_033360.4",
            hgvs_cdna="c.34G>A",
            hgvs_protein="p.(Gly12Ser)",
            protein_short="G12S",
            vaf=0.1281,
            tier="IA",
            variant_type="SNV",
            significance="pathogenic",
        )
        assert v.vaf == pytest.approx(0.1281)
        assert v.tier == "IA"

    def test_significance_enum(self):
        with pytest.raises(ValueError):
            OncopanelVariant(gene="KRAS", significance="maybe_bad")  # invalid literal


class TestCopyNumberVariantModel:
    def test_amp(self):
        c = CopyNumberVariant(gene="HER2", alteration="amplification", copies=8)
        assert c.gene == "HER2"
        assert c.alteration == "amplification"

    def test_invalid_alteration(self):
        with pytest.raises(ValueError):
            CopyNumberVariant(gene="HER2", alteration="upregulation")


class TestOncopanelModel:
    def test_minimal_panel(self):
        p = Oncopanel(panel_id="p1", patient_id="test")
        assert p.msi_status == "unknown"  # default
        assert p.variants == []
        assert p.cnvs == []

    def test_panel_with_variants(self):
        p = _panel("p1", date(2026, 4, 18), [_variant("KRAS", significance="pathogenic")])
        assert len(p.variants) == 1
        assert p.variants[0].gene == "KRAS"


class TestGetLatestOncopanel:
    def test_none_when_empty(self):
        patient = _profile()
        assert get_latest_oncopanel(patient) is None

    def test_single_panel(self):
        panel = _panel("p1", date(2026, 4, 18), [])
        patient = _profile([panel])
        assert get_latest_oncopanel(patient) is panel

    def test_picks_most_recent_by_report_date(self):
        older = _panel("p1", date(2025, 12, 1), [])
        newer = _panel("p2", date(2026, 4, 18), [])
        # Insert in wrong order — function must sort by date
        patient = _profile([newer, older])
        assert get_latest_oncopanel(patient).panel_id == "p2"

    def test_missing_report_date_treated_as_min(self):
        no_date = _panel("nodate", date(2025, 1, 1), [])
        no_date.report_date = None
        dated = _panel("dated", date(2026, 4, 18), [])
        patient = _profile([no_date, dated])
        # Dated panel wins over one without a report_date
        assert get_latest_oncopanel(patient).panel_id == "dated"


class TestGetVariantsForGene:
    def test_empty_when_no_panel(self):
        patient = _profile()
        assert get_variants_for_gene(patient, "KRAS") == []

    def test_case_insensitive(self):
        panel = _panel("p1", date(2026, 4, 18), [_variant("KRAS")])
        patient = _profile([panel])
        assert len(get_variants_for_gene(patient, "kras")) == 1

    def test_multiple_variants_same_gene(self):
        panel = _panel(
            "p1",
            date(2026, 4, 18),
            [
                _variant("ATM", hgvs_cdna="c.73-2A>G"),
                _variant("ATM", hgvs_cdna="c.8278dup"),
            ],
        )
        patient = _profile([panel])
        variants = get_variants_for_gene(patient, "ATM")
        assert len(variants) == 2

    def test_only_latest_panel_queried(self):
        old = _panel("old", date(2025, 1, 1), [_variant("KRAS")])
        new = _panel("new", date(2026, 4, 18), [])
        patient = _profile([old, new])
        # Latest panel has no KRAS — stale panel is ignored
        assert get_variants_for_gene(patient, "KRAS") == []


class TestCountPathogenicVariants:
    def test_only_pathogenic_counted(self):
        panel = _panel(
            "p1",
            date(2026, 4, 18),
            [
                _variant("ATM", significance="pathogenic"),
                _variant("ATM", significance="likely_pathogenic"),
                _variant("ATM", significance="vus"),  # excluded
                _variant("ATM", significance="benign"),  # excluded
            ],
        )
        patient = _profile([panel])
        assert count_pathogenic_variants(patient, "ATM") == 2

    def test_zero_when_no_panel(self):
        assert count_pathogenic_variants(_profile(), "ATM") == 0


class TestIsBiallelicLoss:
    def test_true_for_two_pathogenic(self):
        panel = _panel(
            "p1",
            date(2026, 4, 18),
            [
                _variant("ATM", significance="likely_pathogenic"),
                _variant("ATM", significance="pathogenic"),
            ],
        )
        assert is_biallelic_loss(_profile([panel]), "ATM")

    def test_false_for_single_pathogenic(self):
        panel = _panel("p1", date(2026, 4, 18), [_variant("ATM", significance="likely_pathogenic")])
        assert not is_biallelic_loss(_profile([panel]), "ATM")

    def test_false_for_no_panel(self):
        assert not is_biallelic_loss(_profile(), "ATM")


class TestIsDDRDeficient:
    def test_true_for_atm_biallelic(self):
        panel = _panel(
            "p1",
            date(2026, 4, 18),
            [
                _variant("ATM", significance="likely_pathogenic"),
                _variant("ATM", significance="pathogenic"),
            ],
        )
        assert is_ddr_deficient(_profile([panel]))

    def test_true_for_brca1_biallelic(self):
        panel = _panel(
            "p1",
            date(2026, 4, 18),
            [
                _variant("BRCA1", significance="pathogenic"),
                _variant("BRCA1", significance="likely_pathogenic"),
            ],
        )
        assert is_ddr_deficient(_profile([panel]))

    def test_false_for_single_atm_hit(self):
        panel = _panel("p1", date(2026, 4, 18), [_variant("ATM", significance="likely_pathogenic")])
        assert not is_ddr_deficient(_profile([panel]))

    def test_false_for_kras_only(self):
        # KRAS mutation alone is not DDR deficient
        panel = _panel("p1", date(2026, 4, 18), [_variant("KRAS", significance="pathogenic")])
        assert not is_ddr_deficient(_profile([panel]))

    def test_false_for_tp53_only(self):
        # TP53 alone is not in our DDR core gene list (by design — TP53 is a
        # separate mechanism from HRD-like synthetic-lethality with PARPi)
        panel = _panel(
            "p1",
            date(2026, 4, 18),
            [
                _variant("TP53", significance="pathogenic"),
                _variant("TP53", significance="likely_pathogenic"),
            ],
        )
        assert not is_ddr_deficient(_profile([panel]))

    def test_false_for_no_panel(self):
        assert not is_ddr_deficient(_profile())


class TestQ1bOncopanelSeed:
    """Regression: q1b ships with the real 2026-04-18 oncopanel data."""

    def test_q1b_has_oncopanel(self):
        from oncoteam.patient_context import PATIENT

        assert len(PATIENT.oncopanel_history) >= 1

    def test_q1b_latest_is_2026_04_18(self):
        from oncoteam.patient_context import PATIENT

        latest = get_latest_oncopanel(PATIENT)
        assert latest is not None
        assert latest.panel_id == "q1b_oncopanel_2026-04-18"
        assert latest.report_date == date(2026, 4, 18)

    def test_q1b_has_kras_g12s_ia(self):
        from oncoteam.patient_context import PATIENT

        kras = get_variants_for_gene(PATIENT, "KRAS")
        assert len(kras) == 1
        assert kras[0].protein_short == "G12S"
        assert kras[0].tier == "IA"
        assert kras[0].vaf == pytest.approx(0.1281)

    def test_q1b_has_atm_biallelic(self):
        from oncoteam.patient_context import PATIENT

        atm = get_variants_for_gene(PATIENT, "ATM")
        assert len(atm) == 2
        assert is_biallelic_loss(PATIENT, "ATM")

    def test_q1b_has_tp53_splice(self):
        from oncoteam.patient_context import PATIENT

        tp53 = get_variants_for_gene(PATIENT, "TP53")
        assert len(tp53) == 1
        assert tp53[0].variant_type == "splice"

    def test_q1b_is_mss_and_tmb_low(self):
        from oncoteam.patient_context import PATIENT

        latest = get_latest_oncopanel(PATIENT)
        assert latest.msi_status == "MSS"
        assert latest.mmr_status == "pMMR"
        assert latest.tmb_category == "low"
        assert latest.tmb_score == pytest.approx(6.67)

    def test_q1b_is_ddr_deficient(self):
        """The whole point of #398 + #392: this predicate drives DDR pivot."""
        from oncoteam.patient_context import PATIENT

        assert is_ddr_deficient(PATIENT)

    def test_e5g_is_not_ddr_deficient(self):
        """General-health patient has no oncopanel — predicate safely returns False."""
        from oncoteam.patient_context import PATIENT_E5G

        assert not is_ddr_deficient(PATIENT_E5G)

    def test_sgu_is_not_ddr_deficient(self):
        """Breast-cancer patient with no oncopanel in profile — False."""
        from oncoteam.patient_context import PATIENT_SGU

        assert not is_ddr_deficient(PATIENT_SGU)
