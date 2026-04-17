"""Stub clinical protocol scaffolding for breast cancer patients (C50.*).

This is deliberately minimal — it establishes the diagnosis-driven dispatch
shape so agents and dashboards stop leaking mFOLFOX6 assumptions. Real clinical
thresholds are placeholders pending oncologist review. Source: ESMO 2023 Breast
Cancer Living Guidelines, NCCN Breast Cancer Guidelines.
"""

from __future__ import annotations

import copy
import functools

from .locale import L, resolve

# Regimen lookup by treatment line + subtype.
# For Nora (HR+/HER2-, metastatic) 1L is CDK4/6 + aromatase inhibitor.
BREAST_REGIMENS: dict[str, dict] = {
    "AC-T": {
        "label": L(
            "AC-T (doxorubicín + cyklofosfamid → paklitaxel)",
            "AC-T (doxorubicin + cyclophosphamide → paclitaxel)",
        ),
        "setting": L("adjuvantná / neoadjuvantná", "adjuvant / neoadjuvant"),
        "indication": L(
            "HER2-negatívny včasný karcinóm s vysokým rizikom",
            "HER2-negative early-stage high risk",
        ),
    },
    "TCHP": {
        "label": L(
            "TCHP (docetaxel + karboplatina + trastuzumab + pertuzumab)",
            "TCHP (docetaxel + carboplatin + trastuzumab + pertuzumab)",
        ),
        "setting": L("neoadjuvantná", "neoadjuvant"),
        "indication": L("HER2-pozitívny", "HER2-positive"),
    },
    "CDK46_AI": {
        "label": L(
            "CDK4/6 inhibítor + aromatázový inhibítor", "CDK4/6 inhibitor + aromatase inhibitor"
        ),
        "setting": L("1L metastatická HR+/HER2-", "1L metastatic HR+/HER2-"),
        "indication": L("HR+ / HER2-negatívny metastatický", "HR+ / HER2-negative metastatic"),
    },
    "fulvestrant_CDK46": {
        "label": L("Fulvestrant + CDK4/6 inhibítor", "Fulvestrant + CDK4/6 inhibitor"),
        "setting": L("2L po progresii na AI", "2L after AI progression"),
        "indication": L("HR+ / HER2-negatívny metastatický", "HR+ / HER2-negative metastatic"),
    },
    "T-DXd": {
        "label": L("Trastuzumab deruxtecan", "Trastuzumab deruxtecan"),
        "setting": L("2L+ HER2-pozitívny, HER2-low", "2L+ HER2-positive, HER2-low"),
        "indication": L("HER2-pozitívny alebo HER2-low", "HER2-positive or HER2-low"),
    },
    "PARP": {
        "label": L(
            "PARP inhibítor (olaparib / talazoparib)", "PARP inhibitor (olaparib / talazoparib)"
        ),
        "setting": L("BRCA1/2 mutácia", "BRCA1/2 mutation"),
        "indication": L("gBRCA-mutovaný metastatický", "gBRCA-mutated metastatic"),
    },
}

# Pre-cycle lab safety thresholds.
# source: FDA palbociclib label §5.1 (ANC ≥1000 C1D1); FDA ribociclib / abemaciclib labels;
# ESMO 2023 Breast Cancer Living Guideline §7.4. STATUS: stub — pending oncologist sign-off
# for Nora's specific regimen (goserelin + letrozole + ribociclib).
BREAST_LAB_SAFETY_THRESHOLDS: dict[str, dict] = {
    "ANC": {
        "min": 1000,
        "unit": "/uL",
        "action": "hold_chemo",
        "note": "CDK4/6: ANC >=1000",
        "source": "FDA palbociclib label §5.1; ESMO 2023 §7.4",
    },
    "PLT": {
        "min": 75000,
        "unit": "/uL",
        "action": "hold_chemo",
        "source": "FDA CDK4/6 labels",
    },
    "creatinine": {
        "max_ratio": 1.5,
        "note": "vs ULN",
        "action": "hold_chemo",
        "source": "FDA CDK4/6 labels",
    },
    "ALT": {
        "max_ratio": 3.0,
        "note": "vs ULN",
        "action": "hold_chemo",
        "source": "FDA palbociclib label §5.2 hepatic",
    },
    "AST": {
        "max_ratio": 3.0,
        "note": "vs ULN",
        "action": "hold_chemo",
        "source": "FDA palbociclib label §5.2 hepatic",
    },
    "bilirubin": {
        "max_ratio": 1.5,
        "note": "vs ULN",
        "action": "hold_chemo",
        "source": "FDA CDK4/6 labels",
    },
}

# Dose modification rules (CDK4/6 neutropenia focus)
BREAST_DOSE_MODIFICATION_RULES: dict[str, dict] = {
    "cdk46_neutropenia_grade_3": L(
        "Pozastaviť CDK4/6 do ANC >= 1000. Obnoviť rovnakú dávku.",
        "Hold CDK4/6 until ANC >= 1000. Resume same dose.",
    ),
    "cdk46_neutropenia_grade_4": L(
        "Pozastaviť CDK4/6. Obnoviť na nižšej dávkovej úrovni.",
        "Hold CDK4/6. Resume at next lower dose level.",
    ),
    "cdk46_alt_ast_grade_3": L(
        "Pozastaviť CDK4/6 do <= stupeň 1. Obnoviť na nižšej dávkovej úrovni.",
        "Hold CDK4/6 until <= grade 1. Resume at next lower dose level.",
    ),
}

# Treatment milestones for metastatic breast (HR+)
BREAST_TREATMENT_MILESTONES: list[dict] = [
    {
        "cycle": 2,
        "action": "pk_response_imaging",
        "description": L(
            "Prvé zhodnotenie odpovede (zobrazenie + tumor markery CA 15-3)",
            "First response evaluation (imaging + CA 15-3 tumor markers)",
        ),
    },
    {
        "cycle": 3,
        "action": "bone_health_check",
        "description": L(
            "DEXA / fraktúrne riziko, optimalizácia bisfosfonátu/denosumabu",
            "DEXA / fracture risk, bisphosphonate/denosumab optimization",
        ),
    },
    {
        "cycle": 6,
        "action": "hormone_response_review",
        "description": L(
            "Hodnotenie hormonálnej odpovede, kontinuácia vs switch",
            "Hormone response review, continue vs switch decision",
        ),
    },
]

# Watched trials — HR+/HER2- metastatic breast
BREAST_WATCHED_TRIALS: list[str] = [
    "INAVO120 (inavolisib + palbociclib + fulvestrant)",
    "postMONARCH (abemaciclib after CDK4/6 progression)",
    "CAPItello-291 (capivasertib + fulvestrant)",
    "DESTINY-Breast06 (T-DXd in HER2-low)",
    "SERENA-6 (camizestrant + CDK4/6)",
]

# Next-line options after CDK4/6 + AI progression
BREAST_SECOND_LINE_OPTIONS: list[dict] = [
    {
        "regimen": "Fulvestrant + alpelisib (PIK3CA mutant)",
        "evidence": L("Štúdia SOLAR-1", "SOLAR-1 trial"),
        "note": L("Iba ak PIK3CA mutovaný", "Only if PIK3CA mutant"),
    },
    {
        "regimen": "Fulvestrant + capivasertib",
        "evidence": L("Štúdia CAPItello-291", "CAPItello-291 trial"),
        "note": L("PI3K/AKT/PTEN altered", "PI3K/AKT/PTEN altered"),
    },
    {
        "regimen": "Everolimus + exemestane",
        "evidence": L("Štúdia BOLERO-2", "BOLERO-2 trial"),
        "note": L("mTOR inhibícia", "mTOR inhibition"),
    },
    {
        "regimen": "Sacituzumab govitecan (TROPiCS-02)",
        "evidence": L("Štúdia TROPiCS-02", "TROPiCS-02 trial"),
        "note": L("HR+ / HER2-negative 2L+", "HR+ / HER2-negative 2L+"),
    },
    {
        "regimen": "T-DXd (HER2-low)",
        "evidence": L("DESTINY-Breast04", "DESTINY-Breast04 trial"),
        "note": L("Iba ak HER2-low (IHC 1+/2+)", "Only if HER2-low (IHC 1+/2+)"),
    },
]

# Safety flags specific to breast
BREAST_SAFETY_FLAGS: dict[str, dict] = {
    "anti_her2_her2_negative": {
        "label": L("Anti-HER2 pri HER2-negatívnom", "Anti-HER2 with HER2-negative"),
        "rule": L(
            "NIE JE indikované (okrem HER2-low pri T-DXd)",
            "NOT indicated (except HER2-low with T-DXd)",
        ),
        "source": "ESMO 2023",
    },
    "cdk46_qtc_prolongation": {
        "label": L("CDK4/6 (ribociclib) + QTc > 480ms", "CDK4/6 (ribociclib) + QTc > 480ms"),
        "rule": L(
            "Kontrola EKG pred C1, C2. Zvážiť alternatívny CDK4/6.",
            "ECG check before C1, C2. Consider alternative CDK4/6.",
        ),
        "source": "FDA label",
    },
    "aromatase_inhibitor_bone_loss": {
        "label": L("Aromatázový inhibítor + kostná strata", "Aromatase inhibitor + bone loss"),
        "rule": L(
            "Povinné bisfosfonát/denosumab + DEXA baseline a ročne",
            "Mandatory bisphosphonate/denosumab + DEXA baseline and annual",
        ),
        "source": "ESMO bone health 2020",
    },
}

# Pre-cycle checklist template — breast
BREAST_PRE_CYCLE_CHECKLIST = """\
## Pre-Cycle {cycle_number} Checklist — Breast (HR+/HER2-)

### 1. Laboratory Safety
- [ ] ANC >= 1,000/uL (CDK4/6 threshold)
- [ ] PLT >= 75,000/uL
- [ ] ALT/AST <= 3x ULN
- [ ] Creatinine <= 1.5x ULN

### 2. Toxicity Assessment
- [ ] Fatigue: Grade ___
- [ ] Nausea: Grade ___
- [ ] Hot flushes / arthralgias (AI)
- [ ] Neutropenia — tracked labs

### 3. Bone Health (if C79.* skeletal mets)
- [ ] Bisphosphonate / denosumab on schedule
- [ ] Calcium + vitamin D supplementation
- [ ] New bone pain / fracture risk

### 4. General Assessment
- [ ] ECOG: ___
- [ ] Weight / BMI
- [ ] Menopausal symptoms / quality of life

### 5. Upcoming Milestones
{milestones}

### 6. Questions for Oncologist
{questions}
"""


# Reference ranges (breast-specific — CA 15-3 / CA 27-29 live in clinical_protocol)
# Placeholder — to be confirmed with oncologist.

# Cumulative dose thresholds (placeholder; CDK4/6 doesn't have cumulative limits
# the way oxaliplatin does — kept empty to signal not-applicable).
BREAST_CUMULATIVE_DOSE_THRESHOLDS: dict[str, dict] = {}


@functools.lru_cache(maxsize=2)
def _resolve_breast_protocol_cached(lang: str) -> dict:
    """Resolve bilingual breast protocol data — cached per language."""
    return {
        "lab_thresholds": BREAST_LAB_SAFETY_THRESHOLDS,
        "regimens": resolve(BREAST_REGIMENS, lang),
        "dose_modifications": resolve(BREAST_DOSE_MODIFICATION_RULES, lang),
        "milestones": resolve(BREAST_TREATMENT_MILESTONES, lang),
        "watched_trials": BREAST_WATCHED_TRIALS,
        "second_line_options": resolve(BREAST_SECOND_LINE_OPTIONS, lang),
        "cumulative_dose": BREAST_CUMULATIVE_DOSE_THRESHOLDS,
        "safety_flags": resolve(BREAST_SAFETY_FLAGS, lang),
        "tumor_type": "breast",
    }


def resolve_breast_protocol(lang: str = "sk") -> dict:
    """Return all breast protocol data with bilingual values resolved."""
    return copy.deepcopy(_resolve_breast_protocol_cached(lang))


def is_breast_patient(diagnosis_code: str | None) -> bool:
    """True if diagnosis code is a breast primary (C50.*)."""
    if not diagnosis_code:
        return False
    return diagnosis_code.upper().startswith("C50")
