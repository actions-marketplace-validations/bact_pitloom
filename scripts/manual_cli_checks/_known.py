# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Deviations the checks find that are already tracked in
``working-docs/design/roadmap.md``: a failing check matching one of these
globs is reported as ``KNOWN``, with the roadmap item, not ``FAIL``.

Remove an entry as soon as its roadmap item is done, so a regression
fails again. Never add one without a roadmap item to point to.
"""

from __future__ import annotations

import fnmatch

_IGNORED = "Shared options accepted, then silently ignored"

KNOWN: dict[str, str] = {
    "M/*/output/-o=-+*": "`loom <cmd> -o -` corrupts piped JSON",
    "M/enrich/output/no-o+*": "`enrich` and `merge` stdout is not `KEY=VALUE`",
    "M/merge/output/no-o+*": "`enrich` and `merge` stdout is not `KEY=VALUE`",
    "M/*/opt/--max-source-metadata-bytes=-1": (
        "`--max-source-metadata-bytes` accepts a negative value"
    ),
    "M/wheel/opt/--extract-file-header=*": _IGNORED,
    "M/wheel/opt/--content-type*": _IGNORED,
    "M/model/opt/--extract-file-header=*": _IGNORED,
    "M/model/opt/--content-type*": _IGNORED,
    "M/enrich/opt/--extract-file-header=*": _IGNORED,
    "M/enrich/opt/--content-type*": _IGNORED,
    "M/env/opt/--extract-file-header=*": _IGNORED,
    "M/env/opt/--content-type*": _IGNORED,
    "M/embed-wheel/opt/--describe-relationship=--describe-relationship": _IGNORED,
    "M/model/opt/--describe-relationship=--describe-relationship": _IGNORED,
    "M/enrich/opt/--describe-relationship=--describe-relationship": _IGNORED,
    "S2": "Re-embedding lists the previous embedded SBOM",
}


def known_issue(check_id: str) -> str | None:
    """The roadmap item tracking *check_id*'s failure, if any."""
    for pattern, item in KNOWN.items():
        if fnmatch.fnmatchcase(check_id, pattern):
            return f"roadmap: {item}"
    return None
