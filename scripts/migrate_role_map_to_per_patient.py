#!/usr/bin/env python3
"""Migrate legacy flat ROLE_MAP to per-patient role entries (#422 Part B).

Legacy shape (pre-#422 Part B) — a user's single role applies to every
patient they can see:
    role_map[email] = {
        phone, name,
        roles: [advocate],
        patient_id: q1b,
        patient_ids: [q1b, e5g],
    }

New shape — per-patient role:
    role_map[email] = {
        phone, name,
        patient_roles: {q1b: advocate, e5g: patient, ...},
        # legacy fields preserved for read-compat
        roles: [advocate],
        patient_id: q1b,
        patient_ids: [q1b, e5g],
    }

Guarantees:
    - Legacy fields are NOT removed. The two shapes coexist and the reader
      prefers `patient_roles` when present. Rollback is just "remove
      patient_roles from the entry" — no lossy transform.
    - A snapshot of the pre-migration role_map is written under
      `role_map:snapshot_pre_per_patient_roles` in oncofiles agent_state
      so the original state is recoverable even if someone later edits
      the main key by hand.
    - Idempotent: running twice is a no-op (already-migrated entries are
      skipped based on a `patient_roles` presence check).
    - Dry-run by default. `--commit` performs the writes.

Derivation rule: `patient_roles[pid] = roles[0]` for every pid in
`patient_ids` (or the single `patient_id` if that's all that's set).
If roles is empty, defaults to "advocate" — the legacy pre-#422 fallback.

Usage:
    uv run python scripts/migrate_role_map_to_per_patient.py
    uv run python scripts/migrate_role_map_to_per_patient.py --commit
    uv run python scripts/migrate_role_map_to_per_patient.py \\
        --email peter.fusek@instarea.sk --commit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from oncoteam import oncofiles_client  # noqa: E402

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("migrate_role_map")


async def _load_role_map() -> dict:
    """Read the live role_map from oncofiles agent_state."""
    state = await oncofiles_client.get_agent_state(key="role_map", agent_id="access_rights")
    # oncofiles returns either the raw dict or {"value": "<json>"}.
    if isinstance(state, dict) and "value" in state:
        inner = state["value"]
        if isinstance(inner, str):
            try:
                state = json.loads(inner)
            except (json.JSONDecodeError, TypeError):
                state = {}
        elif isinstance(inner, dict):
            state = inner
    if isinstance(state, dict) and isinstance(state.get("role_map"), dict):
        return state["role_map"]
    if isinstance(state, dict) and all(isinstance(v, dict) for v in state.values()):
        return state
    return {}


def _derive_patient_roles(uc: dict) -> dict[str, str]:
    """Apply legacy `roles[0]` to every `patient_id` / `patient_ids` entry."""
    pids: set[str] = set()
    if isinstance(uc.get("patient_ids"), list):
        for pid in uc["patient_ids"]:
            if isinstance(pid, str) and pid:
                pids.add(pid)
    single = uc.get("patient_id")
    if isinstance(single, str) and single:
        pids.add(single)
    roles = uc.get("roles")
    primary = roles[0] if isinstance(roles, list) and roles else "advocate"
    return {pid: primary for pid in pids}


async def _snapshot_pre_migration(role_map: dict) -> None:
    """Write a timestamped snapshot of the original role_map."""
    key = "role_map:snapshot_pre_per_patient_roles"
    await oncofiles_client.set_agent_state(
        key=key,
        value={
            "captured_at": datetime.now(UTC).isoformat(),
            "role_map": role_map,
            "note": "pre-#422-Part-B snapshot — restore by writing this back under 'role_map'",
        },
        agent_id="access_rights",
    )
    logger.info("Snapshot written under %s", key)


async def _write_migrated(role_map: dict) -> None:
    """Persist the post-migration role_map."""
    await oncofiles_client.set_agent_state(
        key="role_map",
        value={
            "role_map": role_map,
            "updated_at": datetime.now(UTC).isoformat(),
            "migration": "422-part-b-per-patient-roles",
        },
        agent_id="access_rights",
    )
    logger.info("Migrated role_map written (%d entries)", len(role_map))


async def main_async(args: argparse.Namespace) -> int:
    role_map = await _load_role_map()
    if not role_map:
        logger.warning("No role_map found — nothing to migrate.")
        return 0

    target_emails = [args.email] if args.email else sorted(role_map.keys())

    total = 0
    skipped = 0
    migrated: dict[str, dict] = {}
    for email, uc in role_map.items():
        if email not in target_emails:
            migrated[email] = uc
            continue
        if not isinstance(uc, dict):
            migrated[email] = uc
            continue
        total += 1
        if isinstance(uc.get("patient_roles"), dict) and uc["patient_roles"]:
            logger.info(
                "%s — already migrated (%d patient_roles); skipping",
                email,
                len(uc["patient_roles"]),
            )
            migrated[email] = uc
            skipped += 1
            continue
        derived = _derive_patient_roles(uc)
        if not derived:
            logger.warning("%s — no patient_ids to derive from; skipping", email)
            migrated[email] = uc
            skipped += 1
            continue
        new_uc = {**uc, "patient_roles": derived}
        migrated[email] = new_uc
        logger.info("%s — derived patient_roles=%s", email, derived)

    changed = total - skipped
    logger.info("--- Summary ---")
    logger.info("Total entries scanned: %d", total)
    logger.info("Already migrated (skipped): %d", skipped)
    logger.info("Would migrate: %d", changed)

    if not args.commit:
        logger.info("Dry-run — no writes performed. Re-run with --commit to apply.")
        return 0

    if changed == 0:
        logger.info("Nothing to write. Exiting without touching oncofiles.")
        return 0

    await _snapshot_pre_migration(role_map)
    await _write_migrated(migrated)
    logger.info("Migration complete.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true", help="Perform writes (default: dry-run).")
    parser.add_argument(
        "--email",
        default="",
        help="Migrate only a single email entry. Default: migrate all.",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
