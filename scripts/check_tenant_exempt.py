#!/usr/bin/env python3
"""CI grep-gate for tenant isolation (#435 Item 6).

Scans `src/oncoteam/` for call sites that pass `token=None` to oncofiles
wrapper functions. Each such site must declare intent with a
`# tenant-exempt: <reason>` comment on the same line or the line
immediately above it — otherwise we risk a silent cross-tenant fallback
to the admin bearer (the class of bug that caused oncofiles#478).

Exits 0 if every `token=None` hit is annotated, exits 1 with a list of
offenders otherwise. Running locally:

    uv run python scripts/check_tenant_exempt.py

CI wires this into `.github/workflows/ci.yml` so any PR that introduces a
new unannotated caller fails before merging.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_TOKEN_NONE_RE = re.compile(r"\btoken\s*=\s*None\b")
_EXEMPT_MARKER = "tenant-exempt"
_SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "oncoteam"
# Signatures of wrapper functions — their `token: str | None = None` kwarg
# declaration is NOT a caller passing None; it's the library API. Distinguish
# by leaving the declaration on a line that starts with `def ` or `async def`.
_SKIP_DEF_RE = re.compile(r"^\s*(async\s+)?def\b")


def _find_unannotated(path: Path) -> list[tuple[int, str]]:
    """Return (line_no, source) tuples for unannotated `token=None` sites."""
    offenders: list[tuple[int, str]] = []
    text = path.read_text()
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if not _TOKEN_NONE_RE.search(line):
            continue
        if _SKIP_DEF_RE.match(line):
            continue  # fn signature default, not a caller passing None
        # Accept `# tenant-exempt:` on the same line or the line above.
        if _EXEMPT_MARKER in line:
            continue
        if idx > 0 and _EXEMPT_MARKER in lines[idx - 1]:
            continue
        offenders.append((idx + 1, line.rstrip()))
    return offenders


def main() -> int:
    if not _SRC_ROOT.exists():
        print(f"error: src root not found at {_SRC_ROOT}", file=sys.stderr)
        return 2
    any_offenders = False
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        offenders = _find_unannotated(path)
        if not offenders:
            continue
        any_offenders = True
        rel = path.relative_to(_SRC_ROOT.parent.parent)
        for line_no, source in offenders:
            print(f"::error file={rel},line={line_no}::{rel}:{line_no}: {source.strip()}")
            print(f"  {rel}:{line_no}  {source.strip()}", file=sys.stderr)
    if any_offenders:
        print(
            "\nUnannotated `token=None` call sites break the tenant-isolation "
            "contract (#435 Item 6). Every system-scoped caller must declare "
            "intent with a `# tenant-exempt: <reason>` comment on the same line "
            "or the line above. Patient-scoped call sites must pass an explicit "
            "per-patient token via `get_token_for_patient(patient_id)`.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
