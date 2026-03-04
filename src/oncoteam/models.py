from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class ResearchSource(StrEnum):
    PUBMED = "pubmed"
    CLINICALTRIALS = "clinicaltrials"
    MANUAL = "manual"


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


class PatientProfile(BaseModel):
    name: str
    diagnosis_code: str
    diagnosis_description: str
    tumor_site: str
    biomarkers: dict[str, str] = Field(default_factory=dict)
    treatment_regimen: str
    hospitals: list[str] = Field(default_factory=list)
    diagnosis_date: date | None = None
    notes: str = ""


class ResearchEntry(BaseModel):
    source: ResearchSource
    external_id: str = ""
    title: str
    summary: str = ""
    relevance_score: float = 0.0
    tags: list[str] = Field(default_factory=list)


class TreatmentEvent(BaseModel):
    event_date: str
    event_type: EventType
    title: str
    notes: str = ""
    metadata: dict | None = None
