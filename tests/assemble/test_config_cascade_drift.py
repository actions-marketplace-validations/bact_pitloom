# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every config-resolved setting reaches every entry point that can act on it.

A setting that reaches an assembler only where a call site remembers to pass it
stops working on one surface while every other surface's tests keep passing.
These guards are structural: they read the real signatures, so a setting added
to :class:`~pitloom.core.config.AssembleOptions` and forgotten at one entry
point fails here rather than in whichever surface someone happens to exercise.

The matrix covers both layers, because a drop at either one is invisible from
the other: the three assemblers the config splats into, and the library
generators that resolve the cascade and call them.

An entry point that genuinely cannot act on a setting is *declared* in
``_NOT_APPLICABLE`` with a reason -- never silently absent.

A signature check alone cannot see a parameter that is accepted and then
dropped on the floor, which is the same defect one layer in. That half is
:mod:`tests.assemble.test_embed_build_seam`'s: it spies on the one leaf both
assemblers funnel every dependency through, so a value that never arrives
fails there. Neither guard replaces the other.

See also:
- :mod:`tests.assemble.test_embed_build_seam` for the per-surface value checks.
- :mod:`tests.core.test_config_cascade` for the cascade's own unit tests.
- :mod:`tests.test_build_flag_warnings` for the matrix idiom copied here.
"""

from __future__ import annotations

import dataclasses
import inspect
import itertools
from collections.abc import Callable
from typing import Any

import pytest

from pitloom.assemble import (
    generate_env_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.assemble.spdx3._document_model import build_model
from pitloom.assemble.spdx3.document import build, build_deployed
from pitloom.core.config import AssembleOptions, PitloomConfig
from pitloom.core.config_cascade import ConfigOverrides

_ENTRY_POINTS: dict[str, Callable[..., Any]] = {
    # The assemblers the resolved config splats into.
    "build": build,
    "build_deployed": build_deployed,
    "build_model": build_model,
    # The library generators that resolve the cascade and call them.
    "generate_project_sbom": generate_project_sbom,
    "generate_wheel_sbom": generate_wheel_sbom,
    "generate_env_sbom": generate_env_sbom,
    "generate_model_sbom": generate_model_sbom,
}

_MODEL_REASON = (
    "a standalone model file has no dependency graph to enrich, so the method "
    "-- which only steers dependency originator enrichment -- has nothing to "
    "steer"
)

# (entry point, setting) -> why it cannot act on that setting. Declaring it
# here is what keeps the missing parameter honest: the guard below fails if
# such a parameter is ever added anyway, since accepting a setting the callee
# ignores is exactly the silent-drop defect this module guards against.
_NOT_APPLICABLE: dict[tuple[str, str], str] = {
    ("build_model", "offline"): (
        "a standalone model file has no dependency graph to enrich, so nothing "
        "here ever reaches the network"
    ),
    ("build_model", "content_type_method"): _MODEL_REASON,
    ("generate_model_sbom", "content_type_method"): _MODEL_REASON,
}

_CASES = [
    (name, setting)
    for name, setting in itertools.product(
        _ENTRY_POINTS, AssembleOptions.__annotations__
    )
    if (name, setting) not in _NOT_APPLICABLE
]


@pytest.mark.parametrize(
    ("entry_point", "setting"),
    _CASES,
    ids=[f"{name}:{setting}" for name, setting in _CASES],
)
def test_entry_point_accepts_every_applicable_setting(
    entry_point: str, setting: str
) -> None:
    """The config hand-off reaches this entry point, so it must name the
    setting as a keyword parameter."""
    parameters = inspect.signature(_ENTRY_POINTS[entry_point]).parameters
    assert setting in parameters, (
        f"{entry_point}() cannot receive {setting!r} from "
        f"PitloomConfig.assemble_options; add the parameter, or declare the "
        f"pair in _NOT_APPLICABLE with a reason"
    )


@pytest.mark.parametrize(
    ("entry_point", "setting"),
    sorted(_NOT_APPLICABLE),
    ids=[f"{name}:{setting}" for name, setting in sorted(_NOT_APPLICABLE)],
)
def test_declared_inapplicable_setting_is_not_quietly_accepted(
    entry_point: str, setting: str
) -> None:
    """A setting declared inapplicable must genuinely be absent. If someone
    adds the parameter, either it is now used -- and the declaration is stale
    -- or it is accepted and ignored, which is the defect itself."""
    parameters = inspect.signature(_ENTRY_POINTS[entry_point]).parameters
    assert setting not in parameters, (
        f"{entry_point}() now accepts {setting!r}, which _NOT_APPLICABLE says "
        f"it cannot act on; either wire it through or drop the declaration"
    )


def test_matrix_accounts_for_every_cell() -> None:
    """Every (entry point, setting) pair either runs or is declared, with a
    reason, and every entry point and setting appears at least once."""
    cells = set(itertools.product(_ENTRY_POINTS, AssembleOptions.__annotations__))
    assert set(_NOT_APPLICABLE) <= cells
    assert set(_CASES) | set(_NOT_APPLICABLE) == cells
    assert not set(_CASES) & set(_NOT_APPLICABLE)
    assert all(reason.strip() for reason in _NOT_APPLICABLE.values())
    assert {name for name, _ in _CASES} == set(_ENTRY_POINTS)
    assert {setting for _, setting in _CASES} == set(AssembleOptions.__annotations__)


def test_assemble_options_keys_all_exist_on_the_config() -> None:
    """Each key is really resolved from a config, so the cascade cannot hand
    over a value that no ``[tool.pitloom]`` setting can ever supply."""
    options = PitloomConfig().assemble_options
    assert set(options) == set(AssembleOptions.__annotations__)


def test_config_overrides_can_express_every_assemble_option() -> None:
    """The per-run layer has to be able to override anything the assemblers
    read, or a flag has no field to land in and the cascade stops one short
    of the surface that needs it."""
    fields = {f.name for f in dataclasses.fields(ConfigOverrides)}
    assert set(AssembleOptions.__annotations__) <= fields
