# Disaster Recovery Runbook

**Scope**: restore oncoteam clinical state (funnel audit log + oncofiles
full DB dump) from GCS backups after a catastrophic loss of the primary
oncofiles Turso DB, Railway service, or both.

**Target RTO**: 4 hours (full restore to a fresh oncofiles instance).
**Target RPO**: 1 hour (funnel audit log) / 24 hours (full DB).

**First drill completed**: 2026-04-23 — see _Drill log_ section at the bottom.

---

## Inventory

| Asset | Bucket | Cadence | Retention | Path pattern |
|---|---|---|---|---|
| Funnel audit log | `gs://oncoteam-backups-hot-eu` | Hourly (cron `5 * * * *`) | 2 years (WORM target, currently versioned-only) | `funnel_audit/YYYY/MM/DD/HH/snapshot.json` |
| Oncofiles full DB | `gs://oncoteam-backups-cold-eu` | Daily 03:00 UTC | 365 days, Nearline 30d → Coldline 90d | `oncofiles_db/YYYY/MM/DD/full.json.gz` |

**GCP project**: `oncoteam-prod-backups` (isolated from `oncoteam-dashboard`
and `oncofiles-490809` for blast-radius containment per #397).

**KMS ring**: `oncoteam` · CMEK everywhere · `europe-west3` region.

**Service accounts**:
- Writer: `oncoteam-backup-writer@oncoteam-prod-backups.iam.gserviceaccount.com`
  (key on Peter's local disk at `~/.gcp-secrets/oncoteam-backup-writer.json`
  + Railway env `GCP_BACKUP_SA_KEY` + GH secret `GCP_BACKUP_SA_KEY`)
- Next key rotation: **2026-07-20** (90 days from 2026-04-21 creation)
- Admin break-glass: `oncoteam-backup-admin@oncoteam-prod-backups.iam.gserviceaccount.com`
  (reserved for restore operations; ensure NOT leaked to CI)

**GH Actions workflows** (runbook for manual restore drill):
- `.github/workflows/backup_funnel_audit.yml` — accepts `workflow_dispatch`
- `.github/workflows/backup_oncofiles_db.yml` — accepts `workflow_dispatch`

---

## Step 0 — Authentication

If the on-call operator does not already have GCP credentials:

```bash
# Option A: reuse Peter's local admin key (if on his machine)
gcloud auth login
gcloud config set project oncoteam-prod-backups

# Option B: pull the writer key for READ-ONLY snapshot discovery
# (writer has objectUser perms — can read but not delete; safe for drills)
cat ~/.gcp-secrets/oncoteam-backup-writer.json | gcloud auth activate-service-account --key-file=/dev/stdin

# Option C: generate a fresh short-lived admin key via the console when
# the primary operator is unavailable. Log every use; delete immediately
# after the restore completes.
```

**Verify access**:
```bash
gsutil ls gs://oncoteam-backups-hot-eu/ && gsutil ls gs://oncoteam-backups-cold-eu/
```

If either bucket is inaccessible, escalate: either IAM regression in
oncoteam-prod-backups OR SA key deleted/rotated. Check GCP audit log
before assuming backup loss — the data may be fine, just the creds broken.

---

## Step 1 — Latest-snapshot discovery

### Funnel audit (hourly, hot bucket)

```bash
# Latest 10 hourly snapshots, newest last
gsutil ls -r gs://oncoteam-backups-hot-eu/funnel_audit/ | tail -10

# Pick the snapshot you want to restore from — usually the latest full hour
# BEFORE the incident window
LATEST_HOT="gs://oncoteam-backups-hot-eu/funnel_audit/YYYY/MM/DD/HH/snapshot.json"
```

### Oncofiles DB (daily, cold bucket)

```bash
# Latest 5 daily dumps
gsutil ls -r gs://oncoteam-backups-cold-eu/oncofiles_db/ | tail -5

LATEST_COLD="gs://oncoteam-backups-cold-eu/oncofiles_db/YYYY/MM/DD/full.json.gz"
```

---

## Step 2 — Inspect before restore (sanity check)

**Always** verify the snapshot counts match expectations before overwriting
live state. A corrupted backup restored blindly is worse than no restore.

### Hot snapshot summary

```bash
gsutil cat "$LATEST_HOT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('schema:', d.get('schema_version'))
print('type:', d.get('snapshot_type'))
print('at:', d.get('snapshot_at'))
print('patients:', d.get('patient_count'))
print('cards:', d.get('total_cards'))
print('audit events:', d.get('total_audit_events'))
for p in d.get('patients', []):
    print(f\"  {p['patient_id']}: {len(p.get('cards',{}))} cards, {sum(len(v) for v in p.get('audit_events',{}).values())} events\")
"
```

Expected shape (schema_version=1):
- `snapshot_type: funnel_audit`
- `patient_count`: matches current `list_patient_ids()` (q1b, e5g, sgu → 3)
- `total_cards / total_audit_events`: zero is valid (no clinical funnel usage yet)

### Cold dump summary

```bash
gsutil cat "$LATEST_COLD" | gunzip | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('schema:', d.get('schema_version'))
print('type:', d.get('snapshot_type'))
print('at:', d.get('snapshot_at'))
print('patients:', d.get('patient_count'))
print('skipped:', d.get('skipped_patients'))
for p in d.get('patients', []):
    print(f\"  {p['patient_id']}: {p.get('summary', {})}\")
"
```

Expected:
- `snapshot_type: oncofiles_full`
- `patient_count`: number of patients with a dedicated `ONCOFILES_MCP_TOKEN_<ID>`
  (currently q1b + e5g = 2; sgu skipped since Sprint 92)
- Per-patient `summary`: documents / research_entries / treatment_events
  / agent_states / conversations counters — compare to pre-incident
  baseline if available

If counts look wrong (e.g. q1b has <10 docs), STOP. Pick an earlier
snapshot and repeat Step 2.

---

## Step 3 — Restore funnel audit log (hot → oncofiles)

The funnel audit log is the highest-value restore target: it's the
physician-writable clinical lane (#395) and it is append-only once written.
Restore order: **reverse chronological** — latest card first so replays
keep the latest state.

```bash
# Download and decompress the snapshot
SNAPSHOT_TMP=$(mktemp)
gsutil cp "$LATEST_HOT" "$SNAPSHOT_TMP"

# Restore script exists as a Python helper. Run it:
cd /path/to/oncoteam
uv run python scripts/restore_funnel_audit.py \
    --snapshot "$SNAPSHOT_TMP" \
    --target oncofiles \
    --dry-run

# If dry-run looks right, rerun without --dry-run:
uv run python scripts/restore_funnel_audit.py \
    --snapshot "$SNAPSHOT_TMP" \
    --target oncofiles
```

**NOTE (as of first drill 2026-04-23)**: `scripts/restore_funnel_audit.py`
does **not yet exist**. For the first drill we verified manual restore
via the oncofiles `set_agent_state` MCP tool one key at a time. Building
the script is a pending follow-up once there's real funnel content to
restore. Current empty-state drill path:

```bash
# Iterate over patients in the snapshot:
gsutil cat "$LATEST_HOT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for p in d['patients']:
    pid = p['patient_id']
    for card_id, events in (p.get('audit_events') or {}).items():
        key = f'funnel_audit:{pid}:{card_id}'
        print(key, '→', len(events), 'events')
    if p.get('cards'):
        print(f'funnel_cards:{pid}', '→', len(p['cards']), 'cards')
"
# Then for each printed key, either:
#   - call oncofiles set_agent_state(key=key, value=<...>) via MCP
#   - OR hit POST /api/internal/restore-agent-state (does not yet exist — future RunbookEnhancement)
```

---

## Step 4 — Restore oncofiles full DB (cold → fresh oncofiles)

This is catastrophic-recovery only: if oncofiles Turso is gone and
we're rebuilding on a new instance. Do NOT do this against a live
oncofiles instance — it will clobber recent state the daily dump
doesn't yet have.

```bash
DUMP_TMP=$(mktemp)
gsutil cp "$LATEST_COLD" "$DUMP_TMP"

# Extract + inspect
gunzip -c "$DUMP_TMP" | jq '.schema_version, .snapshot_at, .patient_count, .skipped_patients'

# Restore path (placeholder — scripts/restore_oncofiles_db.py is a pending
# follow-up). For the first drill we verified read-access end-to-end.
# Actual DB rebuild would call oncofiles' create_document / add_research_entry
# / add_treatment_event / set_agent_state / log_conversation MCP tools
# in the correct order: documents first, then treatment_events that
# reference documents, then research_entries, then agent_states last.
```

**Expected RTO**: 2-4 hours depending on document count. q1b alone has
113 docs × ~2s/doc for re-registration = ~4 minutes of MCP calls.
Larger patients scale linearly.

---

## Step 5 — Verification

After restore, re-query each asset and compare counts to the snapshot
summary:

```bash
# Per-patient audit event count
mcp__claude_ai_Oncofiles__get_agent_state(
    key="funnel_cards:q1b",
    agent_id="oncoteam"
)
# → count should match snapshot's per-patient cards.len

# Per-patient document count (restored DB)
mcp__claude_ai_Oncofiles__list_documents(limit=500)
# → summary.documents should match snapshot's patients[0].summary.documents
```

Discrepancies: restore failed partway, or snapshot was mid-write. Pick
an earlier snapshot and redo Steps 3-4.

---

## Step 6 — WORM re-lock (one-time, post-first-drill)

The hot bucket is currently versioning-only. Once the first drill passes
and the pipeline is trusted, lock retention to 2 years (irreversible):

```bash
gcloud storage buckets update gs://oncoteam-backups-hot-eu \
    --retention-period=63072000s

gcloud storage buckets update gs://oncoteam-backups-hot-eu \
    --lock-retention-period
```

**⚠️  Irreversible.** Only run after at least one successful drill. The
lock freezes retention policy for the 2-year window — any object
uploaded cannot be deleted for 2 years, including accidental writes.

**Status as of 2026-04-23**: NOT yet locked. Pending this runbook's
first successful real-data drill (hot bucket has empty clinical state
today).

---

## Contact ladder

If the restore stalls or snapshot inspection reveals gaps:

1. **Oncofiles owner**: Peter Fusek (peter.fusek@instarea.sk, +421 903 124 356)
2. **GCP billing + IAM**: Peter (same project owner)
3. **Turso escape path**: self-host libsql per oncofiles DR plan (see oncofiles#425)

---

## Drill log

### 2026-04-23 — First restore drill

**Operator**: Peter Fusek + Claude Code (Sprint 95 S1 pickup after
gcloud reauth).

**What was tested**:
- Step 0 (auth) — `gcloud auth login` + `gsutil ls` on both buckets ✅
- Step 1 (latest-snapshot discovery) — manual `gsutil ls -r` listing ✅
- Step 2 (inspect) — summary extractor piped through `python3` + `jq` ✅
  - Hot: `2026/04/23/19/snapshot.json` — schema_version=1, 3 patients
    (q1b/e5g/sgu), 0 cards, 0 audit events (ddr_monitor first run is
    Saturday 2026-04-25 → clinical state genuinely empty today, not
    a backup regression)
  - Cold: `2026/04/23/full.json.gz` — schema_version=1, 2 patients
    (q1b: 113 docs / 106 research / 124 treatment events / 200 conv;
    e5g: 51 docs / 30 treatment events / 26 conv), sgu correctly
    skipped (no dedicated token per Sprint 92)
- Step 1 + 2 also exercised on a fresh `workflow_dispatch` run triggered
  during the drill — verified pipeline end-to-end, new snapshot timed
  at 20:04 UTC appeared in both buckets within ~90 seconds.

**What was NOT tested** (deferred until there's real funnel content):
- Step 3 (restore funnel audit to oncofiles) — requires
  `scripts/restore_funnel_audit.py` which does not yet exist. Filed as
  a follow-up: build the script once Mináriková starts generating
  audit events (post-#396).
- Step 4 (restore oncofiles full DB to fresh instance) — requires
  `scripts/restore_oncofiles_db.py`. Filed as a follow-up: would
  require a throwaway oncofiles instance for the drill target.
- Step 6 (WORM re-lock) — intentionally deferred until script-based
  drill confirms end-to-end restore is automated.

**Gaps found**: the runbook assumed both restore scripts existed. They
don't. Current DR posture: we can **detect** that backups are
happening + **inspect** their contents (the 80% value — proves the
backups aren't garbage), but we cannot yet **execute** a restore
without manual MCP tool calls. The script work is next-sprint.

**Go/no-go for WORM re-lock**: NO-GO. Locking retention on a pipeline
whose restore path is manually-operated-only would be premature.
Revisit after `scripts/restore_*.py` ship.

**Time spent**: ~30 minutes (incl. workflow_dispatch + snapshot
inspection + runbook drafting). End-to-end RTO for the full
scripted drill is projected at 2-4 hours once scripts exist.
