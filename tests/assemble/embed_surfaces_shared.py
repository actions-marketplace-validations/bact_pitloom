# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One demo project, run through the surfaces that hand a resolved
``[tool.pitloom]`` config to the assembler: ``generate_project_sbom``,
``generate_wheel_sbom``, ``generate_env_sbom``, ``embed_wheel_sbom``,
``loom embed-wheel`` and the Hatchling build hook.

The wheel and environment surfaces have no project of their own, so their
cascade reads the *current directory*'s ``[tool.pitloom]``; their runners
``chdir`` into the demo project to give them one.

Shared by :mod:`tests.assemble.test_embed_build_seam` (what reaches the
assembler) and :mod:`tests.assemble.test_embed_authors_fetch` (what the
assembler then does with it), so both exercise the same surfaces.

The demo declares one dependency, ``fakedep==1.0``; it is not installed, so
it is inert unless a test supplies its installed metadata.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import (
    generate_env_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import load_config_file
from pitloom.core.provenance import ProvenanceConfig
from pitloom.embed import ConfigOverrides, embed_wheel_sbom
from tests.assemble.conftest import _make_dummy_wheel
from tests.extract.conftest import make_hook

DEPENDENCY = "fakedep"

_PYPROJECT = f"""\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1.0.0"
requires-python = ">=3.10"
dependencies = ["{DEPENDENCY}==1.0"]
"""


def demo_project(tmp_path: Path, pitloom_toml: str = "") -> Path:
    """Write the demo project under *tmp_path*; return its directory."""
    root = tmp_path / "proj"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(_PYPROJECT + pitloom_toml, encoding="utf-8")
    return root


def demo_wheel(tmp_path: Path) -> Path:
    """Write a minimal wheel for the demo project under *tmp_path*."""
    return _make_dummy_wheel(
        tmp_path / "dist", "demo", "1.0.0", requires_dist=(f"{DEPENDENCY}==1.0",)
    )


def config_toml(method: str | None, max_bytes: int | None) -> str:
    """``[tool.pitloom...]`` tables for the given config-file values."""
    toml = ""
    if method is not None:
        toml += f'\n[tool.pitloom.content-type]\nmethod = "{method}"\n'
    if max_bytes is not None:
        toml += (
            f"\n[tool.pitloom.provenance]\nmax-source-metadata-bytes = {max_bytes}\n"
        )
    return toml


def run_cli(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Run ``loom *argv*`` in-process; it must exit 0."""
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert __main__.main() == 0


# A runner takes (tmp_path, monkeypatch, config toml, method override,
# max-bytes override) and, keyword-only, whether to run offline. ``None``
# overrides mean "flag not given". A surface with no such per-run override
# raises pytest.skip. Every runner takes the same arguments; not each
# surface needs all of them.
Runner = Callable[..., None]


def _explicit_config(tmp: Path, toml: str) -> PitloomConfig:
    """The demo project's config, named explicitly (``--config``)."""
    return load_config_file(demo_project(tmp, toml) / "pyproject.toml")


def _lib_project(
    tmp: Path,
    _mp: pytest.MonkeyPatch,
    toml: str,
    method: str | None,
    size: int | None,
    *,
    offline: bool = True,
) -> None:
    generate_project_sbom(
        demo_project(tmp, toml),
        content_type_method=method,
        provenance=ProvenanceConfig(max_source_metadata_bytes=size)
        if size is not None
        else None,
        offline=offline,
    )


def _lib_embed(
    tmp: Path,
    _mp: pytest.MonkeyPatch,
    toml: str,
    method: str | None,
    size: int | None,
    *,
    offline: bool = True,
) -> None:
    embed_wheel_sbom(
        demo_wheel(tmp),
        project_dir=demo_project(tmp, toml),
        overrides=ConfigOverrides(
            content_type_method=method,
            provenance=(
                ProvenanceConfig(max_source_metadata_bytes=size)
                if size is not None
                else None
            ),
            offline=offline,
        ),
    )


def _lib_wheel(
    tmp: Path,
    _mp: pytest.MonkeyPatch,
    toml: str,
    method: str | None,
    size: int | None,
    *,
    offline: bool = True,
) -> None:
    # A wheel has no config of its own: the project's is named explicitly,
    # as --config would, and the cap goes through the field-level override.
    wheel = demo_wheel(tmp)
    generate_wheel_sbom(
        wheel,
        content_type_method=method,
        max_source_metadata_bytes=size,
        offline=offline,
        pitloom_config=_explicit_config(tmp, toml),
    )


def _lib_env(
    tmp: Path,
    mp: pytest.MonkeyPatch,
    toml: str,
    method: str | None,
    size: int | None,
    *,
    offline: bool = True,
) -> None:
    config = _explicit_config(tmp, toml)
    # read_environment() shells out to pipdeptree; this stands in for it so
    # the run depends on the same single declared dependency as every other
    # surface here, not on whatever happens to be installed.
    tree = [
        {
            "package": {
                "key": DEPENDENCY,
                "package_name": DEPENDENCY,
                "installed_version": "1.0",
            }
        }
    ]
    mp.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            args=["pipdeptree"], returncode=0, stdout=json.dumps(tree), stderr=""
        ),
    )
    generate_env_sbom(
        content_type_method=method,
        max_source_metadata_bytes=size,
        offline=offline,
        pitloom_config=config,
    )


def cli_embed(
    tmp: Path,
    mp: pytest.MonkeyPatch,
    toml: str,
    method: str | None,
    size: int | None,
    *,
    offline: bool = True,
) -> None:
    argv = [
        "embed-wheel",
        str(demo_wheel(tmp)),
        "--project-dir",
        str(demo_project(tmp, toml)),
    ]
    argv.append("--offline" if offline else "--no-offline")
    if method is not None:
        argv += ["--content-type-method", method]
    if size is not None:
        argv += ["--max-source-metadata-bytes", str(size)]
    run_cli(argv, mp)


def hatch_hook(
    tmp: Path,
    _mp: pytest.MonkeyPatch,
    toml: str,
    method: str | None,
    size: int | None,
    *,
    offline: bool = True,
) -> None:
    if method is not None or size is not None:
        pytest.skip("the Hatchling hook has no per-run override")
    # Its only input is the config file.
    toml += f"\n[tool.pitloom]\noffline = {str(offline).lower()}\n"
    hook = make_hook(str(demo_project(tmp, toml)), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    hook.finalize("standard", build_data, "")


RUNNERS: dict[str, Runner] = {
    "lib-generate_project_sbom": _lib_project,
    "lib-generate_wheel_sbom": _lib_wheel,
    "lib-generate_env_sbom": _lib_env,
    "lib-embed_wheel_sbom": _lib_embed,
    "cli-embed-wheel": cli_embed,
    "hatch-hook": hatch_hook,
}
