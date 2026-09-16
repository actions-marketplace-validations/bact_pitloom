# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared raw-bytes JSON-file read.

See also: :mod:`pitloom.extract._toml_io` (the TOML counterpart, same
"propagate exceptions, exception-handling policy stays with the caller"
shape) :mod:`pitloom.extract.lock._common` (``load_lock_json()``, for
lock files -- adds caching and a dict-shape check),
:mod:`pitloom.cli.commands.fragment` (SBOM fragment reads -- also needs
the raw bytes this returns, for a SHA-256 check alongside the JSON
parse).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ["load_json_bytes"]


def load_json_bytes(path: Path) -> tuple[bytes, Any]:
    """Read *path*'s raw bytes and parse them as JSON.

    Returns ``(raw_bytes, parsed)``. Propagates ``OSError`` (including
    ``FileNotFoundError``), ``UnicodeDecodeError``, and
    ``json.JSONDecodeError`` to the caller -- callers decide how to log
    and what fallback to return for each, and may still need
    *raw_bytes* even when only the parse result matters (e.g. for a
    hash check alongside the JSON read).
    """
    raw = path.read_bytes()
    return raw, json.loads(raw.decode("utf-8"))
