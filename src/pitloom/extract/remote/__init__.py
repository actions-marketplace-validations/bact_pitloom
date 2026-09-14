# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Remote data source extraction subsystem.

Platform-specific fetchers in this subpackage are internal implementation
modules; callers should use the facade functions exported below.
"""

from __future__ import annotations

from pitloom.extract.remote.huggingface import (
    is_huggingface_source,
    parse_hf_model_id,
    read_huggingface,
)

__all__ = [
    "is_huggingface_source",
    "parse_hf_model_id",
    "read_huggingface",
]
