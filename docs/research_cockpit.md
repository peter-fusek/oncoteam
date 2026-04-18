# /research — Physician Cockpit Architecture

**Status**: specification for issue #399. Implementation starts Sprint 93 after #395 backend lands in Sprint 92.

## Purpose

`https://dashboard.oncoteam.cloud/research` is the primary workflow surface for the clinical user (per #396). Today it's a 4-tab **reading surface** with kanban state stored in browser localStorage. That is architecturally incompatible with a cross-device, audit-complete, clinically-trustable workflow. This doc specifies the redesign — 8 sub-panels as a left-sidebar sub-nav, all state server-persisted, all actions audit-logged, all agent output landing in a proposals lane rather than directly into the clinical funnel.

## Roles

| Role | Default landing | Clinical funnel writes | Proposals writes | Audit view | Compliance export |
|------|-----------------|------------------------|------------------|------------|-------------------|
| **Physician** (MUDr. Mináriková) | `/research/inbox` | ✅ (with rationale) | — | ✅ | ✅ |
| **Advocate** (Peter) | `/research/funnel` | ⚠️ (queued for MD sign-off) | — | ✅ | — |
| **Agent** (ddr_monitor etc.) | n/a | ❌ (forbidden) | ✅ (proposals only) | — | — |

## Sub-panels (8 total)

Listed in sidebar order. Each has a badge for relevant counts. Physician default landing = 📥 Inbox. Advocate default = 🎯 Clinical Funnel.

### 1. 📥 Inbox — Agent Proposals Queue

**Purpose**: every new proposal from agents lands here for physician triage.

**Data source**: `GET /api/funnel/proposals?patient_id=q1b&status=unreviewed`

**Per-card content**:
- NCT / PMID + title
- Biomarker-match rationale (gene / variant / tier / therapy class)
- Geographic score (#394) with proximity badge (SK / CZ-AT / CEE / EU / global)
- AI confidence score (0-10) + reasoning
- Source citations with deep-links to oncofiles documents
- Re-surface warning if prior dismissal exists

**Actions per card**:
- **Promote to funnel** → stage picker + rationale (required) → becomes clinical card
- **Archive** → reason dropdown (noise / ineligible / duplicate / low-confidence / other+freetext)
- **Flag for discussion** → moves to Discussion panel, stays in Inbox
- **Need more info** → specifies gap; agent notified on next run

**Sort**: date received | AI confidence | biomarker match | geographic proximity | source | agent
**Bulk**: multi-select + bulk archive with shared reason
**Empty state**: "✅ Inbox empty — caught up" with last-reviewed timestamp
**Badge alerts**: red when unreviewed > 0; amber when > 5 unreviewed > 7 days

**Keyboard shortcuts**: j/k navigate, p promote, a archive, f flag, d discuss, / search

### 2. 🎯 Clinical Funnel

**Purpose**: physician-writable 5-stage kanban. Only physicians (+ advocate with MD sign-off) can move cards.

**Stages**:
- **Watching** — monitoring; status updates relevant
- **Candidate** — reviewed, clinically plausible, pending more data
- **Qualified** — meets eligibility, ready to contact
- **Contacted** — outreach made to trial site
- **Active** — patient enrolled
- **Archived** — dismissed with rationale (reachable, not deleted)

**Data source**: `GET /api/funnel/cards?patient_id=q1b&lane=clinical`

**Per-card (expanded detail view)**:
- Current stage + all prior stages (timeline)
- Biomarker match + geographic score
- Attached literature (evidence — see panel 3)
- Discussion thread (see panel 5)
- Agent suggestions (annotations; accept/dismiss per suggestion)
- Full per-card audit log

**Move semantics**: drag-and-drop OR stage-picker menu. **Rationale modal mandatory** before commit. 1-500 chars required. Below 1 → dialog rejects.

**Agent suggestions**: displayed inline as dismissable annotations. Examples: "new CEE site opened at Masaryk Institute (PL → CZ)" or "Enrollment status changed from Recruiting → Active". Accepting a suggestion creates an audit event with physician attribution + agent reference.

### 3. 📚 Literature

**Purpose**: PubMed/ESMO feed with clinical linkage to funnel cards.

**Data source**: `GET /api/research/entries?patient_id=q1b&source=pubmed,esmo`

**Enhancements over current**:
- **Per-entry review state**: unread / read / relevant / not-applicable (physician-marked)
- **Cite on trial card**: attach PMID as evidence on any funnel card
- **Detected linkages**: abstract mentions NCT already in funnel → auto-show badge
- **Per-entry physician notes**: free-text, persisted, visible in audit

### 4. 📰 News

**Purpose**: real-world clinical news (FDA, ESMO presentations, site activations).

**Data source**: `GET /api/research/entries?patient_id=q1b` filtered client-side into `treatment_updates` / `clinical_news` / `patient_education` categories (same classifier as today).

**Physician-specific enhancements**:
- **Share with patient** button on `patient_education` items → WhatsApp Erika via existing template infrastructure (requires physician explicit click; never auto)
- **Link to funnel**: news mentioning a watched trial auto-attaches to that card's activity log

### 5. 🗣️ Discussion

**Purpose**: threaded notes per card + patient-level discussion board.

**Per-card thread**:
- Entries with actor + role chip + timestamp + markdown-light body
- @-mentions: `@mudr.minarikova`, `@peter` → notify on their next login
- Attachments: pin a PMID or NCT reference with auto-preview
- Export thread as PDF for physician records

**Patient-level board**: cross-card discussions organized by topic (e.g., "4L strategy after FOLFOX progression").

**Data source**: `/api/funnel/cards/{id}/discussion` + `/api/discussion/patient/{id}`

### 6. 📊 Audit Log

**Purpose**: immutable decision history. Compliance + physician retrieval.

**Views**:
- **Per-patient timeline** (this panel default) — everything across Erika's research in date range
- **Per-card timeline** — opened from any card detail
- **Filters**: actor (me / physician / advocate / agent / any) × event type (moved / archived / commented / cited / signed-off / suggested) × date range
- **Exports**: CSV (analysis) + PDF (medical record inclusion)

**Compliance view**: read-only regulatory export — "every decision on q1b by MUDr. Mináriková from [date] to [date]" — for medical record attachment.

**Data source**: `/api/funnel/audit/patient/q1b?filters=...&format=json|csv|pdf`

### 7. ⭐ My Watchlist (physician-curated)

**Purpose**: personal "monitor this" list separate from protocol-derived watched trials.

**Data source**: `/api/funnel/watchlist?user_id=mudr_minarikova_z&patient_id=q1b`

**Actions**:
- Add NCT / PMID / keyword
- Alerts on status change (new site, enrollment resume, publication)
- Promote to Clinical Funnel when ready
- Remove (audit-logged)

**Contrast**: the top-of-page protocol `watched_trials` display stays as today (static from `clinical_protocol.py`). Her personal watchlist is in this sub-panel.

### 8. 🔍 Re-Surfaced

**Purpose**: trials/articles previously dismissed that an agent has re-discovered.

**Data source**: `/api/funnel/resurfaced?patient_id=q1b`

**Per-entry content**:
- Current agent reason for re-surfacing (what's new?)
- Prior-dismissal context: "Archived [date] by [user] because: [rationale]"
- Action: "Re-evaluate with new data" (creates new proposal in Inbox with prior-history attached) OR "Dismiss again" (rate-limits agent; >3 dismissals → agent must justify with new evidence)

**Badge**: visible count on main nav when non-empty.

## Data model (builds on #395)

### Proposal

```python
class FunnelProposal(BaseModel):
    proposal_id: str  # UUID
    patient_id: str
    source_type: Literal["agent"]
    source_agent: str  # e.g., "ddr_monitor"
    source_run_id: str
    nct_id: str | None  # or
    pmid: str | None
    title: str
    rationale: str  # agent's reasoning
    biomarker_match: dict  # structured match info
    geographic_score: float  # from #394
    ai_confidence: float  # 0-10
    citations: list[dict]  # source document references
    status: Literal["unreviewed", "promoted", "archived", "flagged", "info_requested"]
    created_at: datetime
    ttl_expires_at: datetime  # auto-archive after 30d if unreviewed
    reviewed_by: str  # user_id
    reviewed_at: datetime | None
    review_rationale: str
    duplicate_of: str | None  # funnel_card_id if prior clinical card exists
```

### Funnel card (clinical lane) — per #395 spec

### Audit event — per #395 spec

### Discussion entry

```python
class FunnelDiscussionEntry(BaseModel):
    entry_id: str
    patient_id: str
    scope: Literal["card", "patient"]
    card_id: str | None  # null if patient-level
    author_id: str
    author_role: Literal["physician", "advocate", "agent"]
    author_display_name: str
    body_markdown: str
    mentions: list[str]  # user_ids mentioned
    attachments: list[dict]  # pinned PMID/NCT refs
    created_at: datetime
    edited_at: datetime | None  # append-only semantics: edits show "edited"; original preserved in audit
```

## Migration from localStorage funnel

One-time script `scripts/migrate_localstorage_funnel_to_server.py`:

1. Dashboard client-side: on first login post-rollout, dumps all `funnel::` localStorage keys to a one-shot POST `/api/funnel/migrate`
2. Server converts each to an audit event with `event_type="localstorage_migration"` + actor="peter" (legacy; we don't know who actually did it in the per-browser state)
3. If the NCT is present in the new proposals lane or clinical lane, reconcile; otherwise create an Archived clinical card with the migrated stage and a `source="localstorage_migration"` audit entry
4. After confirmed success, client clears localStorage funnel keys
5. Old `useFunnelStage.ts` localStorage code path removed after 60 days (all users migrated)

## Notification hygiene

The research cockpit generates several notification surfaces:
- **In-dashboard banners**: @mentions waiting, re-surfaced count, inbox threshold exceeded
- **WhatsApp admin push** (advocate only): per #391 + #392 delta-gate, proximity-routed. Physician can opt-in for weekly Monday digest.
- **Email digests** (opt-in per user): daily or weekly summary of inbox + re-surfaced + @-mentions

**Never**: real-time agent noise ("scan ran, found nothing") pushed to anyone. Always aggregated.

## Frontend file layout

```
dashboard/app/
├── pages/
│   └── research/
│       ├── index.vue           # redirects to inbox (physician) or funnel (advocate) based on role
│       ├── inbox.vue           # Panel 1
│       ├── funnel.vue          # Panel 2
│       ├── literature.vue      # Panel 3
│       ├── news.vue            # Panel 4
│       ├── discussion.vue      # Panel 5
│       ├── audit.vue           # Panel 6
│       ├── watchlist.vue       # Panel 7
│       └── resurfaced.vue      # Panel 8
├── components/
│   ├── research/
│   │   ├── ResearchSidebar.vue
│   │   ├── ProposalCard.vue
│   │   ├── FunnelCardDetail.vue
│   │   ├── FunnelAuditTimeline.vue
│   │   ├── DiscussionThread.vue
│   │   ├── RationaleDialog.vue
│   │   ├── ReSurfaceWarning.vue
│   │   ├── WatchlistEditor.vue
│   │   ├── ComplianceExport.vue
│   │   └── BulkActionBar.vue
├── composables/
│   ├── useResearchCockpit.ts     # cross-panel orchestration
│   ├── useFunnelCards.ts         # server-backed funnel state (replaces useFunnelStage.ts)
│   ├── useFunnelProposals.ts
│   ├── useFunnelDiscussion.ts
│   ├── useFunnelAudit.ts
│   └── useMentions.ts
```

`useFunnelStage.ts` is **removed** after migration window closes.

## UX principles

1. **Rationale required on every state change** — no silent mutations. 1-500 chars.
2. **Nothing disappears** — archived ≠ deleted. Always reachable via filter.
3. **Role visible everywhere** — green chip for physician / blue for advocate / gray for agent.
4. **Cross-device consistency** — action on device A visible on device B within 5s.
5. **Offline tolerance** — backend unavailable → last-known-good + banner; no silent overwrites.
6. **Minimal friction on common actions** — keyboard shortcuts on Inbox + bulk select.
7. **Physician-first, but advocate-aware** — Peter sees same cockpit with his permissions, not parallel UI.
8. **Medical-record grade exports** — PDF compliance export is a first-class feature, not a hack.

## Success criteria

- Physician logs in at NOÚ desktop, makes 5 decisions, logs in later at home laptop — all 5 decisions present
- Agent proposes NCT04657068, physician dismisses with rationale — 3 days later agent re-runs → proposal lands in Re-Surfaced, not Inbox
- Physician opens a card, leaves a discussion note tagging Peter — Peter sees notification on next login
- Physician exports 30-day audit as PDF → PDF contains every event with her signature + NOÚ institution banner for medical record inclusion
- MUDr. Mináriková clears her inbox in < 10 minutes at end-of-day using keyboard shortcuts + bulk actions
- Zero incidents of \"that trial I dismissed came back\" without prior-context warning
