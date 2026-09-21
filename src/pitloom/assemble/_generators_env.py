# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Deployed SBOM generator for the active installed environment.

See also:
- :mod:`pitloom.assemble._generators_shared` for the helpers shared with the
  other generators.
- :mod:`pitloom.assemble._generators` for the project/sdist generator.
- :mod:`pitloom.assemble._generators_wheel` for the built-wheel generator,
  which resolves the same current-directory cascade.
"""

from __future__ import annotations

from pathlib import Path

from pitloom.assemble._generators_shared import _sync_registry
from pitloom.assemble._model_generator import _write_output_file
from pitloom.assemble.spdx3.document import build_deployed
from pitloom.core.config_cascade import (
    ConfigOverrides,
    apply_overrides,
    resolve_generator_config,
)
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.provenance import ProvenanceConfig
from pitloom.extract.env import read_environment
from pitloom.ids import IdRegistry, resolve_registry
from pitloom.logging_config import configure_logging


# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
def generate_env_sbom(
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    offline: bool | None = None,
    content_type_method: str | None = None,
    update_registry: bool | None = None,
) -> str:
    """Generate a Deployed SPDX 3 SBOM for the current installed environment.

    An installed environment carries no ``[tool.pitloom]`` of its own, so
    every unset *setting* falls back to the current directory's
    ``pyproject.toml``
    (:func:`~pitloom.core.config_cascade.resolve_generator_config`) before
    the built-in defaults -- the same set of settings the project surface
    resolves, but read from the current directory rather than from a target
    project. ``creation_metadata`` and ``ids-file`` are deliberately
    excluded, for the reasons
    :func:`~pitloom.assemble.generate_wheel_sbom`'s docstring gives.

    ``content_type_method`` applies here for one of its two jobs only: it
    steers whether each installed package's originator enrichment fetches a
    remote authors file. The per-file ``contentType`` half needs file
    scanning, which reading an installed environment never performs.
    """
    configure_logging()
    project_metadata, env_tree = read_environment()

    cwd = Path.cwd()
    cfg = apply_overrides(
        resolve_generator_config(cwd),
        ConfigOverrides(
            provenance=provenance,
            offline=offline,
            content_type_method=content_type_method,
            pretty=pretty,
            describe_relationship=describe_relationship,
            update_registry=update_registry,
        ),
    )
    # Not cascaded to cfg.ids_file -- see the matching comment in
    # pitloom.assemble._generators_wheel.
    resolved_registry = resolve_registry(cwd, registry)

    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=creation_metadata or CreationMetadata(),
        ai_models=[],
    )
    exporter = build_deployed(
        doc,
        env_tree=env_tree,
        registry=resolved_registry,
        **cfg.assemble_options,
    )

    _sync_registry(exporter, resolved_registry, cfg.update_registry)

    sbom_json = exporter.to_json(
        pretty=cfg.pretty,
        describe_relationship=bool(cfg.describe_relationship),
    )

    _write_output_file(sbom_json, output_path)

    return sbom_json
