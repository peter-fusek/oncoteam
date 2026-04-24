from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from datetime import date

from . import oncofiles_client
from .activity_logger import record_suppressed_error
from .locale import L, resolve
from .models import (
    EnrollmentPreference,
    HomeRegion,
    Oncopanel,
    OncopanelVariant,
    PatientProfile,
)

# ── Default home region for SK patients ─────────────────────────────────
# Most current patients (q1b, e5g, sgu) live in Bratislava. New patients
# should set their own HomeRegion; the default below is a convenience for
# existing seeded patients. See issue #394.

_BRATISLAVA_HOME = HomeRegion(
    city="Bratislava",
    country="SK",
    lat=48.1486,
    lon=17.1077,
    healthcare_system="VšZP (Slovak national)",
)

_BRATISLAVA_ENROLLMENT = EnrollmentPreference(
    max_travel_km=600,
    preferred_countries=["SK", "CZ", "AT", "HU", "PL", "DE", "CH"],
    language_preferences=["sk", "cs", "en"],
    excluded_countries=[],
    allow_unique_opportunity_global=False,
)

# Erika q1b oncopanel from 2026-04-18 somatic NGS (#398).
# Source: NOÚ Bratislava genetics report. Four tier IA/IIC variants + MSS +
# TMB-low. The ATM biallelic loss unlocks PARPi/ATRi eligibility (#392).
# Physician verification fields will be populated when MUDr. Mináriková
# reviews per #395/#396. Source document ID TBD — awaits document_pipeline
# extraction per #398 scope item #8.
_ERIKA_ONCOPANEL_2026_04_18 = Oncopanel(
    panel_id="q1b_oncopanel_2026-04-18",
    patient_id="q1b",
    sample_date=None,  # TBC from document header
    report_date=date(2026, 4, 18),
    lab="OUSA — Ústav sv. Alžbety",
    sample_type="tumor_tissue",
    methodology="NGS",  # TBC — likely TruSight-500 or similar
    source_document_id="278",
    variants=[
        OncopanelVariant(
            gene="KRAS",
            ref_seq="NM_033360.4",
            hgvs_cdna="c.34G>A",
            hgvs_protein="p.(Gly12Ser)",
            protein_short="G12S",
            vaf=0.1281,
            variant_type="SNV",
            tier="IA",
            classification="somatic",
            significance="pathogenic",
        ),
        OncopanelVariant(
            gene="ATM",
            ref_seq="NM_000051.4",
            hgvs_cdna="c.73-2A>G",
            hgvs_protein="p.(?)",
            protein_short="p.(?)",
            vaf=0.1722,
            variant_type="splice",
            tier="IIC",
            classification="somatic",
            significance="likely_pathogenic",
        ),
        OncopanelVariant(
            gene="ATM",
            ref_seq="NM_000051.4",
            hgvs_cdna="c.8278dup",
            hgvs_protein="p.(Leu2760Profs*9)",
            protein_short="L2760Pfs*9",
            vaf=0.1542,
            variant_type="frameshift",
            tier="IIC",
            classification="somatic",
            significance="likely_pathogenic",
        ),
        OncopanelVariant(
            gene="TP53",
            ref_seq="NM_000546.6",
            hgvs_cdna="c.559+1G>T",
            hgvs_protein="p.(?)",
            protein_short="p.(?)",
            vaf=0.2573,
            variant_type="splice",
            tier="IIC",
            classification="somatic",
            significance="likely_pathogenic",
        ),
    ],
    cnvs=[],
    msi_status="MSS",
    mmr_status="pMMR",
    tmb_score=6.67,
    tmb_category="low",
)

# ── Recipient Registry ────────────────────────────
# WhatsApp message recipients with role-aware formatting.


@dataclass(frozen=True)
class Recipient:
    """A WhatsApp message recipient with role and language preference."""

    name: str
    role: str  # "patient", "caregiver", "physician"
    phone: str
    language: str = "sk"  # ISO 639-1


# Pre-populated care team for current patient.
RECIPIENTS: dict[str, Recipient] = {
    "caregiver": Recipient(
        name="Peter",
        role="caregiver",
        phone=os.environ.get("WHATSAPP_CAREGIVER_PHONE", ""),
        language="sk",
    ),
    "physician": Recipient(
        name="MUDr. [Physician]",
        role="physician",
        phone="",  # not used — physician gets dashboard only
        language="sk",
    ),
}

# Default recipient for all agent WhatsApp messages.
DEFAULT_RECIPIENT = RECIPIENTS["caregiver"]


def format_whatsapp_header(
    title: str,
    recipient: Recipient | None = None,
    date_str: str = "",
    patient_name: str = "",
) -> str:
    """Format a standardized WhatsApp message header.

    Returns lines like:
        *Pre-cycle check (cyklus 3)* — Erika
        Pre: Peter (opatrovateľ)
        Dátum: 2026-03-23
    """
    r = recipient or DEFAULT_RECIPIENT
    role_labels = {
        "caregiver": "opatrovateľ" if r.language == "sk" else "caregiver",
        "physician": "lekár" if r.language == "sk" else "physician",
        "patient": "pacient" if r.language == "sk" else "patient",
    }
    title_line = f"*{title}*" if not patient_name else f"*{title}* \u2014 {patient_name}"
    lines = [title_line]
    lines.append(f"Pre: {r.name} ({role_labels.get(r.role, r.role)})")
    if date_str:
        lines.append(f"Dátum: {date_str}")
    lines.append("")  # blank line before content
    return "\n".join(lines)


# Therapy type categories for display grouping and badges
THERAPY_CATEGORIES: dict[str, dict] = {
    "chemo": {"label": "Chemoterapia", "label_en": "Chemotherapy", "color": "#e53e3e"},
    "targeted": {"label": "Cielená terapia", "label_en": "Targeted therapy", "color": "#dd6b20"},
    "immuno": {"label": "Imunoterapia", "label_en": "Immunotherapy", "color": "#805ad5"},
    "supportive": {"label": "Podporná liečba", "label_en": "Supportive care", "color": "#3182ce"},
    "surgery": {"label": "Chirurgia", "label_en": "Surgery", "color": "#2f855a"},
    "anticoagulation": {
        "label": "Antikoagulácia",
        "label_en": "Anticoagulation",
        "color": "#d69e2e",
    },
}


PATIENT = PatientProfile(
    patient_id="q1b",
    name="Erika F.",
    diagnosis_code="C18.7",
    diagnosis_description="AdenoCa colon sigmoideum, G3, mCRC",
    tumor_site="Sigmoid colon",
    diagnosis_date=date(2025, 12, 1),
    biomarkers={
        "KRAS": "mutant G12S (c.34G>A)",
        "KRAS_G12C": False,
        "NRAS": "wild-type",
        "BRAF_V600E": "wild-type",
        "HER2": "negative (ratio 1.3, copy number 3)",
        "MSI": "pMMR / MSS",
        "anti_EGFR_eligible": False,
        "anti_EGFR_reason": "KRAS G12S mutation",
    },
    treatment_regimen="mFOLFOX6 90%",
    hospitals=["NOU (Národný onkologický ústav)", "Nemocnica Bory"],
    notes="Left-sided mCRC. 1L mFOLFOX6 90% dose. Active VJI thrombosis on Clexane.",
    staging="IV",
    histology="Adenocarcinoma Grade 3",
    tumor_laterality="left-sided",
    metastases=[
        "liver (C78.7)",
        "peritoneum (C78.6)",
        "retroperitoneum",
        "Krukenberg (ovary l.dx., C79.6)",
        "mediastinal LN",
        "hilar LN",
        "retrocrural LN",
        "portal LN (C77.8)",
        "pulmonary nodules (<=5mm, monitor)",
    ],
    comorbidities=["VJI thrombosis (active, Clexane 0.6ml SC 2x/day)"],
    surgeries=[
        {
            "date": "2026-01-18",
            "institution": "Nemocnica Bory",
            "type": "palliative resection",
            "result": "AdenoCa G3",
        }
    ],
    # Treating oncologist (reviewing/onboarding 2026-04-18) — confirmed via NOÚ
    # stamp. Display-name used; ID codes live in secure context, not profile.
    treating_physician="MUDr. Mgr. Zuzana Mináriková, PhD. — klinický onkológ, NOÚ Bratislava",
    admitting_physician="NOÚ Bratislava (admitting clinician TBC)",
    baseline_weight_kg=72.0,
    current_cycle=3,
    ecog="unknown — ask at next onco session",
    excluded_therapies={
        "anti-EGFR (cetuximab, panitumumab)": "KRAS G12S mutation",
        "checkpoint monotherapy (pembrolizumab, nivolumab)": "pMMR/MSS",
        "HER2-targeted (trastuzumab, pertuzumab)": "HER2 negative",
        "BRAF inhibitors (encorafenib)": "BRAF wild-type",
        "KRAS G12C-specific (sotorasib, adagrasib)": "patient has G12S, not G12C",
    },
    patient_ids={
        "rodne_cislo": "",  # loaded from oncofiles patient_context at runtime
        "nou_id": "X98 10496",
        "poistovna": "25",
    },
    active_therapies=[
        {
            "name": "mFOLFOX6 90%",
            "category": "chemo",
            "drugs": [
                {
                    "name": "Oxaliplatin",
                    "dose": "76.5 mg/m²",
                    "lay": "Platinový liek, ktorý poškodzuje DNA nádorových buniek",
                    "medical": "3rd-gen platinum analog; forms inter/intra-strand DNA crosslinks",
                },
                {
                    "name": "Leucovorin (calcium folinate)",
                    "dose": "400 mg/m²",
                    "lay": "Vitamín, ktorý zosilňuje účinok 5-FU",
                    "medical": "Reduced folate; potentiates 5-FU by stabilizing FdUMP-TS complex",
                },
                {
                    "name": "5-Fluorouracil (5-FU)",
                    "dose": "400 mg/m² bolus + 2400 mg/m² 46h infúzia",
                    "lay": "Antimetabolit, ktorý bráni deleniu nádorových buniek",
                    "medical": "Fluoropyrimidine antimetabolite; inhibits thymidylate synthase",
                },
            ],
            "status": "active",
            "cycle": 3,
        },
        {
            "name": "Clexane (enoxaparin)",
            "category": "anticoagulation",
            "drugs": [
                {
                    "name": "Enoxaparin",
                    "dose": "0.6 ml SC 2x/deň",
                    "lay": "Riedenie krvi — prevencia zhoršenia krvnej zrazeniny v žile",
                    "medical": "LMWH anticoagulation for active VJI thrombosis",
                },
            ],
            "status": "active",
            "indication": "VJI thrombosis",
        },
        {
            "name": "Bevacizumab",
            "category": "targeted",
            "drugs": [
                {
                    "name": "Bevacizumab",
                    "dose": "5 mg/kg q2w",
                    "lay": (
                        "Protilátka blokujúca rast ciev nádoru — VYSOKÉ RIZIKO pre aktívnu trombózu"
                    ),
                    "medical": "Anti-VEGF mAb; HIGH RISK due to active VJI thrombosis + Clexane",
                },
            ],
            "status": "planned",
            "warning": "HIGH RISK — requires explicit oncologist discussion due to active VTE",
        },
    ],
    home_region=_BRATISLAVA_HOME,
    enrollment_preference=_BRATISLAVA_ENROLLMENT,
    oncopanel_history=[_ERIKA_ONCOPANEL_2026_04_18],
    # #391 — q1b is the only actively-treated patient; admin (Peter) receives
    # WhatsApp notifications for her scheduled agent runs. e5g / sgu stay on
    # the default "silent" policy until explicitly flipped.
    notification_policy="admin",
)

# ── Second patient: general health management ──────────────────────────────
PATIENT_E5G = PatientProfile(
    patient_id="e5g",
    name="Peter F.",
    diagnosis_code="Z00.0",  # ICD-10: General adult health check
    diagnosis_description="General health management — preventive care",
    tumor_site="",
    treatment_regimen="",
    hospitals=["Poliklinika Tehelná, Bratislava"],
    treating_physician="MUDr. [GP Physician] — všeobecný lekár",
    notes="Non-oncology patient. Preventive care, periodic screenings, health agenda.",
    biomarkers={},
    excluded_therapies={},
    agent_whitelist=["document_pipeline", "lab_sync", "keepalive_ping", "weekly_briefing"],
    paused=True,  # Non-oncology; paused for cost reduction (Sprint 92). Resume by flipping.
    home_region=_BRATISLAVA_HOME,
    enrollment_preference=_BRATISLAVA_ENROLLMENT,
)

# ── Third patient: oncology — breast cancer ──────────────────────────────
PATIENT_SGU = PatientProfile(
    patient_id="sgu",
    name="Nora A.",
    diagnosis_code="C50.9",  # ICD-10: Breast, unspecified
    diagnosis_description="Metastatic breast carcinoma — invasive ductal, HR+/HER2-negative",
    tumor_site="Left breast",
    diagnosis_date=date(2019, 1, 1),
    staging="Stage IIB (initial), currently metastatic (skeletal)",
    biomarkers={
        "HR": "positive",
        "ER": "positive",
        "PR": "positive",
        "HER2": "negative",
        "Ki-67": "unknown — ask at next onco session",
        "BRCA1": "unknown",
        "BRCA2": "unknown",
    },
    excluded_therapies={
        "anti-HER2 (trastuzumab, pertuzumab)": "HER2 negative",
    },
    treatment_regimen="1st line palliative hormone therapy",
    hospitals=[],
    treating_physician="",
    notes="Metastatic breast cancer with skeletal metastases under palliative hormone therapy.",
    metastases=["Skeletal (Th7 — pathological fracture, stabilization + RFA + kyphoplasty)"],
    comorbidities=[],
    active_therapies=[
        {
            "name": "Hormone + CDK4/6 therapy",
            "category": "hormonal",
            "drugs": [
                {"name": "Zoladex (goserelin)", "dose": "3.6mg", "lay": "Hormone suppression"},
                {"name": "Letrozole", "dose": "", "lay": "Aromatase inhibitor"},
                {"name": "Kisqali (ribociclib)", "dose": "200mg", "lay": "CDK4/6 inhibitor"},
                {"name": "Denosumab", "dose": "", "lay": "Bone-strengthening antibody"},
            ],
        },
    ],
    agent_whitelist=[
        "document_pipeline",
        "lab_sync",
        "keepalive_ping",
        "weekly_briefing",
        "daily_research",
        "trial_monitor",
    ],
    paused=True,  # Not under active treatment review; paused for cost reduction (Sprint 92).
    home_region=_BRATISLAVA_HOME,
    enrollment_preference=_BRATISLAVA_ENROLLMENT,
)


# ── Bilingual overlay for dashboard display ──────────────────────────────
# Keys match PATIENT fields. Values are L(sk, en) bilingual dicts.
# Fields not listed here are displayed as-is (e.g. name, diagnosis_code).

_PATIENT_L10N: dict = {
    "tumor_site": L("Sigmoideum (hrubé črevo)", "Sigmoid colon"),
    "histology": L("Adenokarcinóm G3", "Adenocarcinoma Grade 3"),
    "tumor_laterality": L("ľavostranný", "left-sided"),
    "staging": L(
        "IV (metastázy pečene, peritoneálna karcinomatóza, LU, Krukenbergov tumor l.dx.)",
        "IV (liver mets, peritoneal carcinomatosis, LN, Krukenberg tumor l.dx.)",
    ),
    "ecog": L("neznámy — spýtať sa na ďalšej onko vizite", "unknown — ask at next onco session"),
    "notes": L(
        "Ľavostranný mCRC. 1L mFOLFOX6 90% dávka. Aktívna VJI trombóza na Clexane.",
        "Left-sided mCRC. 1L mFOLFOX6 90% dose. Active VJI thrombosis on Clexane.",
    ),
    "metastases": [
        L("pečeň (C78.7)", "liver (C78.7)"),
        L("pobrušnica (C78.6)", "peritoneum (C78.6)"),
        L("retroperitoneum", "retroperitoneum"),
        L("Krukenbergov tumor (vaječník l.dx., C79.6)", "Krukenberg (ovary l.dx., C79.6)"),
        L("mediastinálne LU", "mediastinal LN"),
        L("hilové LU", "hilar LN"),
        L("retrokrurálne LU", "retrocrural LN"),
        L("portálne LU (C77.8)", "portal LN (C77.8)"),
        L("pľúcne uzlíky (<=5mm, sledovanie)", "pulmonary nodules (<=5mm, monitor)"),
    ],
    "comorbidities": [
        L(
            "VJI trombóza (aktívna, Clexane 0,6ml SC 2x/deň)",
            "VJI thrombosis (active, Clexane 0.6ml SC 2x/day)",
        ),
    ],
    "excluded_therapies": [
        {
            "therapy": L(
                "anti-EGFR (cetuximab, panitumumab)", "anti-EGFR (cetuximab, panitumumab)"
            ),
            "reason": L("KRAS G12S mutácia", "KRAS G12S mutation"),
        },
        {
            "therapy": L(
                "checkpoint monoterapia (pembrolizumab, nivolumab)",
                "checkpoint monotherapy (pembrolizumab, nivolumab)",
            ),
            "reason": L("pMMR/MSS", "pMMR/MSS"),
        },
        {
            "therapy": L(
                "HER2-cielená terapia (trastuzumab, pertuzumab)",
                "HER2-targeted (trastuzumab, pertuzumab)",
            ),
            "reason": L("HER2 negatívny", "HER2 negative"),
        },
        {
            "therapy": L("BRAF inhibítory (encorafenib)", "BRAF inhibitors (encorafenib)"),
            "reason": L("BRAF wild-type", "BRAF wild-type"),
        },
        {
            "therapy": L(
                "KRAS G12C-špecifické (sotorasib, adagrasib)",
                "KRAS G12C-specific (sotorasib, adagrasib)",
            ),
            "reason": L("pacient má G12S, nie G12C", "patient has G12S, not G12C"),
        },
    ],
    "biomarker_annotations": {
        "KRAS": L("Riadiaca mutácia liečby", "Treatment driver mutation"),
        "MSI": L("Marker eligibility imunoterapie", "Immunotherapy eligibility marker"),
    },
    # patient_ids values are IDs, not translatable — labels come from frontend i18n
    "active_therapies": [
        {
            "name": "mFOLFOX6 90%",
            "category": "chemo",
            "drugs": [
                {
                    "name": "Oxaliplatin",
                    "dose": "76.5 mg/m²",
                    "lay": L(
                        "Platinový liek, ktorý poškodzuje DNA nádorových buniek",
                        "Platinum drug that damages cancer cell DNA",
                    ),
                    "medical": L(
                        "Platinový analóg 3. generácie; tvorí inter/intra-reťazcové"
                        " DNA krížové väzby",
                        "3rd-gen platinum analog; forms inter/intra-strand DNA crosslinks",
                    ),
                },
                {
                    "name": "Leucovorin",
                    "dose": "400 mg/m²",
                    "lay": L(
                        "Vitamín, ktorý zosilňuje účinok 5-FU",
                        "Vitamin that enhances 5-FU effect",
                    ),
                    "medical": L(
                        "Redukovaný folát; zosilňuje 5-FU stabilizáciou komplexu FdUMP-TS",
                        "Reduced folate; potentiates 5-FU by stabilizing FdUMP-TS complex",
                    ),
                },
                {
                    "name": "5-Fluorouracil (5-FU)",
                    "dose": L(
                        "400 mg/m² bolus + 2400 mg/m² 46h infúzia",
                        "400 mg/m² bolus + 2400 mg/m² 46h infusion",
                    ),
                    "lay": L(
                        "Antimetabolit, ktorý bráni deleniu nádorových buniek",
                        "Antimetabolite that prevents cancer cell division",
                    ),
                    "medical": L(
                        "Fluoropyrimidínový antimetabolit; inhibuje tymidylátsyntetázu",
                        "Fluoropyrimidine antimetabolite; inhibits thymidylate synthase",
                    ),
                },
            ],
            "status": L("aktívna", "active"),
        },
        {
            "name": L("Clexane (enoxaparín)", "Clexane (enoxaparin)"),
            "category": "anticoagulation",
            "drugs": [
                {
                    "name": L("Enoxaparín", "Enoxaparin"),
                    "dose": "0.6 ml SC 2x/deň",
                    "lay": L(
                        "Riedenie krvi — prevencia zhoršenia krvnej zrazeniny v žile",
                        "Blood thinner — prevents worsening of the blood clot in the vein",
                    ),
                    "medical": L(
                        "LMWH antikoagulácia pre aktívnu VJI trombózu",
                        "LMWH anticoagulation for active VJI thrombosis",
                    ),
                },
            ],
            "status": L("aktívna", "active"),
            "indication": L("VJI trombóza", "VJI thrombosis"),
        },
        {
            "name": "Bevacizumab",
            "category": "targeted",
            "drugs": [
                {
                    "name": "Bevacizumab",
                    "dose": "5 mg/kg q2w",
                    "lay": L(
                        "Protilátka blokujúca rast ciev nádoru — VYSOKÉ RIZIKO",
                        "Antibody blocking tumor blood vessel growth — HIGH RISK",
                    ),
                    "medical": L(
                        "Anti-VEGF mAb; VYSOKÉ RIZIKO kvôli aktívnej VJI trombóze + Clexane",
                        "Anti-VEGF mAb; HIGH RISK due to active VJI thrombosis + Clexane",
                    ),
                },
            ],
            "status": L("plánovaná", "planned"),
            "warning": L(
                "VYSOKÉ RIZIKO — vyžaduje výslovný súhlas onkológa kvôli aktívnej VTE",
                "HIGH RISK — requires explicit oncologist discussion due to active VTE",
            ),
        },
    ],
    "surgeries": [
        {
            "date": "2026-01-18",
            "institution": "Nemocnica Bory",
            "type": L("paliatívna resekcia", "palliative resection"),
            "result": "AdenoCa G3",
        }
    ],
}


def get_patient_localized(lang: str = "sk", patient_id: str = "q1b") -> dict:
    """Return patient profile dict with bilingual fields resolved to requested language."""
    patient = get_patient(patient_id)
    # mode="json" serializes all date/datetime fields (including nested
    # oncopanel_history per #398) to ISO strings. Replaces the prior
    # single-field diagnosis_date str() conversion.
    data = patient.model_dump(mode="json")

    # Overlay bilingual fields (q1b has full l10n, others get raw data)
    l10n = _PATIENT_L10N if patient_id == "q1b" else {}
    for key, bilingual_value in l10n.items():
        if key == "biomarker_annotations":
            # Special: this is extra data not in PATIENT model
            data["biomarker_annotations"] = resolve(bilingual_value, lang)
            continue
        data[key] = resolve(bilingual_value, lang)

    return data


# Curated PubMed search terms for Erika's confirmed molecular profile
RESEARCH_TERMS: list[str] = [
    "KRAS G12S metastatic colorectal cancer treatment",
    "mCRC FOLFOX first-line KRAS mutant",
    "pan-KRAS inhibitor colorectal cancer",
    "SOS1 inhibitor KRAS colorectal BI-1701963",
    "MSS colorectal cancer immunotherapy combination",
    "botensilimab balstilimab MSS CRC",
    "bevacizumab VTE thrombosis colorectal cancer safety",
    "FOLFOX oxaliplatin neurotoxicity prevention",
    "mCRC left-sided KRAS mutant prognosis",
    "ivonescimab FOLFOX colorectal HARMONi",
]


def get_patient_profile_text(patient_id: str = "q1b") -> str:
    """Return formatted patient profile for MCP resource.

    Sprint 99 / #436 bug 2 — fail closed on unregistered patient_id.
    Previously fell back to ``PATIENT`` (Erika), quietly serving her full
    clinical profile to any caller whose pid hadn't been registered yet.
    Now raises ``KeyError`` to match ``get_patient()`` — this is the same
    fail-closed contract adopted in Sprint 98 (#435).
    """
    p = _patient_registry.get(patient_id)
    if p is None:
        raise KeyError(f"Patient '{patient_id}' not found")
    biomarkers = "\n".join(f"  - {k}: {v}" for k, v in p.biomarkers.items())
    hospitals = ", ".join(p.hospitals)
    metastases = ", ".join(p.metastases) if p.metastases else "none listed"
    comorbidities = ", ".join(p.comorbidities) if p.comorbidities else "none"
    excluded = "\n".join(f"  - {k}: {v}" for k, v in p.excluded_therapies.items())

    tumor = (
        f"- **Tumor site**: {p.tumor_site} ({p.tumor_laterality})"
        if p.tumor_laterality
        else f"- **Tumor site**: {p.tumor_site}"
    )
    treatment = (
        f"- **Treatment**: {p.treatment_regimen} (cycle {p.current_cycle})"
        if p.current_cycle
        else f"- **Treatment**: {p.treatment_regimen}"
    )
    parts = [
        "# Patient Profile\n",
        f"- **Name**: {p.name}",
        f"- **Diagnosis**: {p.diagnosis_description} ({p.diagnosis_code})",
        f"- **Staging**: {p.staging}" if p.staging else "",
        f"- **Histology**: {p.histology}" if p.histology else "",
        tumor,
        f"- **Biomarkers**:\n{biomarkers}",
        treatment,
        f"- **ECOG**: {p.ecog}" if p.ecog else "",
        f"- **Metastases**: {metastases}",
        f"- **Comorbidities**: {comorbidities}",
        f"- **Hospitals**: {hospitals}",
        f"- **Treating physician**: {p.treating_physician}" if p.treating_physician else "",
        f"- **Excluded therapies**:\n{excluded}" if p.excluded_therapies else "",
        f"- **Notes**: {p.notes}",
    ]
    return "\n".join(line for line in parts if line) + "\n"


def get_research_terms_text(patient_id: str = "q1b") -> str:
    """Return formatted research terms for MCP resource."""
    patient_terms = _patient_research_terms.get(patient_id, RESEARCH_TERMS)
    terms = "\n".join(f"- {t}" for t in patient_terms)
    return f"# Research Search Terms\n\nCurated PubMed queries for this case:\n\n{terms}\n"


def public_patient_view(patient: PatientProfile) -> dict:
    """Allowlisted projection of PatientProfile for non-localized consumers.

    Sprint 100 / #440 Pattern F — shared with the dashboard /api/detail/patient
    allowlist (dashboard_api.py), reused here so the MCP tool
    `get_patient_context` doesn't leak rodné číslo / nou_id / poisťovňa
    (`patient_ids`), home GPS (`home_region`), per-variant VAF + HGVS
    (`oncopanel_history`), or operational flags (`agent_whitelist`,
    `paused`, `notification_policy`). The clinical-profile fields below are
    the same set `/api/detail/patient` ships post-Sprint-99 (#438 bug 4).

    The full model_dump still lives on `get_patient_localized()` for
    `/api/patient`, which intentionally surfaces patient_ids + l10n overlays
    to the session-authed UI — that is the curated per-patient endpoint
    the dashboard reads end-to-end. This helper exists for the smaller,
    bearer-authed surfaces where the sensitive fields aren't needed.
    """
    return {
        "patient_id": patient.patient_id,
        "name": patient.name,
        "diagnosis_code": patient.diagnosis_code,
        "diagnosis_description": patient.diagnosis_description,
        "tumor_site": patient.tumor_site,
        "tumor_laterality": patient.tumor_laterality,
        "staging": patient.staging,
        "histology": patient.histology,
        "treatment_regimen": patient.treatment_regimen,
        "current_cycle": patient.current_cycle,
        "ecog": patient.ecog,
        "metastases": list(patient.metastases),
        "comorbidities": list(patient.comorbidities),
        "hospitals": list(patient.hospitals),
        "treating_physician": patient.treating_physician,
        "notes": patient.notes,
        "biomarkers": dict(patient.biomarkers),
        "excluded_therapies": dict(patient.excluded_therapies),
    }


def get_context_tags(patient_id: str = "q1b") -> list[str]:
    """Derive research tags from patient context.

    Sprint 99 / #436 bug 1 — previously read the module-level ``PATIENT``
    constant, which tagged every caller's research corpus with Erika's
    KRAS G12S / mFOLFOX6 / mCRC markers. For non-q1b patients (sgu breast,
    e5g preventive) this was a clinical-safety issue because the tags drive
    downstream surfacing. Now resolves the registered patient; falls back to
    ``PATIENT`` only for the default q1b path (preserves legacy callers +
    tests that invoke with no args).
    """
    patient = _patient_registry.get(patient_id) or PATIENT
    tags = []
    if patient.treatment_regimen:
        tags.append(patient.treatment_regimen)
    if patient.tumor_site:
        tags.append(patient.tumor_site.lower().replace(" ", "_"))
    if patient.diagnosis_description:
        # Extract key terms from diagnosis
        for term in ["colorectal", "sigmoid", "rectal", "colon"]:
            if term in patient.diagnosis_description.lower():
                tags.append(term)
                break
    for marker, value in patient.biomarkers.items():
        tags.append(f"{marker}_{value}")
    return tags


# ── Patient Registry ──────────────────────────────
# In-memory registry of loaded patient profiles. Erika is pre-seeded.
# Future patients load from oncofiles on first access.

_patient_registry: dict[str, PatientProfile] = {
    "q1b": PATIENT,
    "e5g": PATIENT_E5G,
    "sgu": PATIENT_SGU,
}

# Infra-only override: PAUSED_PATIENTS env var toggles pause without a code push.
# Additive (never un-pauses a code-paused patient).
from .config import PAUSED_PATIENTS as _PAUSED_PATIENTS_ENV  # noqa: E402

for _pid in _PAUSED_PATIENTS_ENV:
    _p = _patient_registry.get(_pid)
    if _p is not None:
        _p.paused = True

# Per-patient bearer tokens for oncofiles. Token scopes all data automatically.
# Erika uses the default ONCOFILES_MCP_TOKEN from config.
_patient_tokens: dict[str, str] = {}  # patient_id → bearer token

# Auto-populate tokens from env vars: ONCOFILES_MCP_TOKEN_<ID> (e.g. ONCOFILES_MCP_TOKEN_E5G)
for _pid in list(_patient_registry.keys()):
    _env_key = f"ONCOFILES_MCP_TOKEN_{_pid.upper()}"
    _tok = os.environ.get(_env_key, "")
    if _tok:
        _patient_tokens[_pid] = _tok

# Per-patient research terms. Erika's are hardcoded; others derived from profile.
_patient_research_terms: dict[str, list[str]] = {"q1b": RESEARCH_TERMS, "e5g": [], "sgu": []}

# Per-patient recipients. Erika's are hardcoded; others loaded from oncofiles.
_patient_recipients: dict[str, dict[str, Recipient]] = {"q1b": RECIPIENTS, "e5g": {}, "sgu": {}}

DEFAULT_PATIENT_ID = "q1b"


def list_patient_ids() -> list[str]:
    """Return all registered patient IDs."""
    return list(_patient_registry.keys())


def get_patient(patient_id: str = DEFAULT_PATIENT_ID) -> PatientProfile:
    """Get a patient profile by ID. Returns Erika by default."""
    if patient_id in _patient_registry:
        return _patient_registry[patient_id]
    raise KeyError(f"Patient '{patient_id}' not found. Register via register_patient().")


def register_patient(
    patient_id: str,
    token: str,
    profile: PatientProfile,
    research_terms: list[str] | None = None,
    recipients: dict[str, Recipient] | None = None,
) -> PatientProfile:
    """Register a new patient in the in-memory registry.

    Args:
        patient_id: Unique patient identifier (e.g. "jan_novak")
        token: Dedicated oncofiles bearer token — scopes all data to this patient
        profile: Patient profile with diagnosis, biomarkers, treatment plan
        research_terms: Curated PubMed search terms (derived from diagnosis if None)
        recipients: Care team recipients for WhatsApp (empty if None)
    """
    profile.patient_id = patient_id
    _patient_registry[patient_id] = profile
    _patient_tokens[patient_id] = token
    _patient_research_terms[patient_id] = research_terms or _derive_research_terms(profile)
    _patient_recipients[patient_id] = recipients or {}
    return profile


def _derive_research_terms(patient: PatientProfile) -> list[str]:
    """Auto-generate PubMed search terms from a patient's profile."""
    terms = []
    dx = patient.diagnosis_description.lower()
    regimen = patient.treatment_regimen

    # Cancer type + treatment
    if dx and regimen:
        terms.append(f"{dx} {regimen} treatment")

    # Biomarker-specific searches
    for marker, value in patient.biomarkers.items():
        if isinstance(value, str) and value.lower() not in ("wild-type", "negative", "false"):
            terms.append(f"{marker} {value} {dx}")

    # Treatment + side effects
    if regimen:
        terms.append(f"{regimen} toxicity management")
        terms.append(f"{regimen} dose modification")

    # General prognosis
    if patient.staging:
        terms.append(f"{dx} stage {patient.staging} prognosis")

    return terms or [f"{dx} treatment"]


def get_patient_token(patient_id: str = DEFAULT_PATIENT_ID) -> str | None:
    """Get the oncofiles bearer token for a patient.

    Returns None for Erika (uses default ONCOFILES_MCP_TOKEN from config).
    For other patients, returns their dedicated token which scopes all
    oncofiles data to that patient automatically.
    """
    return _patient_tokens.get(patient_id)


def append_approved_oncopanel(patient_id: str, panel: Oncopanel) -> None:
    """Append a physician-approved oncopanel to the in-memory registry.

    Durable persistence lives in oncofiles agent_state under
    `approved_oncopanel:{patient_id}:{panel_id}` — this function is the
    best-effort in-process mirror so eligibility rules + dashboard
    surfaces pick up the approval immediately without a restart. On
    restart the in-memory registry rehydrates from agent_state via the
    caller's startup path (tracked as a Sprint 96 follow-up).

    Idempotent: replaces any prior entry with the same panel_id.
    """
    profile = _patient_registry.get(patient_id)
    if profile is None:
        return
    history = [p for p in profile.oncopanel_history if p.panel_id != panel.panel_id]
    history.append(panel)
    profile.oncopanel_history = history


def get_patient_recipients(
    patient_id: str = DEFAULT_PATIENT_ID,
) -> dict[str, Recipient]:
    """Get recipients for a patient."""
    return _patient_recipients.get(patient_id, {})


def get_patient_research_terms(
    patient_id: str = DEFAULT_PATIENT_ID,
) -> list[str]:
    """Get curated research terms for a patient."""
    return _patient_research_terms.get(patient_id, [])


def build_patient_profile_text(patient: PatientProfile) -> str:
    """Build formatted profile text for any patient (not just Erika)."""
    biomarkers = "\n".join(f"  - {k}: {v}" for k, v in patient.biomarkers.items())
    hospitals = ", ".join(patient.hospitals)
    metastases = ", ".join(patient.metastases) if patient.metastases else "none"
    comorbidities = ", ".join(patient.comorbidities) if patient.comorbidities else "none"
    excluded = "\n".join(f"  - {k}: {v}" for k, v in patient.excluded_therapies.items())

    geography_block = ""
    if patient.home_region is not None:
        hr = patient.home_region
        geography_block = f"- **Home region**: {hr.city}, {hr.country}" + (
            f" (lat={hr.lat:.3f}, lon={hr.lon:.3f})" if hr.lat and hr.lon else ""
        )
    enrollment_block = ""
    if patient.enrollment_preference is not None:
        pref = patient.enrollment_preference
        pref_str = ", ".join(pref.preferred_countries) or "none"
        lang_str = ", ".join(pref.language_preferences) or "none"
        enrollment_block = (
            "- **Enrollment geography** (trial-site gating):\n"
            f"  - Preferred countries (tier order): {pref_str}\n"
            f"  - Max travel: {pref.max_travel_km} km\n"
            f"  - Languages: {lang_str}\n"
            f"  - Global opt-in: {pref.allow_unique_opportunity_global}"
        )

    parts = [
        "# Patient Profile\n",
        f"- **Patient ID**: {patient.patient_id}",
        f"- **Name**: {patient.name}",
        f"- **Diagnosis**: {patient.diagnosis_description} ({patient.diagnosis_code})",
        f"- **Staging**: {patient.staging}" if patient.staging else "",
        f"- **Histology**: {patient.histology}" if patient.histology else "",
        f"- **Tumor site**: {patient.tumor_site}",
        f"- **Biomarkers**:\n{biomarkers}",
        f"- **Treatment**: {patient.treatment_regimen}"
        + (f" (cycle {patient.current_cycle})" if patient.current_cycle else ""),
        f"- **ECOG**: {patient.ecog}" if patient.ecog else "",
        f"- **Metastases**: {metastases}",
        f"- **Comorbidities**: {comorbidities}",
        f"- **Hospitals**: {hospitals}",
        geography_block,
        enrollment_block,
        f"- **Treating physician**: {patient.treating_physician}"
        if patient.treating_physician
        else "",
        f"- **Excluded therapies**:\n{excluded}" if patient.excluded_therapies else "",
        f"- **Notes**: {patient.notes}",
    ]
    return "\n".join(line for line in parts if line) + "\n"


def build_biomarker_rules(patient: PatientProfile) -> str:
    """Generate biomarker safety rules from a patient's profile.

    These are the NEVER-violate rules that go into the system prompt.
    Derived dynamically from the patient's biomarkers and excluded therapies.
    """
    rules = ["# Biomarker Rules (NEVER violate)"]
    for marker, value in patient.biomarkers.items():
        rules.append(f"- {marker}: {value}")
    if patient.excluded_therapies:
        rules.append("\nExcluded therapies (NEVER suggest):")
        for therapy, reason in patient.excluded_therapies.items():
            rules.append(f"- {therapy}: {reason}")
    if patient.comorbidities:
        rules.append("\nComorbidity alerts:")
        for c in patient.comorbidities:
            rules.append(f"- {c}")
    return "\n".join(rules)


def build_geographic_rules(patient: PatientProfile) -> str:
    """Generate geographic enrollment rules for agent system prompts (#394).

    Agents that search for trials should prefer sites in `preferred_countries`
    and skip reasoning about trials in excluded countries. Emitted as a
    dedicated section so agents treat it as a hard constraint, not advice.
    """
    if patient.home_region is None or patient.enrollment_preference is None:
        return ""
    hr = patient.home_region
    pref = patient.enrollment_preference
    preferred = ", ".join(pref.preferred_countries) or "none"
    excluded = ", ".join(pref.excluded_countries) or "none"
    global_note = (
        "Globally unique opportunities are acceptable (flag for physician)."
        if pref.allow_unique_opportunity_global
        else "Do NOT suggest trials outside preferred_countries — not enrollable."
    )
    return f"""\
# Enrollment Geography Rules (NEVER violate)
- Patient home: {hr.city}, {hr.country}
- Preferred countries (tier order): {preferred}
- Excluded countries: {excluded}
- Max travel: {pref.max_travel_km} km
- Global policy: {global_note}
- When calling search_trials / search_trials_eu / search_clinical_trials,
  pass country from preferred_countries first (home country tier 0).
- When ranking PubMed / trial results, down-rank entries whose sites are
  not in preferred_countries. Geography filter runs BEFORE biomarker match.
"""


def is_general_health_patient(patient: PatientProfile) -> bool:
    """True if patient is non-oncology (general health / preventive care)."""
    return patient.diagnosis_code.startswith("Z") or patient.treatment_regimen == ""


# ── Dynamic genetic profile ────────────────────

_BIOMARKER_PATTERNS: dict[str, list[re.Pattern]] = {
    "HER2": [re.compile(r"HER[\s-]*2[^:]*:\s*(positive|negative|equivocal)", re.I)],
    "KRAS": [re.compile(r"KRAS[^:]*:\s*(mutant|wild[\s-]*type|positive|negative)", re.I)],
    "NRAS": [re.compile(r"NRAS[^:]*:\s*(mutant|wild[\s-]*type|positive|negative)", re.I)],
    "BRAF": [re.compile(r"BRAF[^:]*:\s*(mutant|wild[\s-]*type|V600E|positive|negative)", re.I)],
    "MSI": [re.compile(r"MSI[^:]*:\s*(MSI[\s-]*H|MSS|MSI[\s-]*L|stable|high|low)", re.I)],
    "MMR": [re.compile(r"MMR[^:]*:\s*(deficient|proficient|dMMR|pMMR)", re.I)],
    "TMB": [re.compile(r"TMB[^:]*:\s*(\d+\.?\d*\s*mut/Mb|high|low|intermediate)", re.I)],
    "ER": [re.compile(r"\bER[^:]*:\s*(positive|negative|\d+\s*%)", re.I)],
    "PR": [re.compile(r"\bPR[^:]*:\s*(positive|negative|\d+\s*%)", re.I)],
    "Ki-67": [re.compile(r"Ki[\s-]*67[^:]*:\s*(\d+\s*%|high|low|intermediate)", re.I)],
}


_GENETIC_SEARCH_TERMS = ["genetik", "HER2", "FISH", "NGS", "KRAS", "BRAF", "MSI", "pathology"]


# Concurrency limit for oncofiles calls — prevents overwhelming the queue.
# Oncofiles has max 3 general + max 1 heavy semaphore slots with 8s timeout.
# Exceeding this causes mass rejections (126 suppressed errors in one session).
_ONCOFILES_CONCURRENCY = asyncio.Semaphore(3)


async def get_genetic_profile(
    patient_id: str = "q1b", *, token: str | None = None
) -> dict[str, str]:
    """Fetch genetic/biomarker data from oncofiles documents.

    Uses semaphore-bounded concurrency to avoid overwhelming oncofiles.

    Sprint 99 / #436 bug 3 — fail closed on unregistered patient_id.
    Previously seeded the result with Erika's biomarkers (KRAS G12S, ATM
    biallelic loss, TP53 splice) before querying oncofiles. If oncofiles
    returned no docs, the caller got her profile back under another pid.
    Now returns an empty dict when the pid is unregistered — no data is
    safer than wrong data (extends Sprint 98 fail-closed contract).
    """
    patient = _patient_registry.get(patient_id)
    if patient is None:
        return {}
    profile = dict(patient.biomarkers)

    # Search with bounded concurrency (3 at a time)
    async def _search(term: str) -> list[dict]:
        async with _ONCOFILES_CONCURRENCY:
            try:
                result = await oncofiles_client.search_documents(text=term, token=token)
                return result.get("documents", []) if isinstance(result, dict) else []
            except Exception as e:
                record_suppressed_error("patient_context", f"search_{term}", e)
                return []

    search_results = await asyncio.gather(*[_search(t) for t in _GENETIC_SEARCH_TERMS])

    # Collect unique doc IDs
    seen_ids: set[str] = set()
    doc_ids: list[str] = []
    for docs in search_results:
        for doc in docs:
            doc_id = str(doc.get("id", ""))
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                doc_ids.append(doc_id)

    # Prefer document summaries over full content when available
    # Full view_document is expensive — use summary field from search results
    doc_summaries: dict[str, str] = {}
    for docs in search_results:
        for doc in docs:
            doc_id = str(doc.get("id", ""))
            summary = doc.get("summary") or doc.get("description") or ""
            if doc_id and summary:
                doc_summaries[doc_id] = summary

    # First pass: extract biomarkers from summaries (no API calls needed)
    for doc_id in doc_ids:
        summary = doc_summaries.get(doc_id, "")
        if summary:
            _update_biomarkers(profile, summary)

    # Second pass: fetch full content only for docs that might have more data
    # Skip if we already have all common biomarkers filled
    common_markers = {"KRAS", "NRAS", "BRAF", "HER2", "MSI"}
    missing = common_markers - set(profile.keys())
    if missing and doc_ids:

        async def _view(doc_id: str) -> str:
            async with _ONCOFILES_CONCURRENCY:
                try:
                    content = await oncofiles_client.view_document(doc_id, token=token)
                    return _extract_text(content)
                except Exception as e:
                    record_suppressed_error("patient_context", f"view_{doc_id}", e)
                    return ""

        # Cap at 10 documents max to avoid queue overload
        texts = await asyncio.gather(*[_view(d) for d in doc_ids[:10]])
        for text in texts:
            if text:
                _update_biomarkers(profile, text)

    return profile


def _extract_text(content: dict | str) -> str:
    """Extract plain text from view_document response."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if "ocr_text" in content:
            return content["ocr_text"]
        if "content" in content and isinstance(content["content"], dict):
            return content["content"].get("ocr_text", "")
        return " ".join(str(v) for v in content.values() if isinstance(v, str))
    return ""


def _update_biomarkers(profile: dict[str, str], text: str) -> None:
    """Extract biomarker values from OCR text and update profile."""
    for marker, patterns in _BIOMARKER_PATTERNS.items():
        if marker in profile:
            continue
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                profile[marker] = match.group(1).strip().lower()
                break
