from __future__ import annotations

import asyncio

import httpx

from .config import CTGOV_BASE_URL
from .models import ClinicalTrial

# Adjacent countries for SK patient (ordered by proximity to Bratislava)
ADJACENT_COUNTRIES = ["Slovakia", "Czech Republic", "Austria", "Hungary"]


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

    return _parse_studies(data)


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

    return combined


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
