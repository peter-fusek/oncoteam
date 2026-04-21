"""Daily full-state backup of oncofiles data for every registered patient (#397).

Aggregates documents, treatment events, research entries, agent_states and the
last 90 days of conversations across every patient_id this oncoteam instance
has tokens for. Gzips the result and uploads to the cold bucket with lifecycle
Nearline 30d → Coldline 90d → delete at 365d (non-live versions).

Runs on a 1-day cron via GitHub Actions. Heavy query load against oncofiles —
don't poll more than once per day. The cold bucket is the restore target for
the DR runbook, not a live lookup path.

Required environment:
    GCP_BACKUP_SA_KEY       base64 JSON of the oncoteam-backup-writer SA key
    ONCOFILES_MCP_URL
    ONCOFILES_MCP_TOKEN     (default patient token)
    ONCOFILES_MCP_TOKEN_<ID>  (optional per-patient tokens)

Writes to:
    gs://oncoteam-backups-cold-eu/oncofiles_db/YYYY/MM/DD/full.json.gz

Re-running within the same day overwrites that day's snapshot.
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import json
import logging
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

_sa_b64 = os.environ.get("GCP_BACKUP_SA_KEY", "")
if not _sa_b64:
    sys.exit("ERROR: GCP_BACKUP_SA_KEY env var not set — cannot authenticate to GCS")
_sa_json = base64.b64decode(_sa_b64)
with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as _sa_tmp:
    _sa_tmp.write(_sa_json)
    _sa_key_path = _sa_tmp.name
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _sa_key_path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from google.cloud import storage  # noqa: E402

from oncoteam import oncofiles_client  # noqa: E402
from oncoteam.patient_context import list_patient_ids  # noqa: E402
from oncoteam.request_context import get_token_for_patient  # noqa: E402

COLD_BUCKET = "oncoteam-backups-cold-eu"
CONVERSATIONS_LOOKBACK_DAYS = 90

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backup_oncofiles_db")


async def _safe_call(label: str, coro):
    """Wrap a single oncofiles call so one slow/failing endpoint doesn't sink the whole run."""
    try:
        return await coro
    except Exception as exc:
        logger.warning("%s failed: %s", label, exc)
        return {"error": str(exc)}


async def dump_patient(patient_id: str) -> dict:
    """Collect every data surface for one patient into a single dict."""
    token = get_token_for_patient(patient_id)
    now = datetime.now(UTC)
    since = (now - timedelta(days=CONVERSATIONS_LOOKBACK_DAYS)).date().isoformat()

    documents = await _safe_call(
        f"list_documents[{patient_id}]",
        oncofiles_client.list_documents(limit=500, token=token),
    )
    research_entries = await _safe_call(
        f"list_research_entries[{patient_id}]",
        oncofiles_client.list_research_entries(limit=500, token=token),
    )
    treatment_events = await _safe_call(
        f"list_treatment_events[{patient_id}]",
        oncofiles_client.list_treatment_events(limit=1000, token=token),
    )
    agent_states = await _safe_call(
        f"list_agent_states[{patient_id}]",
        oncofiles_client.list_agent_states(agent_id="oncoteam", limit=10_000, token=token),
    )
    conversations = await _safe_call(
        f"search_conversations[{patient_id}]",
        oncofiles_client.search_conversations(date_from=since, limit=5000, token=token),
    )

    # Summary counters — lets the restore drill verify row counts without
    # having to gunzip+parse the whole blob.
    summary = {
        "documents": len(documents.get("documents", []))
        if isinstance(documents, dict) and "documents" in documents
        else 0,
        "research_entries": len(research_entries.get("entries", []))
        if isinstance(research_entries, dict) and "entries" in research_entries
        else 0,
        "treatment_events": len(treatment_events.get("events", []))
        if isinstance(treatment_events, dict) and "events" in treatment_events
        else 0,
        "agent_states": len(agent_states.get("states", []))
        if isinstance(agent_states, dict) and "states" in agent_states
        else 0,
        "conversations": len(conversations.get("entries", []))
        if isinstance(conversations, dict) and "entries" in conversations
        else 0,
    }
    logger.info("patient=%s summary=%s", patient_id, summary)

    return {
        "patient_id": patient_id,
        "dumped_at": now.isoformat(),
        "conversations_since": since,
        "summary": summary,
        "documents": documents,
        "research_entries": research_entries,
        "treatment_events": treatment_events,
        "agent_states": agent_states,
        "conversations": conversations,
    }


def _has_own_token(patient_id: str) -> bool:
    """Return True iff this patient has a dedicated bearer token.

    q1b uses the default ONCOFILES_MCP_TOKEN; every other patient requires
    an explicit ONCOFILES_MCP_TOKEN_<ID>. Without it, the wrapper falls
    back to the default token — which would silently dump q1b's data under
    the other patient's label, producing a garbage backup that looks fine
    at row-count level. So we skip those patients entirely.
    """
    from oncoteam.patient_context import _patient_tokens

    if patient_id == "q1b":
        return bool(os.environ.get("ONCOFILES_MCP_TOKEN"))
    return patient_id in _patient_tokens


async def build_dump() -> dict:
    now = datetime.now(UTC)
    patients = []
    skipped: list[str] = []
    for pid in list_patient_ids():
        if not _has_own_token(pid):
            logger.warning(
                "skipping patient=%s — no dedicated ONCOFILES_MCP_TOKEN_%s env var "
                "(dumping under the default token would mislabel q1b's data)",
                pid,
                pid.upper(),
            )
            skipped.append(pid)
            continue
        logger.info("dumping patient=%s", pid)
        patients.append(await dump_patient(pid))

    return {
        "schema_version": 1,
        "snapshot_type": "oncofiles_full",
        "snapshot_at": now.isoformat(),
        "conversations_lookback_days": CONVERSATIONS_LOOKBACK_DAYS,
        "patient_count": len(patients),
        "skipped_patients": skipped,
        "patients": patients,
    }


def upload(dump: dict) -> str:
    now = datetime.fromisoformat(dump["snapshot_at"])
    blob_path = f"oncofiles_db/{now:%Y/%m/%d}/full.json.gz"

    payload = json.dumps(dump, default=str, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(payload, compresslevel=6)

    client = storage.Client()
    bucket = client.bucket(COLD_BUCKET)
    blob = bucket.blob(blob_path)
    blob.content_encoding = "gzip"
    blob.upload_from_string(compressed, content_type="application/json")
    uri = f"gs://{COLD_BUCKET}/{blob_path}"
    logger.info(
        "uploaded %s (raw=%d bytes, compressed=%d bytes, ratio=%.1fx)",
        uri,
        len(payload),
        len(compressed),
        len(payload) / max(1, len(compressed)),
    )
    return uri


async def main() -> int:
    dump = await build_dump()
    try:
        upload(dump)
    except Exception as exc:
        logger.error("upload failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
