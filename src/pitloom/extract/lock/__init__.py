# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Lockfile and pinned dependency extraction subsystem.

Format-specific lockfile extractors in this subpackage are internal
implementation modules; callers should use apply_locked_dependencies().
"""

from __future__ import annotations

from pitloom.extract.lock.cascade import apply_locked_dependencies

__all__ = [
    "apply_locked_dependencies",
]
