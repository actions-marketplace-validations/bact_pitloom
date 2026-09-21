# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one configuration cascade every SBOM-producing surface resolves through.

Pitloom is invoked from several surfaces (CLI subcommands, the library API,
the Hatchling build hook, the GitHub Action). A surface resolving
``[tool.pitloom]`` and its per-run overrides itself is what lets a setting
reach the assembler only where a call site remembers to pass it. Both halves
of the cascade live here so that no surface has to:

- :func:`resolve_generator_config` -- read the local ``[tool.pitloom]``.
- :func:`apply_overrides` -- layer one run's explicit choices on top.

Together they give the hierarchy AGENTS.md mandates: per-run override >
``pyproject.toml`` > hardcoded default. Adding a setting means one
:class:`~pitloom.core.config.PitloomConfig` field, one
:class:`ConfigOverrides` field and one line in :func:`apply_overrides` --
instead of one resolution expression per setting per surface.

This is the goal, not yet the whole state: :mod:`pitloom.embed` reads
``[tool.pitloom]`` by its own route before handing it to
:func:`apply_overrides`, while :mod:`pitloom.plugins.hatch` and
:mod:`pitloom.cli.options_resolve` still read *and* resolve it themselves --
the hook splatting ``PitloomConfig.assemble_options`` directly, the CLI
running its own ``_resolve_bool_cascade()`` per setting.

No leading underscore: imported from outside ``pitloom.core`` (see AGENTS.md
"Naming"). This module must never import from ``pitloom.assemble`` or
``pitloom.embed`` -- the dependency runs one way, and a cycle here would be
imported by every surface at once.

See also: :attr:`~pitloom.core.config.PitloomConfig.assemble_options`, the
matching hand-off from a resolved config into the assemblers.
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Any

from pitloom.core._config_types import _require_valid_content_type_method
from pitloom.core.build_options import BuildOptions
from pitloom.core.config import PitloomConfig, read_pitloom_config
from pitloom.core.provenance import ProvenanceConfig

log = logging.getLogger(__name__)

__all__ = [
    "ConfigOverrides",
    "apply_overrides",
    "resolve_generator_config",
]


@dataclasses.dataclass(frozen=True)
class ConfigOverrides:
    """Per-run overrides layered onto a project's ``[tool.pitloom]`` config.

    Every field defaults to ``None``, meaning "not given, defer to the
    config"; any other value wins, including one equal to the built-in
    default. Each maps to the ``PitloomConfig`` field of the same name,
    except ``enrich`` -> ``enrich_local`` and ``content_type`` ->
    ``content_type_enabled``.

    Attributes:
        provenance: Replaces the config's whole provenance settings, not
            field by field: a field left at its default resets the
            config's value, including ``max_source_metadata_bytes``.
        pretty: Read by the project/wheel/env generators only. The embed
            path (``embed_wheel_sbom(overrides=...)``) merges it and then
            serialises with ``pretty=False`` regardless -- a wheel-embedded
            SBOM is JCS-canonical by PEP 770, not a human-read artifact.
        describe_relationship: Same reach as ``pretty``, for the same
            reason.
        update_registry: Same reach as ``pretty``; the embed path never
            harvests ids back into a registry at all.
        build_options: ``--allow-build`` and its companion flags (see
            :class:`~pitloom.core.build_options.BuildOptions`). Unlike
            every other field here, deliberately has no
            ``[tool.pitloom]`` cascade to defer to, and is read by
            ``embed-wheel`` alone -- :func:`apply_overrides` never touches
            it, and ``generate_project_sbom()`` takes its own separate
            ``build_options`` parameter rather than reading this one.
            Threaded into
            ``_build_sbom_from_project_and_wheel()``'s own project-dir
            rescan, whose only use for the resulting file list is
            layering content-type/file-header extras onto the wheel's
            already-known files (see that function's own comment on
            discarding the rescan's ``merkle_root``/digests) -- so on a
            project whose backend has no static discovery module (or
            whose static discovery fails), enabling this runs a full,
            real, potentially slow PEP 517 build *purely* to compute
            those extras more accurately, not to learn the file list
            itself (the wheel's own ``read_wheel()`` result already has
            that). Deliberate: this is the only way ``embed-wheel``
            avoids silently staying stuck on the Hatchling-heuristic
            rescan for such a project's content-type/header extras.
    """

    provenance: ProvenanceConfig | None = None
    enrich: bool | None = None
    extract_file_header: bool | None = None
    content_type: bool | None = None
    content_type_method: str | None = None
    offline: bool | None = None
    pretty: bool | None = None
    describe_relationship: bool | None = None
    update_registry: bool | None = None
    build_options: BuildOptions = BuildOptions()


def resolve_generator_config(target_dir: Path) -> PitloomConfig:
    """Return the ``[tool.pitloom]`` config a generator should start from,
    read from *target_dir*'s ``pyproject.toml``.

    A missing ``pyproject.toml`` is not an error -- a wheel, a model file or
    an installed environment is a legitimate target with no project of its
    own, and the defaults apply (see AGENTS.md's "absent source data is not
    an error"). Every other failure of that file *is* a genuine failure of a
    source that claimed to carry settings, so each is reported and then
    stepped over rather than aborting SBOM generation: a config Pitloom
    cannot read is no reason to produce no SBOM at all.

    The ``OSError`` branch is not hypothetical. A no-permission or
    directory-shaped ``pyproject.toml`` raises something other than
    ``FileNotFoundError``, and this one helper stands in front of four
    generators (see AGENTS.md on the errno set ``Path.exists()`` swallows).
    """
    try:
        return read_pitloom_config(target_dir / "pyproject.toml")
    except FileNotFoundError:
        return PitloomConfig()
    except ValueError as exc:
        log.warning("Ignoring invalid pyproject.toml in %s: %s", target_dir, exc)
        return PitloomConfig()
    except OSError as exc:
        log.warning("Ignoring unreadable pyproject.toml in %s: %s", target_dir, exc)
        return PitloomConfig()


def apply_overrides(cfg: PitloomConfig, overrides: ConfigOverrides) -> PitloomConfig:
    """Layer one run's explicit overrides onto *cfg*.

    A field left ``None`` defers to *cfg*; anything else wins, including a
    value that happens to equal the built-in default (``0``/``False`` are
    explicit choices, not absences -- see AGENTS.md's ``None`` vs empty
    tri-state rule).

    Raises:
        ValueError: if the *resulting* content-type method is not one of
            :data:`~pitloom.core.config.VALID_CONTENT_TYPE_METHODS`. The
            effective value is what gets checked, not just the override, so
            a hand-built :class:`~pitloom.core.config.PitloomConfig` cannot
            smuggle an invalid method past a caller that overrode nothing.
    """
    changes: dict[str, Any] = {}
    if overrides.provenance is not None:
        # Every ProvenanceConfig field maps to PitloomConfig.provenance_<name>;
        # a field without one fails in dataclasses.replace() below, never
        # silently. Fields are read from the class, so a subclass's extras
        # are ignored.
        for prov_field in dataclasses.fields(ProvenanceConfig):
            changes[f"provenance_{prov_field.name}"] = getattr(
                overrides.provenance, prov_field.name
            )
    if overrides.enrich is not None:
        changes["enrich_local"] = overrides.enrich
    if overrides.extract_file_header is not None:
        changes["extract_file_header"] = overrides.extract_file_header
    if overrides.content_type is not None:
        changes["content_type_enabled"] = overrides.content_type
    if overrides.content_type_method is not None:
        changes["content_type_method"] = overrides.content_type_method
    if overrides.offline is not None:
        changes["offline"] = overrides.offline
    if overrides.pretty is not None:
        changes["pretty"] = overrides.pretty
    if overrides.describe_relationship is not None:
        changes["describe_relationship"] = overrides.describe_relationship
    if overrides.update_registry is not None:
        changes["update_registry"] = overrides.update_registry
    merged = dataclasses.replace(cfg, **changes)
    _require_valid_content_type_method(merged.content_type_method)
    return merged
