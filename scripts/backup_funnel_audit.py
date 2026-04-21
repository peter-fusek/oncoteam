"""Hourly backup of the two-lane clinical funnel audit log (#397 / #395).

Dumps every `funnel_cards:*` and `funnel_audit:*` key from the oncofiles
`agent_state` store for every registered patient, bundles them into a
single JSON snapshot, and uploads to the WORM-intended hot bucket.

Designed to run from GitHub Actions on a 1-hour cron. Safe to run manually
for ad-hoc restore drills.

Required environment:
    GCP_BACKUP_SA_KEY       base64-encoded JSON of the
                            oncoteam-backup-writer@oncoteam-prod-backups
                            service account key
    ONCOFILES_MCP_URL       (read by oncofiles_client as usual)
    ONCOFILES_MCP_TOKEN     (default patient token — typically q1b)
    ONCOFILES_MCP_TOKEN_<ID>  (additional per-patient tokens, optional)

Writes to:
    gs://oncoteam-backups-hot-eu/funnel_audit/YYYY/MM/DD/HH/snapshot.json

Re-running within the same hour overwrites the snapshot with the latest
state — idempotent by wall-clock bucket path.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

# Set up GCP credentials BEFORE importing google.cloud — the library picks up
# GOOGLE_APPLICATION_CREDENTIALS at import. Decode the base64'd SA key from env
# and point the lib at a short-lived temp file.
_sa_b64 = os.environ.get("GCP_BACKUP_SA_KEY", "")
if not _sa_b64:
    sys.exit("ERROR: GCP_BACKUP_SA_KEY env var not set — cannot authenticate to GCS")
_sa_json = base64.b64decode(_sa_b64)
with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as _sa_tmp:
    _sa_tmp.write(_sa_json)
    _sa_key_path = _sa_tmp.name
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _sa_key_path

# Make src/ importable so this script works whether invoked via uv run,
# python -m, or plain python from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from google.cloud import storage  # noqa: E402

from oncoteam import oncofiles_client  # noqa: E402
from oncoteam.patient_context import list_patient_ids  # noqa: E402
from oncoteam.request_context import get_token_for_patient  # noqa: E402

HOT_BUCKET = "oncoteam-backups-hot-eu"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backup_funnel_audit")


async def snapshot_patient(patient_id: str) -> dict:
    """Return {cards, audit_events} for one patient. Missing keys ⇒ empty lists."""
    token = get_token_for_patient(patient_id)
    cards_by_id: dict[str, dict] = {}
    audit_by_card: dict[str, list[dict]] = {}

    # list_agent_states returns every key for the token's scope. We filter
    # client-side so we don't need an extra API method on oncofiles.
    try:
        result = await oncofiles_client.list_agent_states(
            agent_id="oncoteam", limit=10_000, token=token
        )
    except Exception as exc:
        logger.error("patient=%s list_agent_states failed: %s", patient_id, exc)
        return {
            "patient_id": patient_id,
            "cards": {},
            "audit_events": {},
            "error": str(exc),
        }

    states = result.get("states", []) if isinstance(result, dict) else []
    cards_key = f"funnel_cards:{patient_id}"
    audit_prefix = f"funnel_audit:{patient_id}:"

    for entry in states:
        key = entry.get("key", "")
        value = entry.get("value")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                value = None
        if key == cards_key and isinstance(value, dict):
            cards_by_id = value.get("cards", value)
        elif key.startswith(audit_prefix) and isinstance(value, (list, dict)):
            card_id = key[len(audit_prefix) :]
            events = value if isinstance(value, list) else value.get("events", [])
            audit_by_card[card_id] = events

    return {
        "patient_id": patient_id,
        "cards": cards_by_id,
        "audit_events": audit_by_card,
    }


async def build_snapshot() -> dict:
    """Build the hour's full snapshot across every registered patient."""
    now = datetime.now(UTC)
    patient_snapshots = []
    for pid in list_patient_ids():
        logger.info("snapshotting patient=%s", pid)
        patient_snapshots.append(await snapshot_patient(pid))

    total_cards = sum(len(p.get("cards", {})) for p in patient_snapshots)
    total_events = sum(
        sum(len(v) for v in p.get("audit_events", {}).values()) for p in patient_snapshots
    )
    logger.info(
        "snapshot built: %d patients, %d cards, %d audit events",
        len(patient_snapshots),
        total_cards,
        total_events,
    )

    return {
        "schema_version": 1,
        "snapshot_type": "funnel_audit",
        "snapshot_at": now.isoformat(),
        "patient_count": len(patient_snapshots),
        "total_cards": total_cards,
        "total_audit_events": total_events,
        "patients": patient_snapshots,
    }


def upload(snapshot: dict) -> str:
    """Upload to gs://HOT_BUCKET/funnel_audit/YYYY/MM/DD/HH/snapshot.json. Return blob URI."""
    now = datetime.fromisoformat(snapshot["snapshot_at"])
    blob_path = f"funnel_audit/{now:%Y/%m/%d/%H}/snapshot.json"
    client = storage.Client()
    bucket = client.bucket(HOT_BUCKET)
    blob = bucket.blob(blob_path)
    # JSON-serializable — preserve readable formatting so a physician can
    # inspect a snapshot directly with `gsutil cat` without re-parsing.
    blob.upload_from_string(
        json.dumps(snapshot, indent=2, default=str),
        content_type="application/json",
    )
    uri = f"gs://{HOT_BUCKET}/{blob_path}"
    logger.info("uploaded %s (%d bytes)", uri, blob.size or 0)
    return uri


async def main() -> int:
    snapshot = await build_snapshot()
    try:
        upload(snapshot)
    except Exception as exc:
        logger.error("upload failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
