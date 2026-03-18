"""Embedded clinical protocol data for mCRC treatment monitoring.

Sourced from ESMO 2022 mCRC Living Guidelines, NCCN Colon Cancer Guidelines,
ASCO VTE Guidelines, ASH 2021 VTE in Cancer. NOT AI-generated.

All user-facing strings are bilingual via L(sk, en) dicts.
Use resolve_protocol(lang) to get locale-resolved copies.
"""

from __future__ import annotations

import copy
import functools

from .locale import L, resolve

# FOLFOX dose modification rules (NCCN)
DOSE_MODIFICATION_RULES: dict[str, dict] = {
    "neuropathy_grade_2": L(
        "Znížiť oxaliplatinu na 75%. Pokračovať 5-FU/LV plnou dávkou.",
        "Reduce oxaliplatin to 75%. Continue 5-FU/LV full dose.",
    ),
    "neuropathy_grade_3": L(
        "POZASTAVIŤ oxaliplatinu. Pokračovať 5-FU/LV (de Gramont). "
        "Obnoviť na 50% pri zlepšení na stupeň 1.",
        "HOLD oxaliplatin. Continue 5-FU/LV (de Gramont). Resume at 50% if resolves to grade 1.",
    ),
    "neuropathy_grade_4": L(
        "UKONČIŤ oxaliplatinu natrvalo.",
        "DISCONTINUE oxaliplatin permanently.",
    ),
    "plt_below_75k": L(
        "Pozastaviť FOLFOX. Kontrola o 1 týždeň.",
        "Hold FOLFOX. Recheck in 1 week.",
    ),
    "anc_below_1500": L(
        "Pozastaviť FOLFOX. Zvážiť G-CSF pri opakovaní.",
        "Hold FOLFOX. Consider G-CSF if recurrent.",
    ),
    "alt_ast_above_5x": L(
        "Pozastaviť FOLFOX. Vyhodnotiť hepatálnu progresiu vs toxicitu.",
        "Hold FOLFOX. Evaluate hepatic progression vs toxicity.",
    ),
    "diarrhea_grade_3": L(
        "Pozastaviť 5-FU. Obnoviť na 80% po zlepšení na stupeň 1.",
        "Hold 5-FU. Resume at 80% when resolved to grade 1.",
    ),
}

# Pre-cycle lab safety thresholds
LAB_SAFETY_THRESHOLDS: dict[str, dict] = {
    "ANC": {"min": 1500, "unit": "/uL", "action": "hold_chemo"},
    "PLT": {"min": 75000, "unit": "/uL", "action": "hold_chemo"},
    "PLT_anticoag": {"min": 50000, "unit": "/uL", "action": "flag_hematology"},
    "creatinine": {"max_ratio": 1.5, "note": "vs ULN", "action": "hold_chemo"},
    "ALT": {"max_ratio": 5.0, "note": "vs ULN, liver mets allowed", "action": "hold_chemo"},
    "AST": {"max_ratio": 5.0, "note": "vs ULN, liver mets allowed", "action": "hold_chemo"},
    "bilirubin": {"max_ratio": 1.5, "note": "vs ULN", "action": "hold_chemo"},
}

# Treatment timeline milestones
TREATMENT_MILESTONES: list[dict] = [
    {
        "cycle": 3,
        "action": "first_response_ct",
        "description": L(
            "Naplánovať prvé CT hodnotenie odpovede (RECIST 1.1)",
            "Schedule first CT response evaluation (RECIST 1.1)",
        ),
    },
    {
        "cycle": 4,
        "action": "tumor_markers",
        "description": L(
            "CEA + CA 19-9 trend oproti východiskovej hodnote",
            "CEA + CA 19-9 trend check vs baseline",
        ),
    },
    {
        "cycle": 6,
        "action": "neuropathy_cumulative",
        "description": L(
            "Formálne kumulatívne hodnotenie neuropatie (NCI-CTC)",
            "Formal cumulative neuropathy assessment (NCI-CTC)",
        ),
    },
    {
        "cycle": 6,
        "action": "maintenance_discussion",
        "description": L(
            "Diskusia o udržiavacej liečbe vs pokračovanie vs prestávka oxaliplatiny",
            "Discuss maintenance vs continuation vs oxaliplatin holiday",
        ),
    },
    {
        "cycle": 8,
        "action": "second_response_ct",
        "description": L(
            "Druhé CT hodnotenie odpovede",
            "Second CT response evaluation",
        ),
    },
    {
        "cycle": 12,
        "action": "end_of_first_line",
        "description": L(
            "Hodnotenie ukončenia 1L, stratégia udržiavacej liečby, skríning 2L štúdií",
            "Evaluate 1L completion, maintenance strategy, 2L trial screening",
        ),
    },
]

# Monitoring schedule (days relative to cycle start)
MONITORING_SCHEDULE: dict[str, dict] = {
    "pre_cycle_labs": L(
        "Každých 14 dní (deň 1 každého cyklu)", "Every 14 days (day 1 of each cycle)"
    ),
    "tumor_markers": L(
        "Každé 4-8 týždňov (cykly 2, 4, 6...)", "Every 4-8 weeks (cycles 2, 4, 6...)"
    ),
    "response_imaging": L(
        "Každých 8 týždňov po prvom hodnotení (cykly 4, 8, 12...)",
        "Every 8 weeks after first assessment (cycles 4, 8, 12...)",
    ),
    "neuropathy_grade": L(
        "Každý cyklus, formálne hodnotenie každé 3 cykly",
        "Every cycle, formal assessment every 3 cycles",
    ),
    "vte_check": L(
        "Každý cyklus: PLT + klinické DVT/PE hodnotenie",
        "Every cycle: PLT + clinical DVT/PE assessment",
    ),
    "ecog_assessment": L("Každý cyklus", "Every cycle"),
    "weight_nutrition": L(
        "Každý cyklus, upozorniť pri >5% úbytku od východiskovej hodnoty",
        "Every cycle, flag if >5% loss from baseline",
    ),
    "trial_screening": L(
        "Týždenne (nové štúdie sa publikujú priebežne)",
        "Weekly (new trials published continuously)",
    ),
    "research_scan": L(
        "Denne (PubMed, preprinty relevantné pre prípad)",
        "Daily (PubMed, preprints relevant to case)",
    ),
}

# Watched clinical trials (specific to patient profile)
WATCHED_TRIALS: list[str] = [
    "HARMONi-GI3 (ivonescimab + FOLFOX)",
    "pan-KRAS: BI-1701963 (SOS1 inhibitor)",
    "pan-KRAS: RMC-6236",
    "pan-KRAS: JAB-3312",
    "botensilimab + balstilimab (MSS CRC)",
    "anti-TIGIT combinations (MSS CRC)",
]

# 2L options ranking for KRAS G12S mCRC (ESMO/NCCN based)
SECOND_LINE_OPTIONS: list[dict] = [
    {
        "regimen": "FOLFIRI +/- bevacizumab",
        "evidence": L(
            "ESMO preferovaná 2L po oxaliplatine v 1L",
            "ESMO preferred 2L after oxaliplatin-based 1L",
        ),
        "note": L(
            "Ak bev nebol v 1L alebo po progresii na bev",
            "If bev not used in 1L or beyond progression on bev",
        ),
    },
    {
        "regimen": "FOLFIRI +/- aflibercept",
        "evidence": L("Štúdia VELOUR", "VELOUR trial"),
        "note": L("Anti-VEGF možnosť", "Anti-VEGF option"),
    },
    {
        "regimen": "FOLFIRI +/- ramucirumab",
        "evidence": L("Štúdia RAISE", "RAISE trial"),
        "note": L("Anti-VEGF možnosť", "Anti-VEGF option"),
    },
    {
        "regimen": "Trifluridine/tipiracil (TAS-102)",
        "evidence": L("Štúdia RECOURSE, 3L+", "RECOURSE trial, 3L+"),
        "note": L("Neskoršia línia", "Later line"),
    },
    {
        "regimen": "Regorafenib",
        "evidence": L("Štúdia CORRECT, 3L+", "CORRECT trial, 3L+"),
        "note": L("Neskoršia línia", "Later line"),
    },
    {
        "regimen": L("Klinická štúdia (pan-KRAS inhibítor)", "Clinical trial (pan-KRAS inhibitor)"),
        "evidence": L("Experimentálna", "Experimental"),
        "note": L(
            "Aktívne vyhľadávať štúdie pre KRAS G12S",
            "Screen actively for KRAS G12S-eligible trials",
        ),
    },
]

# Lab reference ranges (normal adult ranges)
LAB_REFERENCE_RANGES: dict[str, dict] = {
    "ANC": {"min": 1800, "max": 7700, "unit": "/uL"},
    "PLT": {"min": 150000, "max": 400000, "unit": "/uL"},
    "hemoglobin": {"min": 12.0, "max": 16.0, "unit": "g/dL", "note": "female"},
    "creatinine": {"min": 0.6, "max": 1.1, "unit": "mg/dL", "note": "female"},
    "ALT": {"min": 0, "max": 35, "unit": "U/L"},
    "AST": {"min": 0, "max": 35, "unit": "U/L"},
    "bilirubin": {"min": 0.1, "max": 1.2, "unit": "mg/dL"},
    "CEA": {"min": 0, "max": 5.0, "unit": "ng/mL", "note": "non-smoker ULN"},
    "CA_19_9": {"min": 0, "max": 37.0, "unit": "U/mL"},
    "WBC": {"min": 4.5, "max": 11.0, "unit": "×10³/µL"},
    "ABS_LYMPH": {"min": 1000, "max": 4800, "unit": "/µL"},
    "SII": {"min": 0, "max": 1800, "unit": "", "note": "systemic immune-inflammation index"},
    "NE_LY_RATIO": {"min": 0, "max": 3.0, "unit": "", "note": "neutrophil/lymphocyte ratio"},
}

# Health direction for lab parameters: determines if rising/falling is good or bad.
# "lower_is_better" = rising is worsening, falling is improving.
# "higher_is_better" = rising is improving, falling is worsening.
PARAMETER_HEALTH_DIRECTION: dict[str, str] = {
    "CEA": "lower_is_better",
    "CA_19_9": "lower_is_better",
    "ANC": "higher_is_better",
    "PLT": "in_range",  # both too high and too low are bad
    "hemoglobin": "higher_is_better",
    "creatinine": "lower_is_better",
    "ALT": "lower_is_better",
    "AST": "lower_is_better",
    "bilirubin": "lower_is_better",
    "WBC": "in_range",
    "ABS_LYMPH": "higher_is_better",
    "SII": "lower_is_better",
    "NE_LY_RATIO": "lower_is_better",
}

# Cumulative oxaliplatin dose thresholds (ESMO/NCCN)
CUMULATIVE_DOSE_THRESHOLDS: dict[str, dict] = {
    "oxaliplatin": {
        "unit": "mg/m²",
        "dose_per_cycle": 85,  # standard mFOLFOX6: 85 mg/m² q2w
        "thresholds": [
            {
                "at": 400,
                "action": L(
                    "Formálne hodnotenie neuropatie (NCI-CTC)",
                    "Formal neuropathy assessment (NCI-CTC)",
                ),
                "severity": "warning",
            },
            {
                "at": 550,
                "action": L(
                    "Dôrazne zvážiť prestávku oxaliplatiny",
                    "Strongly consider oxaliplatin holiday",
                ),
                "severity": "warning",
            },
            {
                "at": 680,
                "action": L(
                    "Vysoké riziko pretrvávajúcej neuropatie — diskusia o ukončení",
                    "High risk persistent neuropathy — discuss stop",
                ),
                "severity": "critical",
            },
            {
                "at": 850,
                "action": L(
                    "Maximum odporúčanej dávky — UKONČIŤ oxaliplatinu",
                    "Maximum recommended — STOP oxaliplatin",
                ),
                "severity": "critical",
            },
        ],
    },
}

# Cycle delay rules (ESMO/NCCN)
CYCLE_DELAY_RULES: list[dict] = [
    {
        "condition": "ANC 1000–1499",
        "action": L(
            "Odložiť 7 dní, kontrola. G-CSF pri opakovaní.",
            "Delay 7 days, recheck. G-CSF if recurrent.",
        ),
    },
    {
        "condition": "ANC < 1000",
        "action": L("Odložiť do >= 1500. G-CSF povinne.", "Delay until >= 1500. G-CSF mandatory."),
    },
    {
        "condition": "PLT 50000–74999",
        "action": L(
            "Odložiť 7 dní. Skontrolovať dávku antikoagulácie.",
            "Delay 7 days. Check anticoagulation dose.",
        ),
    },
    {
        "condition": "PLT < 50000",
        "action": L(
            "Pozastaviť chemo + znížiť Clexane. Konzultácia hematológ.",
            "Hold chemo + reduce Clexane. Hematology consult.",
        ),
    },
    {
        "condition": "ALT/AST 3–5x ULN",
        "action": L(
            "Odložiť 3–7 dní. Vyhodnotiť hepatálnu progresiu.",
            "Delay 3–7 days. Evaluate hepatic progression.",
        ),
    },
    {
        "condition": L("Kreatinín 1,5–2x HHN", "Creatinine 1.5–2x ULN"),
        "action": L("Odložiť 7 dní. Hydratácia. Kontrola.", "Delay 7 days. Hydration. Recheck."),
    },
    {
        "condition": L("Hnačka stupeň 2 neústupujúca", "Diarrhea grade 2 unresolved"),
        "action": L("Odložiť do stupňa ≤ 1.", "Delay until grade ≤ 1."),
    },
    {
        "condition": L("Neuropatia stupeň 2 zhoršujúca sa", "Neuropathy grade 2 worsening"),
        "action": L(
            "Zvážiť zníženie dávky oxaliplatiny na 75%.",
            "Consider oxaliplatin dose reduction to 75%.",
        ),
    },
    {
        "condition": L("Febrilná neutropénia", "Febrile neutropenia"),
        "action": L(
            "Pozastaviť do ústupu + ANC ≥ 1500. G-CSF profylaxia v ďalších cykloch.",
            "Hold until resolved + ANC ≥ 1500. G-CSF prophylaxis future cycles.",
        ),
    },
]

# Nutrition escalation thresholds (weight loss from baseline)
NUTRITION_ESCALATION: list[dict] = [
    {
        "loss_pct": 5,
        "action": L("Upozorniť na nutričné hodnotenie", "Flag for nutritional assessment"),
        "severity": "warning",
    },
    {
        "loss_pct": 7,
        "action": L(
            "Odporúčanie k dietetičke — perorálne nutričné doplnky",
            "Dietitian referral — oral nutritional supplements",
        ),
        "severity": "warning",
    },
    {
        "loss_pct": 10,
        "action": L(
            "Tím nutričnej podpory — zvážiť enterálnu výživu",
            "Nutritional support team — consider enteral nutrition",
        ),
        "severity": "critical",
    },
    {
        "loss_pct": 15,
        "action": L(
            "Upozornenie na malnutríciu — multidisciplinárne hodnotenie",
            "Malnutrition alert — multidisciplinary assessment",
        ),
        "severity": "critical",
    },
]

# Drug interaction safety flags
SAFETY_FLAGS: dict[str, dict] = {
    "anti_egfr_kras_mutant": {
        "label": L("Anti-EGFR pri KRAS mutácii", "Anti-EGFR with KRAS mutation"),
        "rule": L("NIKDY — trvalo kontraindikované", "NEVER — permanently contraindicated"),
        "source": "ESMO 2022",
    },
    "bevacizumab_active_vte": {
        "label": L("Bevacizumab pri aktívnej VTE", "Bevacizumab with active VTE"),
        "rule": L(
            "VYSOKÉ RIZIKO — vyžaduje výslovný súhlas onkológa",
            "HIGH RISK — requires explicit oncologist discussion",
        ),
        "source": "ASCO VTE 2023",
    },
    "oxaliplatin_grade3_neuropathy": {
        "label": L("Oxaliplatina pri neuropatii st. 3", "Oxaliplatin with grade 3 neuropathy"),
        "rule": L(
            "POZASTAVIŤ oxaliplatinu, pokračovať 5-FU/LV (de Gramont)",
            "HOLD oxaliplatin, continue 5-FU/LV (de Gramont)",
        ),
        "source": "NCCN",
    },
    "checkpoint_mono_pmmr_mss": {
        "label": L("Checkpoint monoterapia pri pMMR/MSS", "Checkpoint monotherapy with pMMR/MSS"),
        "rule": L("NIE JE indikovaná ako monoterapia", "NOT indicated as monotherapy"),
        "source": "ESMO 2022",
    },
    "lmwh_thrombocytopenia_50k": {
        "label": L("LMWH pri trombocytopénii <50k", "LMWH with thrombocytopenia <50k"),
        "rule": L(
            "UPOZORNENIE — zníženie dávky alebo pozastavenie, konzultácia hematológ",
            "FLAG — dose reduction or hold, hematology consult",
        ),
        "source": "ASH 2021",
    },
    "5fu_dpd_deficiency": {
        "label": L("5-FU pri DPD deficiencii", "5-FU with DPD deficiency"),
        "rule": L(
            "TEST odporúčaný — riziko fatálnej toxicity",
            "TEST recommended — fatal toxicity risk",
        ),
        "source": "ESMO/CPIC",
    },
}

# Pre-cycle checklist template
PRE_CYCLE_CHECKLIST = """\
## Pre-Cycle {cycle_number} Checklist — mFOLFOX6

### 1. Laboratory Safety
- [ ] ANC >= 1,500/uL
- [ ] PLT >= 75,000/uL (also check >= 50,000 for full-dose Clexane)
- [ ] Creatinine <= 1.5x ULN
- [ ] ALT/AST <= 5x ULN (liver mets threshold)
- [ ] Bilirubin <= 1.5x ULN

### 2. Toxicity Assessment (NCI-CTC grading)
- [ ] Peripheral neuropathy: Grade ___
- [ ] Diarrhea: Grade ___
- [ ] Mucositis: Grade ___
- [ ] Fatigue: Grade ___
- [ ] Hand-foot syndrome: Grade ___
- [ ] Nausea/vomiting: Grade ___

### 3. VTE Monitoring
- [ ] PLT adequate for Clexane continuation
- [ ] No new DVT/PE symptoms (leg swelling, dyspnea, chest pain)
- [ ] Clexane compliance confirmed

### 4. General Assessment
- [ ] ECOG performance status: ___
- [ ] Weight: ___ kg (baseline: ___ kg, change: __%)
- [ ] Nutritional status adequate

### 5. Upcoming Milestones
{milestones}

### 6. Questions for Oncologist
{questions}
"""


def check_lab_safety(lab_name: str, value: float) -> dict[str, str | bool]:
    """Check a single lab value against safety thresholds.

    Returns dict with 'safe', 'action', 'message' keys.
    """
    threshold = LAB_SAFETY_THRESHOLDS.get(lab_name)
    if not threshold:
        return {"safe": True, "action": "none", "message": f"No threshold defined for {lab_name}"}

    if "min" in threshold and value < threshold["min"]:
        return {
            "safe": False,
            "action": threshold["action"],
            "message": (
                f"{lab_name} = {value} {threshold.get('unit', '')} "
                f"< {threshold['min']} — {threshold['action']}"
            ),
        }
    return {"safe": True, "action": "none", "message": f"{lab_name} within safe range"}


def get_milestones_for_cycle(cycle: int) -> list[dict]:
    """Return milestones at or near the given cycle number."""
    return [m for m in TREATMENT_MILESTONES if m["cycle"] == cycle or m["cycle"] == cycle + 1]


def get_dose_modification(toxicity: str, lang: str = "en") -> str | None:
    """Look up dose modification rule for a toxicity key."""
    value = DOSE_MODIFICATION_RULES.get(toxicity)
    if value is None:
        return None
    return resolve(value, lang) if isinstance(value, dict) else value


def format_pre_cycle_checklist(
    cycle_number: int,
    milestones: str = "None upcoming",
    questions: str = "None generated",
) -> str:
    """Format the pre-cycle checklist template."""
    return PRE_CYCLE_CHECKLIST.format(
        cycle_number=cycle_number,
        milestones=milestones,
        questions=questions,
    )


@functools.lru_cache(maxsize=2)
def _resolve_protocol_cached(lang: str) -> dict:
    """Resolve bilingual protocol data — cached per language."""
    return {
        "lab_thresholds": LAB_SAFETY_THRESHOLDS,
        "reference_ranges": LAB_REFERENCE_RANGES,
        "health_direction": PARAMETER_HEALTH_DIRECTION,
        "dose_modifications": resolve(DOSE_MODIFICATION_RULES, lang),
        "milestones": resolve(TREATMENT_MILESTONES, lang),
        "monitoring_schedule": resolve(MONITORING_SCHEDULE, lang),
        "watched_trials": WATCHED_TRIALS,
        "second_line_options": resolve(SECOND_LINE_OPTIONS, lang),
        "cumulative_dose": resolve(CUMULATIVE_DOSE_THRESHOLDS, lang),
        "cycle_delay_rules": resolve(CYCLE_DELAY_RULES, lang),
        "nutrition_escalation": resolve(NUTRITION_ESCALATION, lang),
        "safety_flags": resolve(SAFETY_FLAGS, lang),
        "current_cycle": 3,
    }


def resolve_protocol(lang: str = "sk") -> dict:
    """Return all protocol data with bilingual values resolved to requested language."""
    return copy.deepcopy(_resolve_protocol_cached(lang))


# Section name aliases for the MCP tool
PROTOCOL_SECTIONS = {
    "lab_thresholds",
    "reference_ranges",
    "health_direction",
    "dose_modifications",
    "milestones",
    "monitoring_schedule",
    "watched_trials",
    "second_line_options",
    "cumulative_dose",
    "cycle_delay_rules",
    "nutrition_escalation",
    "safety_flags",
}
