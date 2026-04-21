#!/usr/bin/env bash
# One-time GCP setup for oncoteam backups (#397).
#
# Creates a dedicated project in the instarea.sk org with IAM/billing isolated
# from oncoteam-dashboard + oncofiles-490809 so the backup service account
# cannot reach primary data — only write backups into its own buckets.
#
# Prereqs: gcloud CLI installed, authenticated as peter.fusek@instarea.sk,
# billing account 014C04-71B29C-CEE57C active.
#
# Estimated monthly cost at current scale: < $5 (KMS $0.06/key, GCS EU
# multi-region ~$0.02/GB, plus ops charges — audit log < 100 MB initially).
#
# Run step-by-step; review before each block. Do not pipe blind to bash.

set -euo pipefail

# ── Config ─────────────────────────────────────────────────────────────
ORG_ID="4876110950"                      # instarea.sk
BILLING_ACCOUNT="014C04-71B29C-CEE57C"   # "My Billing Account"
PROJECT_ID="oncoteam-prod-backups"        # globally unique; may need suffix if taken
PROJECT_NAME="Oncoteam Production Backups"
KMS_LOCATION="europe"                     # KMS multi-region (lower-case)
BUCKET_LOCATION="EU"                      # GCS multi-region (upper-case — different vocab!)
KEYRING="oncoteam-backups"
KMS_KEY="backup-encryption-key"
HOT_BUCKET="gs://oncoteam-backups-hot-eu"
COLD_BUCKET="gs://oncoteam-backups-cold-eu"
SA_NAME="oncoteam-backup-writer"

# ── Step 1: create project under instarea.sk org ───────────────────────
# Free. Reversible (can delete within 30 days). Project ID globally burned.
# Idempotent: skip if the project already exists (Sprint 93 S5 re-run after
# billing-quota block on first attempt).
echo "Step 1: creating project ${PROJECT_ID} under org ${ORG_ID}"
if gcloud projects describe "${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  project ${PROJECT_ID} already exists — skipping create"
else
  gcloud projects create "${PROJECT_ID}" \
    --name="${PROJECT_NAME}" \
    --organization="${ORG_ID}"
fi

# ── Step 2: link billing (required for KMS + GCS) ──────────────────────
# Activates billable resource creation. Reversible: unlink to stop charges.
echo "Step 2: linking billing ${BILLING_ACCOUNT}"
gcloud billing projects link "${PROJECT_ID}" \
  --billing-account="${BILLING_ACCOUNT}"

# ── Step 3: set project as active (for subsequent commands) ────────────
gcloud config set project "${PROJECT_ID}"

# ── Step 4: enable required APIs ───────────────────────────────────────
# Free. Cloud Storage + KMS (for CMEK) + Secret Manager + IAM (for SA).
echo "Step 4: enabling APIs"
gcloud services enable \
  storage.googleapis.com \
  cloudkms.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudresourcemanager.googleapis.com

# ── Step 5: create KMS keyring + key for CMEK ──────────────────────────
# Cost: $0.06/month per key + $0.03 per 10k operations.
# Idempotent: keyring/key creation is a no-op if they already exist.
echo "Step 5: creating KMS keyring + key"
if ! gcloud kms keyrings describe "${KEYRING}" --location="${KMS_LOCATION}" >/dev/null 2>&1; then
  gcloud kms keyrings create "${KEYRING}" --location="${KMS_LOCATION}"
fi
if ! gcloud kms keys describe "${KMS_KEY}" --keyring="${KEYRING}" --location="${KMS_LOCATION}" >/dev/null 2>&1; then
  gcloud kms keys create "${KMS_KEY}" \
    --keyring="${KEYRING}" \
    --location="${KMS_LOCATION}" \
    --purpose=encryption
fi

# Grant the GCS service agent permission to use this key (required for CMEK).
# GOTCHA: after enabling storage.googleapis.com, the service agent takes up to
# ~120s to materialize. Calling add-iam-policy-binding before it exists fails
# with "Service account ... does not exist". Force-provision it with
# `gcloud storage service-agent` which is the documented way to trigger agent
# creation, and retry until it resolves.
echo "  provisioning GCS service agent (can take ~1 min after API enable)"
for i in 1 2 3 4 5 6; do
  GCS_SERVICE_AGENT="$(gcloud storage service-agent --project="${PROJECT_ID}" 2>/dev/null || true)"
  if [ -n "${GCS_SERVICE_AGENT}" ]; then
    break
  fi
  echo "  retry ${i}/6 — waiting 10s for service agent"
  sleep 10
done
if [ -z "${GCS_SERVICE_AGENT}" ]; then
  echo "ERROR: GCS service agent not provisioned after 60s. Try again later."
  exit 1
fi
gcloud kms keys add-iam-policy-binding "${KMS_KEY}" \
  --keyring="${KEYRING}" \
  --location="${KMS_LOCATION}" \
  --member="serviceAccount:${GCS_SERVICE_AGENT}" \
  --role="roles/cloudkms.cryptoKeyEncrypterDecrypter"

# ── Step 6: create buckets ─────────────────────────────────────────────
# EU multi-region. CMEK from step 5. Versioning on both. Idempotent.
# GCS multi-region uses UPPERCASE "EU" — different vocabulary from KMS's
# "europe". Using the wrong one returns HTTPError 400 "location constraint
# is not valid".
KMS_KEY_NAME="projects/${PROJECT_ID}/locations/${KMS_LOCATION}/keyRings/${KEYRING}/cryptoKeys/${KMS_KEY}"

echo "Step 6a: creating hot bucket (audit log, versioned — WORM added later)"
if ! gcloud storage buckets describe "${HOT_BUCKET}" >/dev/null 2>&1; then
  gcloud storage buckets create "${HOT_BUCKET}" \
    --project="${PROJECT_ID}" \
    --location="${BUCKET_LOCATION}" \
    --uniform-bucket-level-access \
    --default-encryption-key="${KMS_KEY_NAME}"
fi

# NOTE (Sprint 93 S5 soften): the original config applied a 2-year retention
# lock via `--retention-period=63072000s`. Retention LOCKS are irreversible —
# once applied, GCS refuses any object delete for the full retention period,
# even by the project owner. We defer that commitment until the backup
# pipeline proves itself (scripts/backup_funnel_audit.py + restore drill).
# Versioning below gives defense-in-depth that stays fully reversible: any
# accidental delete becomes a non-current version, recoverable within the
# 365d lifecycle.
#
# To re-introduce WORM once we're comfortable (typically after the first
# successful restore drill, late Sprint 93 / early Sprint 94):
#   gcloud storage buckets update "${HOT_BUCKET}" --retention-period=63072000s
#   gcloud storage buckets update "${HOT_BUCKET}" --lock-retention-period
gcloud storage buckets update "${HOT_BUCKET}" --versioning

echo "Step 6b: creating cold bucket (daily DB dump, 365d versioning)"
if ! gcloud storage buckets describe "${COLD_BUCKET}" >/dev/null 2>&1; then
  gcloud storage buckets create "${COLD_BUCKET}" \
    --project="${PROJECT_ID}" \
    --location="${BUCKET_LOCATION}" \
    --uniform-bucket-level-access \
    --default-encryption-key="${KMS_KEY_NAME}"
fi

gcloud storage buckets update "${COLD_BUCKET}" --versioning

# Lifecycle: move cold bucket objects to Nearline after 30d, Coldline after 90d,
# delete after 365d (versions). Cheaper long-tail storage.
cat > /tmp/oncoteam-cold-lifecycle.json <<'JSON'
{
  "rule": [
    {"action": {"type": "SetStorageClass", "storageClass": "NEARLINE"},
     "condition": {"age": 30}},
    {"action": {"type": "SetStorageClass", "storageClass": "COLDLINE"},
     "condition": {"age": 90}},
    {"action": {"type": "Delete"},
     "condition": {"age": 365, "isLive": false}}
  ]
}
JSON
gcloud storage buckets update "${COLD_BUCKET}" \
  --lifecycle-file=/tmp/oncoteam-cold-lifecycle.json

# ── Step 7: create backup service account with minimum-scope IAM ───────
# Idempotent: skip create if the SA already exists.
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
echo "Step 7: creating service account ${SA_NAME}"
if ! gcloud iam service-accounts describe "${SA_EMAIL}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="Oncoteam backup writer" \
    --description="Writes hourly audit + daily DB backups. No read of prod data."
  # SA visibility is eventually consistent — wait until describe succeeds
  # before we start binding IAM roles that depend on the SA existing.
  for i in 1 2 3 4 5 6; do
    if gcloud iam service-accounts describe "${SA_EMAIL}" >/dev/null 2>&1; then
      break
    fi
    echo "  waiting ${i}/6 for SA to propagate"
    sleep 5
  done
fi

# Grant write-only access to both buckets (Object Creator — cannot read or delete existing objects).
gcloud storage buckets add-iam-policy-binding "${HOT_BUCKET}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectCreator"

gcloud storage buckets add-iam-policy-binding "${COLD_BUCKET}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectCreator"

# KMS encrypter role — needed to upload objects that are CMEK-encrypted.
gcloud kms keys add-iam-policy-binding "${KMS_KEY}" \
  --keyring="${KEYRING}" \
  --location="${KMS_LOCATION}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudkms.cryptoKeyEncrypter"

# ── Step 8: create service account key (for Railway env vars) ─────────
# Store the resulting file in Railway env var GCP_BACKUP_SA_KEY (base64-encoded JSON).
echo "Step 8: creating service account key — store securely, do NOT commit"
mkdir -p ~/.gcp-secrets
gcloud iam service-accounts keys create ~/.gcp-secrets/oncoteam-backup-writer.json \
  --iam-account="${SA_EMAIL}"

echo ""
echo "Key written to ~/.gcp-secrets/oncoteam-backup-writer.json"
echo "Next: base64-encode this file and set as GCP_BACKUP_SA_KEY in Railway."
echo "  base64 -i ~/.gcp-secrets/oncoteam-backup-writer.json | pbcopy"
echo ""
echo "Rotate this key every 90 days (schedule a Linear reminder)."

# ── Step 9: billing alert (recommended but optional) ───────────────────
# Configure via console: https://console.cloud.google.com/billing/${BILLING_ACCOUNT}/budgets
# Suggest: budget $25/month, alert at 50% / 90% / 100%.
echo "Step 9 (manual): create billing alert in console — $25/month budget, 50/90/100% alerts"

# ── Done ───────────────────────────────────────────────────────────────
echo ""
echo "✅ GCP backup infrastructure provisioned."
echo "Project:   ${PROJECT_ID}"
echo "Hot:       ${HOT_BUCKET} (WORM, 2y retention)"
echo "Cold:      ${COLD_BUCKET} (versioned, 365d lifecycle)"
echo "KMS key:   ${KMS_KEY_NAME}"
echo "SA:        ${SA_EMAIL}"
echo ""
echo "Next steps (see #397):"
echo "  1. Add GCP_BACKUP_SA_KEY env var to Railway (base64 of SA key JSON)"
echo "  2. Write scripts/backup_funnel_audit.py — hourly via GitHub Actions cron"
echo "  3. Write scripts/backup_oncofiles_db.py — daily via GitHub Actions cron"
echo "  4. docs/disaster_recovery.md — write the runbook"
echo "  5. First monthly restore drill — schedule for end of Sprint 93"
