"""Programmatic eligibility checker for clinical trials against patient profile."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date

from .models import (
    ClinicalTrial,
    EligibilityFlag,
    EligibilityResult,
    EnrollmentPreference,
    Oncopanel,
    OncopanelVariant,
    PatientProfile,
    TrialSite,
)

# ── Enrollment geography (#394) ─────────────────────────────────────────

# Default neighbor ordering when auto-generating EnrollmentPreference.
# Ordered by combination of shared border + linguistic proximity + healthcare
# similarity. Non-exhaustive — add countries as patients onboard.
_NEIGHBOR_COUNTRIES: dict[str, list[str]] = {
    "SK": ["CZ", "AT", "HU", "PL", "DE", "CH"],
    "CZ": ["SK", "AT", "PL", "DE", "HU"],
    "AT": ["DE", "CH", "SK", "CZ", "HU", "IT", "SI"],
    "HU": ["AT", "SK", "CZ", "RO", "HR", "SI"],
    "PL": ["CZ", "SK", "DE", "LT"],
    "DE": ["AT", "CH", "NL", "BE", "FR", "CZ", "PL", "DK"],
    "CH": ["AT", "DE", "FR", "IT"],
    "RO": ["HU", "BG", "AT", "CZ"],
    "SI": ["AT", "HR", "HU", "IT"],
    "HR": ["SI", "HU", "AT", "IT"],
}

# Statuses where the site is NOT enrolling new patients — filter out.
_INACTIVE_SITE_STATUSES = frozenset({"completed", "terminated", "withdrawn", "suspended", "closed"})

# Earth radius in km (mean — adequate for trial-distance filtering).
_EARTH_RADIUS_KM = 6371.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometers."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def default_enrollment_preference(
    home_country: str,
    max_travel_km: int = 600,
    language_preferences: list[str] | None = None,
) -> EnrollmentPreference:
    """Auto-generate sensible enrollment preference from home country.

    preferred_countries = [home, *immediate_neighbors_ordered_by_proximity].
    Caller should supply language_preferences; defaults to native + English
    best-guess when omitted.
    """
    hc = home_country.upper()
    neighbors = _NEIGHBOR_COUNTRIES.get(hc, [])
    preferred = [hc] + [n for n in neighbors if n != hc]
    langs = language_preferences if language_preferences is not None else ["en"]
    return EnrollmentPreference(
        max_travel_km=max_travel_km,
        preferred_countries=preferred,
        language_preferences=langs,
        excluded_countries=[],
        allow_unique_opportunity_global=False,
    )


def geographic_score(sites: list[TrialSite], patient: PatientProfile) -> float:
    """Score 0-100 for trial proximity to patient. 0 = filter out.

    100 = home country, short distance, actively recruiting.
    Returns 50 (neutral) when patient has no home_region / enrollment_preference
    — backwards-compatible: don't hard-filter trials for patients we haven't
    geolocated yet.
    """
    if not sites:
        return 0.0
    if patient.home_region is None or patient.enrollment_preference is None:
        return 50.0
    home = patient.home_region
    pref = patient.enrollment_preference
    preferred = [c.upper() for c in pref.preferred_countries]
    excluded = {c.upper() for c in pref.excluded_countries}
    best = 0.0
    for site in sites:
        sc = (site.country or "").upper()
        if not sc or sc in excluded:
            continue
        status = (site.status or "").lower()
        if status in _INACTIVE_SITE_STATUSES:
            continue
        if sc in preferred:
            tier = preferred.index(sc)
        elif pref.allow_unique_opportunity_global:
            tier = len(preferred)
        else:
            continue
        if site.lat is not None and site.lon is not None:
            km = haversine(home.lat, home.lon, site.lat, site.lon)
            if km > pref.max_travel_km and tier > 1:
                continue
            distance_penalty = min(km / max(pref.max_travel_km, 1), 1.0) * 30.0
        else:
            distance_penalty = 0.0
        tier_score = max(100.0 - tier * 12.0, 0.0)
        score = max(tier_score - distance_penalty, 0.0)
        best = max(best, score)
    return best


def is_geographically_accessible(sites: list[TrialSite], patient: PatientProfile) -> bool:
    """True when at least one site falls within the patient's enrollment envelope."""
    return geographic_score(sites, patient) > 0.0


# ── Genomic profile helpers (#398) ──────────────────────────────────────
# Variant-level queries over a patient's structured oncopanel history.
# Cleanly handles absence — patients with no panel get empty results, not errors.

_PATHOGENIC_SIGNIFICANCES = frozenset({"pathogenic", "likely_pathogenic"})

# DDR-deficiency genes (biallelic loss triggers PARPi/ATRi eligibility).
# ATM is the primary case for q1b. BRCA1/2 + PALB2 cover HRD-like contexts.
_DDR_CORE_GENES = frozenset({"ATM", "BRCA1", "BRCA2", "PALB2"})


def get_latest_oncopanel(patient: PatientProfile) -> Oncopanel | None:
    """Most recent oncopanel by report_date; None when patient has no history."""
    if not patient.oncopanel_history:
        return None
    return max(patient.oncopanel_history, key=lambda p: p.report_date or date.min)


def get_variants_for_gene(patient: PatientProfile, gene: str) -> list[OncopanelVariant]:
    """Variants affecting the given gene in the patient's latest oncopanel."""
    latest = get_latest_oncopanel(patient)
    if latest is None:
        return []
    target = gene.upper()
    return [v for v in latest.variants if v.gene.upper() == target]


def count_pathogenic_variants(patient: PatientProfile, gene: str) -> int:
    """Number of distinct pathogenic / likely-pathogenic variants in a gene."""
    return sum(
        1
        for v in get_variants_for_gene(patient, gene)
        if v.significance in _PATHOGENIC_SIGNIFICANCES
    )


def is_biallelic_loss(patient: PatientProfile, gene: str) -> bool:
    """Two or more pathogenic variants in one gene — proxy for biallelic loss."""
    return count_pathogenic_variants(patient, gene) >= 2


def is_ddr_deficient(patient: PatientProfile) -> bool:
    """HRD-like phenotype driven by biallelic loss in any core DDR gene.

    Triggers eligibility for PARPi (olaparib / rucaparib / niraparib / talazoparib)
    and ATRi (ceralasertib) classes. Primary case for q1b is ATM biallelic loss
    from the 2026-04-18 oncopanel.
    """
    return any(is_biallelic_loss(patient, gene) for gene in _DDR_CORE_GENES)


# ── Structured biomarker queries with flat-dict fallback (#398) ───────
# These helpers prefer the structured oncopanel history (variant-level
# traceability: date, lab, VAF, source document) over the flat biomarkers
# dict. Patients with no oncopanel fall back to the dict so existing
# single-patient flows keep working. Returns `(status, source_label)`
# so the dashboard can render the origin alongside the value.


@dataclass(frozen=True)
class BiomarkerStatus:
    """Biomarker query result with traceable origin.

    `value`:  normalized status string (e.g. "G12S", "MSS", "negative").
    `source`: "oncopanel:<report_date>" when read from oncopanel_history,
              "biomarkers_dict" when from the legacy flat dict,
              "unknown" when neither has data.
    `detail`: optional structured extra — e.g. the matched variant for
              oncopanel-sourced queries, so the dashboard can link to the
              source document page.
    """

    value: str
    source: str
    detail: OncopanelVariant | None = None


def get_kras_status(patient: PatientProfile) -> BiomarkerStatus:
    """Return patient's KRAS status (e.g. 'G12S', 'G12C', 'WT', 'mutant').

    Reads oncopanel first for the specific allele; falls back to
    `biomarkers["KRAS"]` for patients without structured panel data.
    """
    for variant in get_variants_for_gene(patient, "KRAS"):
        if variant.significance in _PATHOGENIC_SIGNIFICANCES and variant.protein_short:
            latest = get_latest_oncopanel(patient)
            src = (
                f"oncopanel:{latest.report_date}" if latest and latest.report_date else "oncopanel"
            )
            return BiomarkerStatus(
                value=variant.protein_short,
                source=src,
                detail=variant,
            )
    # No pathogenic KRAS variant in oncopanel → may be WT, or patient has no panel.
    latest = get_latest_oncopanel(patient)
    if latest is not None:
        src = f"oncopanel:{latest.report_date}" if latest.report_date else "oncopanel"
        return BiomarkerStatus(value="WT", source=src)
    raw = (patient.biomarkers.get("KRAS") or "") if patient.biomarkers else ""
    if raw:
        return BiomarkerStatus(value=str(raw), source="biomarkers_dict")
    return BiomarkerStatus(value="unknown", source="unknown")


def has_kras_g12c(patient: PatientProfile) -> bool:
    """True iff the patient's KRAS allele is specifically G12C.

    Matters because sotorasib / adagrasib are G12C-specific inhibitors —
    prescribing them for any other KRAS allele (e.g. q1b's G12S) would
    be clinically wrong. Returns False for unknown / non-KRAS patients.
    """
    status = get_kras_status(patient)
    return status.value.upper().replace(".", "") == "G12C"


def is_msi_high(patient: PatientProfile) -> bool:
    """True iff the patient's tumor is microsatellite-unstable / dMMR.

    Checkpoint monotherapy indication requires MSI-H / dMMR. MSS / pMMR
    patients should not receive single-agent checkpoint inhibitors.
    Reads structured MSI status from the latest oncopanel; falls back
    to `biomarkers["MSI"]` then `biomarkers["MMR"]`.
    """
    latest = get_latest_oncopanel(patient)
    if latest is not None:
        if latest.msi_status == "MSI-H" or latest.mmr_status == "dMMR":
            return True
        if latest.msi_status in ("MSS", "MSI-L") or latest.mmr_status == "pMMR":
            return False
        # unknown → fall through to legacy dict
    raw_msi = str(patient.biomarkers.get("MSI", "") if patient.biomarkers else "").upper()
    if raw_msi in ("MSI-H", "MSI_H", "MSIH", "HIGH"):
        return True
    raw_mmr = str(patient.biomarkers.get("MMR", "") if patient.biomarkers else "").upper()
    return raw_mmr in ("DMMR", "D-MMR")


def is_braf_v600e(patient: PatientProfile) -> bool:
    """True iff the patient carries a pathogenic BRAF V600E variant.

    BRAF V600E is a specific actionable mutation (encorafenib + cetuximab
    in CRC; dabrafenib + trametinib in other contexts). Any other BRAF
    status (WT, non-V600E mutant) should NOT trigger V600E-specific
    recommendations. Reads oncopanel variants first.
    """
    for variant in get_variants_for_gene(patient, "BRAF"):
        if variant.significance not in _PATHOGENIC_SIGNIFICANCES:
            continue
        short = variant.protein_short.upper().replace(".", "")
        if "V600E" in short or variant.hgvs_protein.upper().endswith("VAL600GLU)"):
            return True
    # Oncopanel says no V600E — if patient has panel at all, trust it (return False).
    if get_latest_oncopanel(patient) is not None:
        return False
    raw = str(patient.biomarkers.get("BRAF_V600E", "") if patient.biomarkers else "").lower()
    return raw in ("mutant", "positive", "v600e", "true")


def is_her2_positive(patient: PatientProfile) -> bool:
    """True iff the patient's tumor is HER2-positive (amplification).

    Matters for HER2-targeted therapy (trastuzumab, pertuzumab, T-DM1,
    T-DXd). Reads oncopanel CNVs first (look for HER2/ERBB2 amplification),
    then falls back to `biomarkers["HER2"]` for IHC/FISH-only reports.
    """
    latest = get_latest_oncopanel(patient)
    if latest is not None:
        for cnv in latest.cnvs:
            if cnv.gene.upper() in {"HER2", "ERBB2"} and cnv.alteration in {
                "amplification",
                "gain",
            }:
                return True
        # Oncopanel present but no HER2 amplification — trust it for the CNV axis.
        # Still check biomarkers dict for IHC/FISH results the panel didn't capture.
    raw = str(patient.biomarkers.get("HER2", "") if patient.biomarkers else "").lower()
    return raw in ("positive", "pos", "3+", "amplified", "amp", "her2+")


# Drug names mapped to rules
_ANTI_EGFR = {"cetuximab", "panitumumab"}
_KRAS_G12C = {"sotorasib", "adagrasib"}
_HER2_TARGETED = {"trastuzumab", "pertuzumab", "trastuzumab deruxtecan", "t-dxd"}
_BRAF_INHIBITORS = {"encorafenib", "dabrafenib", "vemurafenib"}
_CHECKPOINT_MONO = {
    "pembrolizumab",
    "nivolumab",
    "atezolizumab",
    "durvalumab",
    "ipilimumab",
}
_BEVACIZUMAB = {"bevacizumab"}
_CHEMO_NAMES = {
    "folfox",
    "folfiri",
    "capox",
    "oxaliplatin",
    "irinotecan",
    "fluorouracil",
    "capecitabine",
}
# Breast-specific drug groups (ESMO 2023 / NCCN Breast v2.2024 / FDA labels)
_PARP_INHIBITORS = {"olaparib", "talazoparib", "rucaparib", "niraparib"}
_CDK46_INHIBITORS = {"palbociclib", "ribociclib", "abemaciclib"}
_PI3K_INHIBITORS = {"alpelisib", "inavolisib"}
_AKT_INHIBITORS = {"capivasertib"}
_MTOR_INHIBITORS = {"everolimus"}
_AROMATASE_INHIBITORS = {"letrozole", "anastrozole", "exemestane"}
_SERD = {"fulvestrant", "elacestrant", "camizestrant"}
_ADC_BREAST = {
    "sacituzumab",
    "trastuzumab deruxtecan",
    "t-dxd",
    "trastuzumab emtansine",
    "t-dm1",
}


def _is_breast_patient(patient: PatientProfile | None) -> bool:
    """True if patient's diagnosis code indicates breast primary (C50.*)."""
    if patient is None or not patient.diagnosis_code:
        return False
    return patient.diagnosis_code.upper().startswith("C50")


# --- Research relevance scoring ---

# Contraindicated drug/target keywords → "not_applicable"
_CONTRAINDICATED_KEYWORDS = (
    _ANTI_EGFR | _KRAS_G12C | _HER2_TARGETED | {"anti-egfr", "anti egfr", "egfr inhibit"}
)

# High relevance: matches patient's specific profile
_HIGH_RELEVANCE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"kras\s*(?:g12\w|mutat)",
        r"(?:mcrc|metastatic\s+colorectal)",
        r"folfox",
        r"(?:first|1st|1l|first.line)\s*line",
        r"pan.kras",
        r"ras\s*mutat",
        r"left.sided\s*(?:colon|crc|colorectal)",
    ]
]

# Medium relevance: broadly related
_MEDIUM_RELEVANCE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"colorectal",
        r"\bcrc\b",
        r"colon\s*cancer",
        r"oxaliplatin",
        r"systemic\s*immune.inflammation",
        r"\bsii\b",
        r"liver\s*metast",
        r"peritoneal",
        r"anticoagul",
        r"thrombosis.*cancer",
        r"cancer.*thrombosis",
    ]
]

# Breast-specific high/medium relevance patterns.
# source: ESMO 2023 Breast Cancer Living Guideline §7; NCCN Breast v2.2024.
_BREAST_HIGH_RELEVANCE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"breast\s*(?:cancer|carcinoma)",
        r"mbc|metastatic\s*breast",
        r"hr[+\s-]*(?:positive)?",
        r"her2[-\s]*(?:low|negative|positive)",
        r"\bcdk4/6\b|cdk4/?6",
        r"aromatase\s*inhibitor",
        r"fulvestrant|letrozole|anastrozole|exemestane",
        r"palbociclib|ribociclib|abemaciclib",
        r"pi?k?3ca\s*mutat",
        r"brca1|brca2|gbrca",
        r"tnbc|triple[- ]negative",
    ]
]

_BREAST_MEDIUM_RELEVANCE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"bone\s*met",
        r"bisphosphon|denosumab|zoledron",
        r"hormone\s*(?:receptor|therapy)",
        r"endocrine\s*therap",
        r"antibody[- ]drug\s*conjugate|adc",
        r"sacituzumab|trastuzumab\s*deruxtecan|t-dxd",
        r"menopaus|goserelin",
    ]
]


@dataclass
class ResearchRelevance:
    """Result of research relevance assessment."""

    score: str  # "high", "medium", "low", "not_applicable"
    reason: str


def assess_research_relevance(
    title: str,
    summary: str | None = None,
    *,
    patient: PatientProfile | None = None,
    trial_countries: list[str] | None = None,
) -> ResearchRelevance:
    """Assess how relevant a research entry is to the patient's profile.

    Checks for contraindicated therapies (false hope), then scores
    by biomarker/treatment/disease match. When `trial_countries` is supplied
    AND the patient has an enrollment_preference, geographically inaccessible
    trials are down-ranked to "low" with a geography-specific reason (#394).
    """
    # Geography pre-filter (#394) — runs before biomarker rules so an anti-EGFR
    # trial in Houston still gets "not_applicable" for contraindication (the
    # more useful signal for the physician), but an otherwise-relevant trial
    # in an excluded country is correctly downgraded to "low".
    geography_downgrade: ResearchRelevance | None = None
    if trial_countries and patient is not None and patient.enrollment_preference is not None:
        pref = patient.enrollment_preference
        preferred = {c.upper() for c in pref.preferred_countries}
        excluded = {c.upper() for c in pref.excluded_countries}
        tc = {(c or "").upper() for c in trial_countries if c}
        if tc:
            has_preferred = bool(tc & preferred)
            all_excluded = bool(tc) and tc.issubset(excluded)
            if all_excluded:
                geography_downgrade = ResearchRelevance(
                    score="not_applicable",
                    reason="Trial sites in excluded countries — not enrollable",
                )
            elif not has_preferred and not pref.allow_unique_opportunity_global:
                geography_downgrade = ResearchRelevance(
                    score="low",
                    reason=(
                        f"Trial sites ({', '.join(sorted(tc))}) outside"
                        f" preferred countries — not enrollable"
                    ),
                )

    text = (title + " " + (summary or "")).lower()
    words = set(re.findall(r"[a-z][a-z0-9-]+", text))

    if _is_breast_patient(patient):
        return _assess_breast_relevance(text, words, patient)

    # #398: read biomarker values through the structured helpers so research
    # relevance reasoning sees the precise allele (e.g. q1b's KRAS G12S) via
    # oncopanel rather than stale / string-level dict data.
    if patient is not None:
        kras_val = get_kras_status(patient).value
        if kras_val == "unknown":
            kras_val = "mutant"
    else:
        kras_val = "G12S"
    her2_val = (patient.biomarkers.get("HER2", "") if patient else "negative") or "negative"

    # Rule 1: Contraindicated — false hope detection
    matched_contra = _CONTRAINDICATED_KEYWORDS & words
    if matched_contra:
        # Check if it's specifically about KRAS G12C — only contraindicated for
        # non-G12C patients. A G12C-carrying patient stays eligible.
        if matched_contra & _KRAS_G12C and (patient is None or not has_kras_g12c(patient)):
            return ResearchRelevance(
                score="not_applicable",
                reason=f"KRAS G12C inhibitor — patient has {kras_val}, not G12C",
            )
        if matched_contra & (_ANTI_EGFR | {"anti-egfr", "anti egfr", "egfr inhibit"}):
            # KRAS WT patients can receive anti-EGFR — only contraindicated when mutant.
            kras_wt = (
                patient is not None
                and get_kras_status(patient).value.upper() == "WT"
                and get_kras_status(patient).source.startswith("oncopanel")
            )
            if not kras_wt:
                return ResearchRelevance(
                    score="not_applicable",
                    reason=f"Anti-EGFR therapy — contraindicated (KRAS {kras_val})",
                )
        if matched_contra & _HER2_TARGETED and (patient is None or not is_her2_positive(patient)):
            return ResearchRelevance(
                score="not_applicable",
                reason=f"HER2-targeted therapy — patient is HER2 {her2_val}",
            )

    # Rule 1b: Later-line trials — patient is on 1L, these are 2L/3L+
    _later_line_re = re.compile(
        r"(?:second|third|2nd|3rd|2l|3l|later)\s*(?:-?\s*)?line"
        r"|previously\s+treated"
        r"|refractory"
        r"|after\s+(?:progression|failure)\s+(?:on|of)"
        r"|post[- ]?progression"
        r"|salvage\s+therap",
        re.IGNORECASE,
    )
    if _later_line_re.search(text):
        # Still relevant but not for current line — medium relevance with annotation
        return ResearchRelevance(
            score="medium",
            reason="Later-line trial (2L/3L+) — patient is on 1st line",
        )

    # Check for checkpoint monotherapy in MSS context
    checkpoint_words = _CHECKPOINT_MONO & words
    if checkpoint_words:
        has_combo = bool(words & _CHEMO_NAMES) or "combin" in text
        if not has_combo and ("mss" in text or "microsatellite stable" in text):
            return ResearchRelevance(
                score="not_applicable",
                reason="Checkpoint monotherapy for MSS — not indicated (pMMR/MSS)",
            )

    # Rule 2: High relevance — specific profile match
    for pattern in _HIGH_RELEVANCE_PATTERNS:
        if pattern.search(text):
            # Geography gate (#394): even a high profile match gets downgraded
            # if the trial is not enrollable. Physician still sees it, just
            # sorted lower so WA/briefing pushes focus on actionable trials.
            if geography_downgrade is not None:
                return geography_downgrade
            return ResearchRelevance(
                score="high",
                reason=f"Matches patient profile: {pattern.pattern}",
            )

    # Rule 3: Medium relevance — broadly related
    for pattern in _MEDIUM_RELEVANCE_PATTERNS:
        if pattern.search(text):
            if geography_downgrade is not None:
                return geography_downgrade
            return ResearchRelevance(
                score="medium",
                reason=f"Related to patient's condition: {pattern.pattern}",
            )

    # Rule 4: Low relevance — no specific match
    if geography_downgrade is not None:
        return geography_downgrade
    return ResearchRelevance(
        score="low",
        reason="No specific match to patient's biomarkers or treatment",
    )


def _drugs_in_trial(trial: ClinicalTrial) -> set[str]:
    """Extract lowercase drug names from interventions + eligibility text."""
    text = " ".join(trial.interventions) + " " + trial.eligibility_criteria
    return {w.lower() for w in re.findall(r"[a-zA-Z]\w+", text)}


def _fmt(names: set[str]) -> str:
    return ", ".join(sorted(names))


def check_eligibility(
    trial: ClinicalTrial,
    patient: PatientProfile,
) -> EligibilityResult:
    """Check trial eligibility against patient's molecular and clinical profile.

    Applies tumor-type-specific rules: breast (C50.*) uses the breast rule set
    (ER/PR/HER2/BRCA/PIK3CA), colorectal/default uses the KRAS/NRAS/BRAF/MSI
    rule set. Rules from `reference_clinical-protocol-sources.md`.
    """
    if _is_breast_patient(patient):
        return _check_breast_eligibility(trial, patient)

    flags: list[EligibilityFlag] = []
    warnings: list[str] = []
    drugs = _drugs_in_trial(trial)

    # #398: read biomarker status through the structured helpers so any patient
    # with a current oncopanel gets the precise allele/status (e.g. q1b KRAS G12S
    # not just "mutant"). Falls back to the flat biomarkers dict for patients
    # without structured panel data — existing single-patient flows unaffected.
    kras_status = get_kras_status(patient)
    kras_val = kras_status.value if kras_status.value != "unknown" else "mutant"
    her2_val = patient.biomarkers.get("HER2", "negative") or "negative"
    braf_val = patient.biomarkers.get("BRAF_V600E", "wild-type") or "wild-type"
    msi_val = patient.biomarkers.get("MSI", "pMMR/MSS") or "pMMR/MSS"

    # Rule 1: KRAS mutant -> no anti-EGFR. Skip the exclusion for KRAS WT
    # patients (oncopanel-confirmed) since they may actually benefit from
    # anti-EGFR therapy. q1b is KRAS G12S mutant so behavior unchanged.
    matched = _ANTI_EGFR & drugs
    kras_is_wt = kras_status.source.startswith("oncopanel") and kras_val.upper() == "WT"
    if matched and not kras_is_wt:
        flags.append(
            EligibilityFlag(
                rule="KRAS_anti_EGFR",
                status="excluded",
                reason=f"Anti-EGFR ({_fmt(matched)}) contraindicated — KRAS {kras_val}",
            )
        )

    # Rule 2: KRAS G12C-specific drugs only for G12C. Now actually respects
    # the patient's allele — G12C patients are NOT excluded from G12C drugs.
    matched = _KRAS_G12C & drugs
    if matched and not has_kras_g12c(patient):
        flags.append(
            EligibilityFlag(
                rule="KRAS_not_G12C",
                status="excluded",
                reason=(
                    f"KRAS G12C inhibitors ({_fmt(matched)}) not applicable"
                    f" — patient has {kras_val}"
                ),
            )
        )

    # Rule 3: pMMR/MSS -> checkpoint monotherapy not indicated. Now respects
    # MSI-H/dMMR patients who SHOULD receive checkpoint monotherapy.
    checkpoint_found = _CHECKPOINT_MONO & drugs
    if checkpoint_found and not is_msi_high(patient):
        has_chemo = bool(drugs & _CHEMO_NAMES)
        if not has_chemo and len(trial.interventions) <= 2:
            flags.append(
                EligibilityFlag(
                    rule="pMMR_MSS_checkpoint_mono",
                    status="excluded",
                    reason=(
                        f"Checkpoint monotherapy ({_fmt(checkpoint_found)})"
                        f" not indicated — {msi_val}"
                    ),
                )
            )
        else:
            warnings.append(
                f"Checkpoint inhibitor ({_fmt(checkpoint_found)})"
                f" in combination — acceptable for {msi_val},"
                " monitor response"
            )

    # Rule 4: HER2 negative -> no HER2-targeted therapy. HER2-positive
    # patients (oncopanel CNV amplification or IHC 3+) stay eligible.
    matched = _HER2_TARGETED & drugs
    if matched and not is_her2_positive(patient):
        flags.append(
            EligibilityFlag(
                rule="HER2_negative",
                status="excluded",
                reason=f"HER2-targeted therapy ({_fmt(matched)}) not indicated — HER2 {her2_val}",
            )
        )

    # Rule 5: BRAF wild-type -> no BRAF inhibitors alone. V600E-positive
    # patients stay eligible for BRAF-targeted therapy.
    matched = _BRAF_INHIBITORS & drugs
    if matched and not is_braf_v600e(patient):
        flags.append(
            EligibilityFlag(
                rule="BRAF_wildtype",
                status="excluded",
                reason=f"BRAF inhibitors ({_fmt(matched)}) not indicated — BRAF V600E {braf_val}",
            )
        )

    # Rule 6: Active VTE -> bevacizumab high risk
    if _BEVACIZUMAB & drugs:
        has_vte = any(
            "thrombosis" in c.lower() or "vte" in c.lower() for c in patient.comorbidities
        )
        if has_vte:
            vte_detail = next(
                (
                    c
                    for c in patient.comorbidities
                    if "thrombosis" in c.lower() or "vte" in c.lower()
                ),
                "active VTE",
            )
            flags.append(
                EligibilityFlag(
                    rule="VTE_bevacizumab",
                    status="warning",
                    reason=f"Bevacizumab HIGH RISK — {vte_detail}",
                )
            )
            warnings.append("Active VTE + bevacizumab requires oncologist discussion")

    excluded = any(f.status == "excluded" for f in flags)
    eligible = not excluded

    # Build summary
    if not flags and not warnings:
        summary = f"No biomarker contraindications found for {trial.nct_id}."
    else:
        parts = []
        if excluded:
            excl = [f for f in flags if f.status == "excluded"]
            parts.append(f"{len(excl)} exclusion(s): " + "; ".join(f.reason for f in excl))
        warn_flags = [f for f in flags if f.status == "warning"]
        if warn_flags or warnings:
            parts.append(f"{len(warn_flags) + len(warnings)} warning(s)")
        summary = ". ".join(parts)

    return EligibilityResult(
        nct_id=trial.nct_id,
        eligible=eligible,
        flags=flags,
        warnings=warnings,
        summary=summary,
    )


# ── Breast-specific helpers (C50.*) ──────────────────────────────────
# source: ESMO 2023 Breast Cancer Living Guideline §7; NCCN Breast v2.2024;
# FDA drug labels for each targeted agent.


def _assess_breast_relevance(
    text: str,
    words: set[str],
    patient: PatientProfile | None,
) -> ResearchRelevance:
    """Relevance for breast-cancer patients. Flags false-hope cases based on
    actual biomarker status (HER2, HR, BRCA, PIK3CA) rather than mCRC defaults.
    """
    biomarkers = patient.biomarkers if patient else {}
    her2_val = (biomarkers.get("HER2", "") or "").lower()
    hr_val = (biomarkers.get("HR", "") or "").lower()
    er_val = (biomarkers.get("ER", "") or "").lower()
    brca1 = (biomarkers.get("BRCA1", "") or "").lower()
    brca2 = (biomarkers.get("BRCA2", "") or "").lower()
    pik3ca = (biomarkers.get("PIK3CA", "") or "").lower()

    her2_negative = "negative" in her2_val
    hr_positive = "positive" in hr_val or "positive" in er_val
    brca_mut = any(
        v and v not in {"unknown", "wild-type", "wt", "negative"} for v in [brca1, brca2]
    )
    pik3ca_mut = bool(pik3ca and pik3ca not in {"unknown", "wild-type", "wt", "negative"})

    # False-hope: trastuzumab-only trials for HER2-negative (T-DXd HER2-low allowed)
    her2_matched = _HER2_TARGETED & words
    if her2_matched and her2_negative:
        her2_low_trial = "her2-low" in text or "her2 low" in text or "low her2" in text
        if not her2_low_trial and not ({"trastuzumab deruxtecan", "t-dxd"} & her2_matched):
            return ResearchRelevance(
                score="not_applicable",
                reason=f"HER2-targeted therapy — patient HER2 {her2_val or 'negative'}",
            )

    # PARP inhibitor: only relevant if BRCA-mutated
    parp_matched = _PARP_INHIBITORS & words
    if parp_matched and not brca_mut:
        brca_status = brca1 or brca2 or "unknown"
        return ResearchRelevance(
            score="medium",
            reason=f"PARP inhibitor — BRCA status {brca_status}, confirm before eligibility",
        )

    # Alpelisib / inavolisib: PIK3CA-mutant only
    pi3k_matched = _PI3K_INHIBITORS & words
    if pi3k_matched and not pik3ca_mut:
        return ResearchRelevance(
            score="medium",
            reason="PI3K inhibitor — confirm PIK3CA mutation status before eligibility",
        )

    # High relevance: breast-specific patterns
    for pattern in _BREAST_HIGH_RELEVANCE_PATTERNS:
        if pattern.search(text):
            return ResearchRelevance(
                score="high",
                reason=f"Matches breast profile: {pattern.pattern}",
            )

    # CDK4/6 is high relevance for HR+
    if hr_positive and _CDK46_INHIBITORS & words:
        return ResearchRelevance(
            score="high",
            reason="CDK4/6 inhibitor — HR+ breast cancer",
        )

    # Medium relevance: bone mets / endocrine / ADC
    for pattern in _BREAST_MEDIUM_RELEVANCE_PATTERNS:
        if pattern.search(text):
            return ResearchRelevance(
                score="medium",
                reason=f"Related to breast-patient care: {pattern.pattern}",
            )

    return ResearchRelevance(
        score="low",
        reason="No specific match to breast-cancer biomarkers or treatment",
    )


def _check_breast_eligibility(
    trial: ClinicalTrial,
    patient: PatientProfile,
) -> EligibilityResult:
    """Breast-specific trial eligibility: HER2, HR, BRCA, PIK3CA."""
    flags: list[EligibilityFlag] = []
    warnings: list[str] = []
    drugs = _drugs_in_trial(trial)
    text = " ".join(trial.interventions) + " " + trial.eligibility_criteria

    biomarkers = patient.biomarkers
    her2_val = (biomarkers.get("HER2", "") or "").lower()
    hr_val = (biomarkers.get("HR", "") or "").lower()
    er_val = (biomarkers.get("ER", "") or "").lower()
    brca1 = (biomarkers.get("BRCA1", "") or "").lower()
    brca2 = (biomarkers.get("BRCA2", "") or "").lower()
    pik3ca = (biomarkers.get("PIK3CA", "") or "").lower()

    her2_negative = "negative" in her2_val
    hr_positive = "positive" in hr_val or "positive" in er_val
    brca_mut = any(
        v and v not in {"unknown", "wild-type", "wt", "negative"} for v in [brca1, brca2]
    )
    pik3ca_mut = bool(pik3ca and pik3ca not in {"unknown", "wild-type", "wt", "negative"})

    # Rule B1: HER2-targeted therapy requires HER2+ (or HER2-low for T-DXd)
    matched = _HER2_TARGETED & drugs
    if matched and her2_negative:
        is_tdxd = bool(matched & {"trastuzumab deruxtecan", "t-dxd"})
        her2_low_trial = "her2-low" in text.lower() or "her2 low" in text.lower()
        if not (is_tdxd and her2_low_trial):
            flags.append(
                EligibilityFlag(
                    rule="HER2_negative",
                    status="excluded",
                    reason=(
                        f"HER2-targeted therapy ({_fmt(matched)}) not indicated — "
                        f"HER2 {her2_val or 'negative'}"
                    ),
                )
            )

    # Rule B2: PARP inhibitors require BRCA mutation
    matched = _PARP_INHIBITORS & drugs
    if matched and not brca_mut:
        brca_status = brca1 or brca2 or "unknown"
        flags.append(
            EligibilityFlag(
                rule="BRCA_PARP",
                status="warning" if brca_status == "unknown" else "excluded",
                reason=(
                    f"PARP inhibitor ({_fmt(matched)}) requires BRCA1/2 mutation — "
                    f"patient BRCA status: {brca_status}"
                ),
            )
        )

    # Rule B3: PI3K inhibitors require PIK3CA mutation
    matched = _PI3K_INHIBITORS & drugs
    if matched and not pik3ca_mut:
        pik3ca_status = pik3ca or "unknown"
        flags.append(
            EligibilityFlag(
                rule="PIK3CA_PI3K",
                status="warning" if pik3ca_status == "unknown" else "excluded",
                reason=(
                    f"PI3K inhibitor ({_fmt(matched)}) requires PIK3CA mutation — "
                    f"status: {pik3ca_status}"
                ),
            )
        )

    # Rule B4: CDK4/6 — informational (ribociclib QTc warning per FDA label)
    matched = _CDK46_INHIBITORS & drugs
    if matched and "ribociclib" in matched:
        warnings.append("Ribociclib: baseline + month 1 ECG required (FDA label §5.3)")

    # Rule B5: Active VTE + any monoclonal antibody — caution
    has_vte = any("thrombosis" in c.lower() or "vte" in c.lower() for c in patient.comorbidities)
    if has_vte and (drugs & _BEVACIZUMAB):
        flags.append(
            EligibilityFlag(
                rule="VTE_bevacizumab",
                status="warning",
                reason="Bevacizumab HIGH RISK — active VTE (rare in breast protocols)",
            )
        )

    # Rule B6: HR-negative / triple-negative patient with endocrine therapy
    if not hr_positive and (drugs & (_AROMATASE_INHIBITORS | _SERD | _CDK46_INHIBITORS)):
        flags.append(
            EligibilityFlag(
                rule="HR_negative_endocrine",
                status="excluded",
                reason=(f"Endocrine therapy requires HR+ — patient HR {hr_val or 'negative'}"),
            )
        )

    excluded = any(f.status == "excluded" for f in flags)
    eligible = not excluded

    if not flags and not warnings:
        summary = f"No biomarker contraindications found for {trial.nct_id}."
    else:
        parts = []
        if excluded:
            excl = [f for f in flags if f.status == "excluded"]
            parts.append(f"{len(excl)} exclusion(s): " + "; ".join(f.reason for f in excl))
        warn_flags = [f for f in flags if f.status == "warning"]
        if warn_flags or warnings:
            parts.append(f"{len(warn_flags) + len(warnings)} warning(s)")
        summary = ". ".join(parts)

    return EligibilityResult(
        nct_id=trial.nct_id,
        eligible=eligible,
        flags=flags,
        warnings=warnings,
        summary=summary,
    )
