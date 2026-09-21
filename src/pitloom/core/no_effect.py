# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one ``WARNING:`` shape for an explicit option that has no effect.

Every "has no effect" warning -- a build flag without ``--allow-build``, an
option the target cannot act on, ``--use-lockfile`` for a non-project
target -- is logged here, so the wording cannot drift between subsystems:

``WARNING: <prefix><subject>: <flag> has no effect <reason>``

No leading underscore: imported from ``pitloom.extract`` and
``pitloom.assemble`` as well as from within ``pitloom.core``.

See also: :mod:`pitloom.core.build_options` and
:mod:`pitloom.core.inert_options`, the two callers that decide *which*
flags to warn about.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

log = logging.getLogger(__name__)

INERT_LOG_PREFIX = "Options: "
"""Sub-prefix for an option the target or command cannot act on -- sibling
of :data:`pitloom.core._models_wheel_types.BUILD_LOG_PREFIX`."""


def warn_no_effect(
    prefix: str, subject: object, flags: Iterable[str], reason: str
) -> None:
    """Log one ``WARNING:`` per flag in *flags*, in the given order.

    *reason* follows "has no effect" with no trailing punctuation, e.g.
    ``"without --allow-build"``.
    """
    for flag in flags:
        log.warning("%s%s: %s has no effect %s", prefix, subject, flag, reason)


__all__ = ["INERT_LOG_PREFIX", "warn_no_effect"]
