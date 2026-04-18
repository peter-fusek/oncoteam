from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class ResearchSource(StrEnum):
    PUBMED = "pubmed"
    CLINICALTRIALS = "clinicaltrials"
    MANUAL = "manual"


class ActivityStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


class EventType(StrEnum):
    CHEMO_CYCLE = "chemo_cycle"
    LAB_WORK = "lab_work"
    CONSULTATION = "consultation"
    SURGERY = "surgery"
    SCAN = "scan"


class PubMedArticle(BaseModel):
    pmid: str
    title: str
    abstract: str = ""
    authors: list[str] = Field(default_factory=list)
    journal: str = ""
    pub_date: str = ""
    doi: str = ""


class ClinicalTrial(BaseModel):
    nct_id: str
    title: str
    status: str = ""
    phase: str = ""
    conditions: list[str] = Field(default_factory=list)
    interventions: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    summary: str = ""
    eligibility_criteria: str = ""


class HomeRegion(BaseModel):
    """Patient's home location — drives trial enrollment geography.

    ISO alpha-2 country codes. Coords in decimal degrees (WGS84).
    """

    city: str
    country: str
    lat: float
    lon: float
    healthcare_system: str = ""


class EnrollmentPreference(BaseModel):
    """Patient preferences for clinical trial enrollment.

    Agents filter + rank trials by proximity before biomarker match so we
    never push non-enrollable trials. See issue #394 for policy details.
    """

    max_travel_km: int = 600
    preferred_countries: list[str] = Field(default_factory=list)
    language_preferences: list[str] = Field(default_factory=list)
    excluded_countries: list[str] = Field(default_factory=list)
    allow_unique_opportunity_global: bool = False


class TrialSite(BaseModel):
    """A single clinical trial site.

    Distance-from-home is computed at ranking time, not stored.
    """

    country: str
    city: str = ""
    facility: str = ""
    status: str = ""
    lat: float | None = None
    lon: float | None = None
    contact: str = ""


class PatientProfile(BaseModel):
    patient_id: str = ""  # Unique ID (e.g. "q1b"). Empty = legacy single-patient.
    name: str
    diagnosis_code: str
    diagnosis_description: str
    tumor_site: str
    biomarkers: dict[str, str | bool] = Field(default_factory=dict)
    treatment_regimen: str
    hospitals: list[str] = Field(default_factory=list)
    diagnosis_date: date | None = None
    notes: str = ""
    # Extended clinical fields
    staging: str = ""
    histology: str = ""
    tumor_laterality: str = ""
    metastases: list[str] = Field(default_factory=list)
    comorbidities: list[str] = Field(default_factory=list)
    surgeries: list[dict] = Field(default_factory=list)
    treating_physician: str = ""
    admitting_physician: str = ""
    baseline_weight_kg: float | None = None
    current_cycle: int | None = None
    ecog: str = ""
    excluded_therapies: dict[str, str] = Field(default_factory=dict)
    patient_ids: dict[str, str] = Field(default_factory=dict)
    active_therapies: list[dict] = Field(default_factory=list)
    agent_whitelist: list[str] = Field(default_factory=list)  # empty = all agents
    # Enrollment geography (#394)
    home_region: HomeRegion | None = None
    enrollment_preference: EnrollmentPreference | None = None


class ResearchEntry(BaseModel):
    source: ResearchSource
    external_id: str = ""
    title: str
    summary: str = ""
    relevance_score: float = 0.0
    tags: list[str] = Field(default_factory=list)


class EligibilityFlag(BaseModel):
    rule: str
    status: str  # "excluded", "warning", "eligible"
    reason: str


class EligibilityResult(BaseModel):
    nct_id: str
    eligible: bool
    flags: list[EligibilityFlag] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: str = ""


class TreatmentEvent(BaseModel):
    event_date: str
    event_type: EventType
    title: str
    notes: str = ""
    metadata: dict | None = None
