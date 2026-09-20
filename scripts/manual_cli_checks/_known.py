# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Deviations the checks find that are already tracked in
``working-docs/design/roadmap.md``: a failing check matching one of these
globs *with its tracked failure text* is reported as ``KNOWN``, with the
roadmap item, not ``FAIL``.

Remove an entry as soon as its roadmap item is done, so a regression
fails again. Never add one without a roadmap item to point to.
"""

from __future__ import annotations

import fnmatch

_IGNORED = "Shared options accepted, then silently ignored"
_IGNORED_SIGN = "expected changes, got same"
_PIPED = "`loom <cmd> -o -` corrupts piped JSON"
_KV = "`enrich` and `merge` stdout is not `KEY=VALUE`"

# Check-id glob -> (roadmap item, text the failure detail must contain).
# Both must match: any other failure in the same cell still FAILs.
KNOWN: dict[str, tuple[str, str]] = {
    **{
        f"M/{cmd}/output/-o=-+*": (_PIPED, "JSONDecodeError: Extra data")
        for cmd in ("generate", "project", "wheel", "model", "enrich", "env")
    },
    "M/enrich/output/no-o+*": (_KV, "stdout: ['Enrichment fragment written to"),
    "M/merge/output/no-o+*": (_KV, "stdout: ['pitloom: merged"),
    "M/*/opt/--max-source-metadata-bytes=-1": (
        "`--max-source-metadata-bytes` accepts a negative value",
        "exit 0, want 2",
    ),
    **{
        f"M/{cmd}/opt/{variant}": (_IGNORED, _IGNORED_SIGN)
        for cmd in ("wheel", "model", "enrich", "env")
        for variant in (
            "--extract-file-header=--no-extract-file-header",
            "--content-type=--content-type",
            "--content-type-method=extension",
        )
    },
    **{
        f"M/{cmd}/opt/--describe-relationship=--describe-relationship": (
            _IGNORED,
            _IGNORED_SIGN,
        )
        for cmd in ("embed-wheel", "model", "enrich")
    },
    "S2": (
        "Re-embedding lists the previous embedded SBOM",
        "re-embedding changed the SBOM",
    ),
}


def known_issue(check_id: str, detail: str) -> str | None:
    """The roadmap item tracking *check_id*'s failure, if *detail* is
    the tracked failure."""
    for pattern, (item, sign) in KNOWN.items():
        if fnmatch.fnmatchcase(check_id, pattern) and sign in detail:
            return f"roadmap: {item}"
    return None
