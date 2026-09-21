# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An enrichment's ``CreationInfo.created`` follows the pinned datetime.

Enrichment adds a second ``CreationInfo`` (the enricher as its tool). Its
``created`` once came from the wall clock, so two runs a second apart
differed despite ``--creation-datetime``/``SOURCE_DATE_EPOCH``. Every
surface that enriches is checked on the value itself, so the tests do not
depend on how fast they run.

See also: :mod:`tests.assemble.test_provenance_integration` (the N3 shape).
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble import enrich_model, generate_model_sbom, generate_project_sbom
from pitloom.core.creation import CreationMetadata
from tests.assemble.embed_surfaces_shared import demo_project
from tests.cli.shared import SAFETENSORS_FIXTURE

_PINNED = "2026-01-01T00:00:00Z"
#: 2026-01-02T00:00:00Z.
_EPOCH = "1767312000"
_EPOCH_ISO = "2026-01-02T00:00:00Z"
_MODEL_CARD = "---\nlicense: mit\n---\n"


def _model(directory: Path) -> Path:
    """A model file with a model card beside it, so enrichment has a result."""
    directory.mkdir(parents=True, exist_ok=True)
    model = directory / "model.safetensors"
    shutil.copyfile(SAFETENSORS_FIXTURE, model)
    (directory / "README.md").write_text(_MODEL_CARD, encoding="utf-8")
    return model


def _model_sbom(tmp: Path, creation: CreationMetadata | None) -> str:
    return generate_model_sbom(
        _model(tmp / "m"), enrich=True, creation_metadata=creation
    )


def _project_sbom(tmp: Path, creation: CreationMetadata | None) -> str:
    project = demo_project(tmp)
    _model(project / "demo")  # inside the package, so it is scanned
    return generate_project_sbom(
        project, enrich=True, offline=True, creation_metadata=creation
    )


def _fragment(tmp: Path, creation: CreationMetadata | None) -> str:
    return enrich_model(_model(tmp / "m"), creation_metadata=creation)


_SURFACES: dict[str, Callable[[Path, CreationMetadata | None], str]] = {
    "model": _model_sbom,
    "project": _project_sbom,
    "enrich": _fragment,
}


def _created(sbom_json: str) -> list[str]:
    graph = json.loads(sbom_json)["@graph"]
    return [o["created"] for o in graph if o.get("type") == "CreationInfo"]


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_enrichment_created_follows_creation_datetime(
    surface: str, tmp_path: Path
) -> None:
    created = _created(
        _SURFACES[surface](tmp_path, CreationMetadata(creation_datetime=_PINNED))
    )
    assert len(created) >= 2, "no enrichment CreationInfo: the test sees nothing"
    assert set(created) == {_PINNED}


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_enrichment_created_follows_source_date_epoch(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", _EPOCH)
    created = _created(_SURFACES[surface](tmp_path, None))
    assert len(created) >= 2, "no enrichment CreationInfo: the test sees nothing"
    assert set(created) == {_EPOCH_ISO}
