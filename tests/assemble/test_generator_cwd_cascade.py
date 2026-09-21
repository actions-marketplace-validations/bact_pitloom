# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A wheel or environment inherits the cwd's policy settings, never its
identity claims.

``generate_wheel_sbom``/``generate_env_sbom`` have no project of their own,
so they resolve the current directory's ``[tool.pitloom]``. That directory
is frequently an unrelated project -- a wheel can sit anywhere on disk --
which splits the config in two:

- *Policy* (``pretty``, ``offline``, ``content_type_method``, ...) says how
  to generate, and inheriting it is the point of the cascade.
- *Identity* (``creators``, ``creation-datetime``, ``creation-comment``)
  asserts who produced this SBOM and when. Inheriting that would name a
  stranger as the creator of this wheel's SBOM and override
  ``SOURCE_DATE_EPOCH`` with their pinned timestamp.

``ids-file`` is excluded for a third reason: adopting the cwd project's
registry breaks determinism outright (see the test at the bottom).

Both halves are asserted together on purpose: an assertion that the
identity did not leak passes just as well when the whole cascade is dead,
so each test also pins a policy setting that must have come through.

See also: :mod:`tests.assemble.test_embed_overrides`'s
``test_cli_wheel_embed_ignores_cwd_project`` for the CLI counterpart, which
cannot reach this because the CLI passes a resolved ``creation_metadata``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from pitloom.assemble import generate_env_sbom, generate_wheel_sbom
from pitloom.ids import EntityEntry, FileEntry, IdRegistry

from .conftest import _make_dummy_wheel

_COMMENT = "comment-from-an-unrelated-cwd-project"
_DATETIME = "2001-02-03T04:05:06Z"
_CREATOR = "Creator Of An Unrelated Cwd Project"
_IDS_FILE = "cwd-project-ids.json"
# Every id this registry holds lives here, so its presence anywhere in an
# SBOM means the registry was adopted.
_IDS_NAMESPACE = "https://example.invalid/cwd-project-ids"
_TARGET = "targetpkg"

_CWD_PROJECT = f"""
[project]
name = "unrelated-cwd-project"
version = "9.9.9"

[tool.pitloom]
pretty = true
ids-file = "{_IDS_FILE}"
creation-comment = "{_COMMENT}"
creation-datetime = "{_DATETIME}"

[[tool.pitloom.creator]]
name = "{_CREATOR}"
type = "person"
"""


def _seed_registry(path: Path, wheel: Path | None = None) -> None:
    """Write a registry holding ids the target *would* pick up if adopted.

    An empty registry cannot tell "adopted" from "not adopted" on a first
    run -- it supplies nothing either way. Seeding an entity (looked up by
    name, which the env surface does) and, given a wheel, a file entry
    (looked up by path and digest, which the wheel surface does) makes
    adoption visible in the SBOM itself, whether or not anything is
    written back.
    """
    registry = IdRegistry(namespace=_IDS_NAMESPACE, path=path)
    registry.entities[_TARGET] = EntityEntry(
        spdx_id=f"{_IDS_NAMESPACE}#Package-seeded", type="software_Package"
    )
    if wheel is not None:
        member = f"{_TARGET}/__init__.py"
        with zipfile.ZipFile(wheel) as archive:
            digest = hashlib.sha256(archive.read(member)).hexdigest()
        registry.files[member] = FileEntry(
            spdx_id=f"{_IDS_NAMESPACE}#File-seeded", sha256=digest
        )
    registry.save()


@pytest.fixture(name="cwd_project")
def _cwd_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Stand in a project that has nothing to do with the target."""
    root = tmp_path / "somewhere-else"
    root.mkdir()
    (root / "pyproject.toml").write_text(_CWD_PROJECT, encoding="utf-8")
    _seed_registry(root / _IDS_FILE)
    monkeypatch.chdir(root)
    return root


def _assert_policy_in_identity_out(sbom_json: str) -> None:
    """``pretty`` came through; nothing identifying the cwd project did,
    and none of its registry's ids were adopted."""
    assert "\n  " in sbom_json, "pretty from the cwd config did not apply"
    assert _COMMENT not in sbom_json
    assert _DATETIME not in sbom_json
    assert _CREATOR not in sbom_json
    assert "unrelated-cwd-project" not in sbom_json
    assert _IDS_NAMESPACE not in sbom_json, "the cwd project's registry was adopted"
    assert json.loads(sbom_json)["@graph"]


def test_wheel_sbom_takes_cwd_policy_not_cwd_identity(
    tmp_path: Path, cwd_project: Path
) -> None:
    wheel = _make_dummy_wheel(tmp_path / "dist", _TARGET, "1.0.0")
    _seed_registry(cwd_project / _IDS_FILE, wheel)
    _assert_policy_in_identity_out(generate_wheel_sbom(wheel, offline=True))


def test_env_sbom_takes_cwd_policy_not_cwd_identity(
    cwd_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = [
        {
            "package": {
                "key": _TARGET,
                "package_name": _TARGET,
                "installed_version": "1.0.0",
            }
        }
    ]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            args=["pipdeptree"], returncode=0, stdout=json.dumps(tree), stderr=""
        ),
    )
    _assert_policy_in_identity_out(generate_env_sbom(offline=True))


def test_wheel_sbom_does_not_adopt_the_cwd_ids_file(
    tmp_path: Path, cwd_project: Path
) -> None:
    """Repeat runs stay deterministic and mint no duplicate spdxId.

    Adopting the cwd project's registry made run 2 take the harvested ids
    for the files that carry a digest, then re-mint the remaining
    (directory) elements from a counter restarting at 1 -- which does not
    reserve the registry-supplied numbers, so two ``software_File``
    elements collided on one spdxId. The registry file must also stay
    untouched: this wheel's ids do not belong to that project.
    """
    wheel = _make_dummy_wheel(tmp_path / "dist", _TARGET, "1.0.0")
    _seed_registry(cwd_project / _IDS_FILE, wheel)
    registry_before = (cwd_project / _IDS_FILE).read_bytes()

    runs = [generate_wheel_sbom(wheel, offline=True) for _ in range(3)]

    assert runs[0] == runs[1] == runs[2]
    file_ids = [
        element["spdxId"]
        for element in json.loads(runs[-1])["@graph"]
        if element.get("type") == "software_File"
    ]
    assert len(file_ids) == len(set(file_ids)), f"duplicate spdxId: {file_ids}"
    assert (cwd_project / _IDS_FILE).read_bytes() == registry_before
