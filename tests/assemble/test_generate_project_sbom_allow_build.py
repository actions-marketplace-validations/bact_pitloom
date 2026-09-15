# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests that ``allow_build``/``no_build_isolation`` reach
``get_wheel_files()`` from every library-API entry point that accepts
them (:func:`pitloom.assemble.generate_project_sbom`,
:func:`pitloom.assemble.generate`) -- the library-API counterpart of the
CLI-level checks in ``tests/cli/test_cli_parser.py``. Both parameters are
plain ``bool = False`` (no ``[tool.pitloom]`` cascade), so there is no
config-precedence case to test here, unlike ``use_lockfile``'s sibling
test module.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest import mock

import pytest

from pitloom.assemble import generate, generate_project_sbom
from pitloom.core.project import ProjectFile
from tests.cli.shared import _make_simple_project


def test_generate_project_sbom_threads_allow_build(tmp_path: Path) -> None:
    project_dir = _make_simple_project(tmp_path)

    with mock.patch(
        "pitloom.assemble._generators.get_wheel_files",
        return_value=(None, [], lambda: None),
    ) as mocked:
        generate_project_sbom(
            project_dir, offline=True, allow_build=True, no_build_isolation=True
        )

    assert mocked.call_args.kwargs["allow_build"] is True
    assert mocked.call_args.kwargs["no_build_isolation"] is True


def test_generate_project_sbom_defers_cleanup_past_ai_model_scan(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: ``get_wheel_files()``'s cleanup callback (a real
    filesystem removal only for a build-and-read result, see
    ``_models_wheel_build_and_read.py``) must not run before
    ``scan_project_for_ai_models()`` re-reads each returned
    ``ProjectFile``'s bytes from ``physical_path`` -- calling it too
    early turns every ``.py`` file into a spurious "could not read for
    usage scanning" WARNING instead of a clean scan. Caught by manually
    running ``--allow-build`` against a real vendored ``uv_build``
    fixture, where every one of its ~90 Python files logged this
    warning. Simulates a build-and-read-sourced file here (a real file
    physically outside *project_dir*, deleted by ``cleanup``) without
    needing a real PEP 517 build."""
    project_dir = _make_simple_project(tmp_path)
    fake_extract_dir = tmp_path / "fake-extract"
    fake_extract_dir.mkdir()
    py_file = fake_extract_dir / "mod.py"
    py_file.write_text("x = 1\n", encoding="utf-8")

    project_file = ProjectFile(
        physical_path=str(py_file),
        distribution_path="demo/mod.py",
        digest_sha256="e" * 64,
    )
    cleanup_calls: list[str] = []

    def _cleanup() -> None:
        cleanup_calls.append("cleanup")
        py_file.unlink()

    with mock.patch(
        "pitloom.assemble._generators.get_wheel_files",
        return_value=(None, [project_file], _cleanup),
    ):
        with caplog.at_level(logging.WARNING):
            generate_project_sbom(project_dir, offline=True, allow_build=True)

    assert cleanup_calls == ["cleanup"]
    assert "could not read for usage scanning" not in caplog.text


def test_generate_project_sbom_defaults_allow_build_false(tmp_path: Path) -> None:
    project_dir = _make_simple_project(tmp_path)

    with mock.patch(
        "pitloom.assemble._generators.get_wheel_files",
        return_value=(None, [], lambda: None),
    ) as mocked:
        generate_project_sbom(project_dir, offline=True)

    assert mocked.call_args.kwargs["allow_build"] is False
    assert mocked.call_args.kwargs["no_build_isolation"] is False


def test_generate_dispatches_allow_build_to_project_sbom(tmp_path: Path) -> None:
    """``generate()``'s own "project" classification branch (a plain
    directory target, not env/wheel/model/HF) must forward both flags
    unchanged to :func:`generate_project_sbom`."""
    project_dir = _make_simple_project(tmp_path)

    with mock.patch(
        "pitloom.assemble.generate_project_sbom", return_value="{}"
    ) as mocked:
        generate(project_dir, offline=True, allow_build=True, no_build_isolation=True)

    assert mocked.call_args.kwargs["allow_build"] is True
    assert mocked.call_args.kwargs["no_build_isolation"] is True
