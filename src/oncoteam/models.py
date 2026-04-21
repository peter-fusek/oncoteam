from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Timezone-aware UTC now. `datetime.utcnow()` is deprecated in Python 3.12+."""
    return datetime.now(UTC)


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


# ── Structured oncopanel (#398) ────────────────────────────────────────


class OncopanelVariant(BaseModel):
    """Single variant from a somatic oncopanel report.

    Source traceability: every variant references the document + page it was
    extracted from so clinicians can verify against the original report.
    """

    gene: str
    ref_seq: str = ""
    hgvs_cdna: str = ""
    hgvs_protein: str = ""
    protein_short: str = ""
    vaf: float | None = None  # 0.0-1.0 (e.g. 0.1281 for 12.81%)
    variant_type: Literal["SNV", "indel", "splice", "frameshift", "CNV", "fusion", "other"] = "SNV"
    tier: str = ""  # "IA" | "IB" | "IIC" | "IID" | "III"
    classification: Literal["somatic", "germline", "unknown"] = "somatic"
    significance: Literal[
        "pathogenic", "likely_pathogenic", "vus", "likely_benign", "benign", "unknown"
    ] = "unknown"
    source_document_id: str = ""
    source_page: int | None = None
    notes: str = ""
    # Physician review state (populated via #395 audit path)
    reviewed_by: str = ""
    reviewed_at: datetime | None = None
    reviewed_status: Literal["unreviewed", "accepted", "flagged", "dismissed"] = "unreviewed"
    reviewed_rationale: str = ""


class CopyNumberVariant(BaseModel):
    gene: str
    alteration: Literal["amplification", "deletion", "loss", "gain"]
    copies: int | None = None
    source_document_id: str = ""
    source_page: int | None = None
    notes: str = ""


class Oncopanel(BaseModel):
    """A single oncopanel report. Patients can have multiple over time (versioned)."""

    panel_id: str
    patient_id: str
    sample_date: date | None = None
    report_date: date | None = None
    lab: str = ""
    sample_type: Literal["tumor_tissue", "ctDNA", "germline", "mixed"] = "tumor_tissue"
    methodology: str = ""
    variants: list[OncopanelVariant] = Field(default_factory=list)
    cnvs: list[CopyNumberVariant] = Field(default_factory=list)
    msi_status: Literal["MSS", "MSI-L", "MSI-H", "unknown"] = "unknown"
    mmr_status: Literal["pMMR", "dMMR", "unknown"] = "unknown"
    tmb_score: float | None = None
    tmb_category: Literal["low", "intermediate", "high", "unknown"] = "unknown"
    quality_metrics: dict = Field(default_factory=dict)
    source_document_id: str = ""
    # Report-level physician verification
    verified_by: str = ""
    verified_at: datetime | None = None
    verified_status: Literal["unreviewed", "approved", "queried", "superseded"] = "unreviewed"
    verification_notes: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


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
    # Non-destructive pause: scheduler + document webhook skip, data intact.
    # Flip to False and restart to resume. Overridable via PAUSED_PATIENTS env.
    paused: bool = False
    # Notification policy (#391) — gates WhatsApp admin push. "silent" is the
    # default so parity-onboarded / read-only patients don't spam Peter's
    # inbox with agent-run notifications they aren't acting on. Agents still
    # run + persist data to oncofiles; only the push is suppressed.
    #   silent         — no WhatsApp push (dashboard surfaces only)
    #   admin          — push to admin role (caregiver/advocate) — no patient
    #   patient+admin  — push to both admin and the patient's own phone
    notification_policy: Literal["silent", "admin", "patient+admin"] = "silent"
    # Enrollment geography (#394)
    home_region: HomeRegion | None = None
    enrollment_preference: EnrollmentPreference | None = None
    # Structured oncopanel history (#398) — newest last; append, never overwrite
    oncopanel_history: list[Oncopanel] = Field(default_factory=list)


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


# ── Clinical funnel two-lane architecture (#395) ────────────────────────
#
# Trust model: agents write to the PROPOSAL lane; physicians write to the
# CLINICAL lane. The audit log is append-only — every state change produces
# an immutable FunnelAuditEvent. Corrections never delete events; they
# append a new event with event_type="correction". See docs/clinical_decision_audit.md.


class FunnelLane(StrEnum):
    PROPOSAL = "proposal"
    CLINICAL = "clinical"


class FunnelActorType(StrEnum):
    HUMAN = "human"
    AGENT = "agent"


class FunnelEventType(StrEnum):
    CREATED = "created"
    VIEWED = "viewed"
    MOVED = "moved"
    COMMENTED = "commented"
    ARCHIVED = "archived"
    SUGGESTED = "suggested"
    PROMOTED_FROM_PROPOSAL = "promoted_from_proposal"
    RE_SURFACED = "re_surfaced"
    CORRECTION = "correction"
    MIGRATED_FROM_V1 = "migrated_from_v1"
    KANBAN_RESET = "kanban_reset"


# Events that change card state — rationale is required for these.
FUNNEL_STATE_CHANGING_EVENTS: frozenset[FunnelEventType] = frozenset(
    {
        FunnelEventType.MOVED,
        FunnelEventType.ARCHIVED,
        FunnelEventType.PROMOTED_FROM_PROPOSAL,
        FunnelEventType.KANBAN_RESET,
    }
)

# Events that agents are ALLOWED to produce. All others require a human actor.
FUNNEL_AGENT_ALLOWED_EVENTS: frozenset[FunnelEventType] = frozenset(
    {
        FunnelEventType.CREATED,  # proposals only — enforced at API layer
        FunnelEventType.SUGGESTED,
        FunnelEventType.RE_SURFACED,
    }
)


class FunnelAuditEvent(BaseModel):
    """Append-only audit event for a funnel card.

    `frozen=True` makes the instance immutable after construction — a defense-
    in-depth guarantee on top of the API-level "never delete" invariant.
    Validators enforce: state-changing events require rationale; agents cannot
    produce state-changing events.
    """

    model_config = {"frozen": True}

    event_id: str  # UUID4
    card_id: str
    nct_id: str
    patient_id: str
    actor_type: FunnelActorType
    actor_id: str
    actor_display_name: str
    event_type: FunnelEventType
    from_stage: str | None = None
    to_stage: str | None = None
    rationale: str = ""
    metadata: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)
    session_id: str = ""

    def model_post_init(self, __context) -> None:
        """Enforce the two invariants from #395 at construction time."""
        # Invariant 1: state-changing events require rationale.
        if self.event_type in FUNNEL_STATE_CHANGING_EVENTS and not self.rationale.strip():
            raise ValueError(
                f"event_type={self.event_type} is state-changing; rationale is required"
            )
        # Invariant 2: agents can only produce the allow-listed event types.
        if (
            self.actor_type == FunnelActorType.AGENT
            and self.event_type not in FUNNEL_AGENT_ALLOWED_EVENTS
        ):
            raise ValueError(
                f"actor_type=agent cannot produce event_type={self.event_type};"
                " agents may only CREATE proposals, SUGGEST, or flag RE_SURFACED"
            )


class FunnelClinicalVerification(BaseModel):
    """Physician sign-off metadata attached to a clinical-lane card."""

    reviewed_by: str = ""
    reviewed_at: datetime | None = None
    approved: bool = False
    notes: str = ""


class FunnelCard(BaseModel):
    """A single card in the two-lane funnel.

    `lane` drives write permissions: proposal-lane cards are agent-writable,
    clinical-lane cards are physician-writable. A card's lane never silently
    changes — the only transition is `promoted_from_proposal`, which creates
    a NEW clinical-lane card and archives the proposal with an audit event.
    """

    card_id: str  # e.g. "q1b_NCT04657068_proposal" or "q1b_NCT04657068"
    patient_id: str
    nct_id: str
    lane: FunnelLane
    current_stage: str  # lane-specific vocabulary; validated at API layer
    title: str = ""
    biomarker_match: dict = Field(default_factory=dict)
    geographic_score: float | None = None  # from #394; None when not scored
    sites_in_scope: list[TrialSite] = Field(default_factory=list)
    ai_suggestions: list[dict] = Field(default_factory=list)
    source_agent: str = ""  # which agent first created the proposal
    source_run_id: str = ""
    proposal_ttl_expires_at: datetime | None = None  # None in clinical lane
    duplicate_of_card_id: str | None = None  # re-surfacing flag
    clinical_verification: FunnelClinicalVerification | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# Stage vocabularies per lane. Keep PROPOSAL_STAGES minimal — agents only
# create cards in "new"; physician promotion bumps them out of the proposal
# lane entirely. CLINICAL_STAGES is the full 5-stage kanban.
PROPOSAL_STAGES: tuple[str, ...] = ("new", "dismissed", "expired")
CLINICAL_STAGES: tuple[str, ...] = (
    "Watching",
    "Candidate",
    "Qualified",
    "Contacted",
    "Active",
    "Archived",
)
