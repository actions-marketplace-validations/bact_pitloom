# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one check that an SBOM file name is a name, not a path.

Shared by the ``sbom-basename`` config key
(:mod:`pitloom.core._config_parse`) and the name an SBOM is embedded under
in a wheel (:mod:`pitloom._embed_wheel`), so the two cannot disagree.
"""

from __future__ import annotations

#: A path separator (either platform), a Windows drive or alternate-data-
#: stream colon, or NUL.
_NOT_IN_A_FILE_NAME = frozenset({"/", "\\", ":", "\x00"})


def is_plain_file_name(name: str) -> bool:
    """Whether *name* (surrounding whitespace ignored) is a non-empty file
    name that cannot name another directory: no separator, colon or NUL,
    and not ``.``/``..``."""
    clean = name.strip()
    return (
        bool(clean)
        and clean not in (".", "..")
        and not any(c in clean for c in _NOT_IN_A_FILE_NAME)
    )


__all__ = ["is_plain_file_name"]
