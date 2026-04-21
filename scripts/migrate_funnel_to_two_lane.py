#!/usr/bin/env python3
"""Migrate legacy flat funnel stages to the two-lane model (#395).

Legacy storage (pre-#395):
    agent_state["funnel_stages:{patient_id}"] = {nct_id: stage_str, ...}

New storage (#395):
    agent_state["funnel_cards:{patient_id}"] = {"cards": {card_id: FunnelCard, ...}}
    agent_state["funnel_audit:{patient_id}:{card_id}"] = {"events": [FunnelAuditEvent, ...]}
    agent_state["funnel_snapshot:{patient_id}:{YYYYMMDD}"] = {"entries": {nct_id: stage_str, ...}}

Guarantees:
    - Legacy `funnel_stages` key is READ, then LEFT UNTOUCHED. Rollback is just
      "ignore the new cards" — no lossy transform.
    - A snapshot is written under `funnel_snapshot:{patient_id}:{YYYYMMDD}` so
      the pre-migration state is recoverable even if the legacy key is later
      removed.
    - Each migrated NCT lands in the clinical lane at its legacy stage, with a
      single `migrated_from_v1` audit event carrying actor_type=human,
      actor_id="migration-script", rationale="automated migration to two-lane".
    - Legacy stage names (Excluded / Later Line / Watching / Eligible Now /
      Action Needed) are mapped to the new 5-stage kanban:
          Excluded      -> Archived (rationale: "excluded in v1")
          Later Line    -> Watching
          Watching      -> Watching
          Eligible Now  -> Candidate
          Action Needed -> Qualified

Usage:
    uv run python scripts/migrate_funnel_to_two_lane.py --dry-run
    uv run python scripts/migrate_funnel_to_two_lane.py --patient q1b --commit
    uv run python scripts/migrate_funnel_to_two_lane.py --all --commit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure repo root is on path so `oncoteam.*` imports work when run directly.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from oncoteam import oncofiles_client  # noqa: E402
from oncoteam.funnel_audit import (  # noqa: E402
    record_event,
    upsert_card,
)
from oncoteam.models import (  # noqa: E402
    FunnelActorType,
    FunnelCard,
    FunnelEventType,
    FunnelLane,
)
from oncoteam.patient_context import (  # noqa: E402
    _patient_registry,  # intentional — migration needs the full registry
    get_patient_token,
)

logger = logging.getLogger("migrate_funnel_to_two_lane")


# Legacy stage → new clinical stage + optional archival rationale.
_LEGACY_STAGE_MAP: dict[str, tuple[str, str | None]] = {
    "Excluded": ("Archived", "excluded in v1 (auto-migrated)"),
    "Later Line": ("Watching", None),
    "Watching": ("Watching", None),
    "Eligible Now": ("Candidate", None),
    "Action Needed": ("Qualified", None),
}

_SNAPSHOT_KEY = "funnel_snapshot:{patient_id}:{date}"
_LEGACY_KEY = "funnel_stages:{patient_id}"


async def _read_legacy(patient_id: str, token: str | None) -> dict:
    """Read the legacy `funnel_stages:{patient_id}` agent_state key."""
    try:
        raw = await oncofiles_client.get_agent_state(
            _LEGACY_KEY.format(patient_id=patient_id), token=token
        )
    except Exception as e:
        logger.warning("could not read legacy funnel_stages for %s: %s", patient_id, e)
        return {}
    value = raw.get("result") or raw.get("value") or {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            logger.warning("legacy funnel_stages for %s was a non-JSON string", patient_id)
            return {}
    if not isinstance(value, dict):
        return {}
    return value


async def _write_snapshot(
    patient_id: str, legacy: dict, *, token: str | None, dry_run: bool
) -> str:
    """Persist a dated snapshot of the legacy state (never deleted)."""
    date_str = datetime.now(UTC).strftime("%Y%m%d")
    key = _SNAPSHOT_KEY.format(patient_id=patient_id, date=date_str)
    if dry_run:
        logger.info("[dry-run] would write snapshot %s (%d entries)", key, len(legacy))
        return key
    await oncofiles_client.set_agent_state(
        key,
        {"entries": legacy, "source_key": _LEGACY_KEY.format(patient_id=patient_id)},
        token=token,
    )
    logger.info("wrote snapshot %s (%d entries)", key, len(legacy))
    return key


async def _migrate_one_nct(
    patient_id: str,
    nct_id: str,
    legacy_stage: str,
    *,
    token: str | None,
    dry_run: bool,
) -> tuple[bool, str]:
    """Migrate one NCT to the new schema. Returns (did_write, message)."""
    mapped = _LEGACY_STAGE_MAP.get(legacy_stage)
    if mapped is None:
        return False, f"no mapping for legacy stage {legacy_stage!r}"
    new_stage, extra_rationale = mapped
    card_id = f"{patient_id}_{nct_id}"

    rationale_parts = [f"automated migration to two-lane; legacy stage={legacy_stage!r}"]
    if extra_rationale:
        rationale_parts.append(extra_rationale)
    rationale = "; ".join(rationale_parts)

    if dry_run:
        return True, (
            f"[dry-run] would create clinical-lane card {card_id} "
            f"at stage={new_stage!r} (from legacy {legacy_stage!r})"
        )

    card = FunnelCard(
        card_id=card_id,
        patient_id=patient_id,
        nct_id=nct_id,
        lane=FunnelLane.CLINICAL,
        current_stage=new_stage,
        source_agent="migration-script",
        source_run_id=f"migrate_funnel_to_two_lane:{datetime.now(UTC).isoformat()}",
    )
    await upsert_card(card, token=token)
    await record_event(
        card_id=card.card_id,
        patient_id=patient_id,
        nct_id=nct_id,
        actor_type=FunnelActorType.HUMAN,  # treat migration as human-authored
        actor_id="migration-script",
        actor_display_name="Legacy migration (v1 → v2)",
        event_type=FunnelEventType.MIGRATED_FROM_V1,
        from_stage=legacy_stage,
        to_stage=new_stage,
        rationale=rationale,
        metadata={"source_key": _LEGACY_KEY.format(patient_id=patient_id)},
        token=token,
    )
    return True, f"migrated {card_id} → {new_stage!r}"


async def migrate_patient(patient_id: str, *, dry_run: bool) -> dict:
    """Migrate one patient. Returns {migrated, skipped, snapshot_key, errors}."""
    token = get_patient_token(patient_id)
    legacy = await _read_legacy(patient_id, token)
    if not legacy:
        return {
            "patient_id": patient_id,
            "migrated": 0,
            "skipped": 0,
            "errors": [],
            "snapshot_key": None,
            "message": "no legacy data — nothing to migrate",
        }

    snapshot_key = await _write_snapshot(patient_id, legacy, token=token, dry_run=dry_run)

    migrated = 0
    skipped = 0
    errors: list[str] = []
    for nct_id, legacy_stage in legacy.items():
        if not isinstance(legacy_stage, str):
            skipped += 1
            errors.append(f"{nct_id}: non-string stage {legacy_stage!r}")
            continue
        try:
            did_write, msg = await _migrate_one_nct(
                patient_id, nct_id, legacy_stage, token=token, dry_run=dry_run
            )
            logger.info("[%s] %s", patient_id, msg)
            if did_write:
                migrated += 1
            else:
                skipped += 1
                errors.append(msg)
        except Exception as e:
            skipped += 1
            errors.append(f"{nct_id}: {e}")
            logger.exception("failed to migrate %s for %s", nct_id, patient_id)

    return {
        "patient_id": patient_id,
        "migrated": migrated,
        "skipped": skipped,
        "errors": errors,
        "snapshot_key": snapshot_key,
    }


async def main_async(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    patient_ids = list(_patient_registry.keys()) if args.all else [args.patient]

    dry_run = not args.commit

    if dry_run:
        logger.info("DRY RUN — no writes will occur. Pass --commit to apply.")

    results = []
    for pid in patient_ids:
        r = await migrate_patient(pid, dry_run=dry_run)
        results.append(r)

    print(json.dumps({"dry_run": dry_run, "results": results}, indent=2, default=str))
    total_errors = sum(len(r["errors"]) for r in results)
    return 0 if total_errors == 0 else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--patient", help="Patient ID to migrate (e.g. q1b)")
    g.add_argument("--all", action="store_true", help="Migrate every registered patient")
    ap.add_argument(
        "--commit",
        action="store_true",
        help="Perform writes. Without this flag, runs in dry-run mode.",
    )
    args = ap.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
