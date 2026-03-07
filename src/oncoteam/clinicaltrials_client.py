from __future__ import annotations

import asyncio

import httpx

from .config import CTGOV_BASE_URL
from .models import ClinicalTrial

# Adjacent countries for SK patient (ordered by proximity to Bratislava)
ADJACENT_COUNTRIES = ["Slovakia", "Czech Republic", "Austria", "Hungary"]

# CRC relevance filter — exclude non-CRC conditions and G12C-specific interventions
_EXCLUDE_CONDITIONS = {
    "pediatric",
    "hepatocellular",
    "biliary",
    "cholangiocarcinoma",
    "pancreatic",
    "gastric",
    "esophageal",
    "breast",
    "lung",
    "prostate",
}
_EXCLUDE_INTERVENTIONS = {"sotorasib", "adagrasib"}


def _is_crc_relevant(trial: ClinicalTrial) -> bool:
    """Return True if trial is relevant for CRC (excludes other cancer types and G12C drugs)."""
    conds = " ".join(trial.conditions).lower()
    intrs = " ".join(trial.interventions).lower()
    if any(exc in conds for exc in _EXCLUDE_CONDITIONS):
        return False
    return not any(exc in intrs for exc in _EXCLUDE_INTERVENTIONS)


async def fetch_trial(nct_id: str) -> ClinicalTrial | None:
    """Fetch a single trial by NCT ID from ClinicalTrials.gov API v2."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{CTGOV_BASE_URL}/studies/{nct_id}", params={"format": "json"})
        resp.raise_for_status()
        data = resp.json()

    proto = data.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status_mod = proto.get("statusModule", {})
    design = proto.get("designModule", {})
    conditions_mod = proto.get("conditionsModule", {})
    interventions_mod = proto.get("armsInterventionsModule", {})
    locations_mod = proto.get("contactsLocationsModule", {})
    desc = proto.get("descriptionModule", {})
    elig_mod = proto.get("eligibilityModule", {})

    phases = design.get("phases", [])
    interventions = [
        intr.get("name", "")
        for intr in interventions_mod.get("interventions", [])
        if intr.get("name")
    ]
    locations = [
        loc.get("facility", "") for loc in locations_mod.get("locations", []) if loc.get("facility")
    ]

    return ClinicalTrial(
        nct_id=ident.get("nctId", nct_id),
        title=ident.get("briefTitle", ""),
        status=status_mod.get("overallStatus", ""),
        phase=", ".join(phases) if phases else "",
        conditions=conditions_mod.get("conditions", []),
        interventions=interventions,
        locations=locations,
        summary=desc.get("briefSummary", ""),
        eligibility_criteria=elig_mod.get("eligibilityCriteria", ""),
    )


async def search_trials(
    condition: str,
    intervention: str | None = None,
    max_results: int = 10,
    country: str | None = None,
) -> list[ClinicalTrial]:
    """Search ClinicalTrials.gov API v2 for recruiting studies."""
    params: dict = {
        "query.cond": condition,
        "filter.overallStatus": "RECRUITING",
        "pageSize": min(max_results, 100),
        "format": "json",
        "fields": (
            "NCTId,BriefTitle,OverallStatus,Phase,Condition,"
            "InterventionName,LocationFacility,BriefSummary"
        ),
    }
    if intervention:
        params["query.intr"] = intervention
    if country:
        params["query.locn"] = country

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{CTGOV_BASE_URL}/studies", params=params)
        resp.raise_for_status()
        data = resp.json()

    return [t for t in _parse_studies(data) if _is_crc_relevant(t)]


async def search_trials_adjacent(
    condition: str,
    intervention: str | None = None,
    max_per_country: int = 5,
) -> list[ClinicalTrial]:
    """Search recruiting trials across SK and adjacent countries.

    Searches Slovakia, Czech Republic, Austria, and Hungary in parallel.
    Deduplicates by NCT ID and returns combined results.
    """
    tasks = [
        search_trials(condition, intervention, max_per_country, country)
        for country in ADJACENT_COUNTRIES
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    seen_nct: set[str] = set()
    combined: list[ClinicalTrial] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        for trial in result:
            if trial.nct_id not in seen_nct:
                seen_nct.add(trial.nct_id)
                combined.append(trial)

    return [t for t in combined if _is_crc_relevant(t)]


def _parse_studies(data: dict) -> list[ClinicalTrial]:
    """Parse ClinicalTrials.gov v2 JSON response."""
    trials = []
    for study in data.get("studies", []):
        proto = study.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        status_mod = proto.get("statusModule", {})
        design = proto.get("designModule", {})
        conditions_mod = proto.get("conditionsModule", {})
        interventions_mod = proto.get("armsInterventionsModule", {})
        locations_mod = proto.get("contactsLocationsModule", {})
        desc = proto.get("descriptionModule", {})

        nct_id = ident.get("nctId", "")
        title = ident.get("briefTitle", "")
        status = status_mod.get("overallStatus", "")

        phases = design.get("phases", [])
        phase = ", ".join(phases) if phases else ""

        conditions = conditions_mod.get("conditions", [])

        interventions = []
        for intr in interventions_mod.get("interventions", []):
            name = intr.get("name", "")
            if name:
                interventions.append(name)

        locations = []
        for loc in locations_mod.get("locations", []):
            facility = loc.get("facility", "")
            if facility:
                locations.append(facility)

        summary = desc.get("briefSummary", "")

        trials.append(
            ClinicalTrial(
                nct_id=nct_id,
                title=title,
                status=status,
                phase=phase,
                conditions=conditions,
                interventions=interventions,
                locations=locations,
                summary=summary,
            )
        )

    return trials
