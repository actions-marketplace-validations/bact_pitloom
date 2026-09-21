# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which project-or-sdist target kinds get a build-flag ``WARNING:``, and
which get none: an sdist archive is warned about with its own reason, a
directory settles normally, and anything else (a missing path, a file
that is no sdist) settles nothing -- the read's ``ERROR:`` then stands
alone, identically on the CLI and the library API.

See also: :mod:`tests.test_build_flag_warnings` for the cross-surface
flag matrix, :mod:`tests.test_build_flag_warning_ordering` for the order
of a warning against metadata warnings, and
:mod:`tests.core.test_build_options` for
:meth:`~pitloom.core.build_options.BuildOptions.settle_target`'s unit
tests.
"""

from __future__ import annotations

import logging
import sys
import tarfile
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.core.build_options import BuildOptions
from pitloom.embed import ConfigOverrides, embed_wheel_sbom
from tests.assemble.conftest import _make_dummy_wheel

_BUILD_WARNING = "--build-timeout has no effect"
_SDIST_REASON = "for an sdist archive target"


def _make_sdist_with_malformed_pyproject(tmp_path: Path) -> Path:
    """An sdist whose member ``pyproject.toml`` is malformed, so reading its
    config fails -- the ``ERROR:`` a build-flag warning must precede."""
    root = tmp_path / "src" / "demo-1.0.0"
    root.mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project\nname =\n", encoding="utf-8")
    sdist_path = tmp_path / "demo-1.0.0.tar.gz"
    with tarfile.open(sdist_path, "w:gz") as tar:
        tar.add(root, arcname="demo-1.0.0")
    return sdist_path


def _embed_wheel_argv(wheel: Path, project_dir: Path) -> list[str]:
    return [
        "loom",
        "embed-wheel",
        str(wheel),
        "--project-dir",
        str(project_dir),
        "--build-timeout",
        "5",
    ]


def test_cli_embed_wheel_sdist_project_dir_warns_before_the_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--project-dir <sdist>``: the sdist-reason warning is settled from
    the arguments alone, so it precedes every warning the read produces."""
    sdist = _make_sdist_with_malformed_pyproject(tmp_path)
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
    monkeypatch.setattr(sys, "argv", _embed_wheel_argv(wheel, sdist))

    __main__.main()

    stderr = capsys.readouterr().err.splitlines()
    build = [i for i, line in enumerate(stderr) if _BUILD_WARNING in line]
    assert len(build) == 1, stderr
    assert _SDIST_REASON in stderr[build[0]]
    # Non-vacuous: the read's own error is there, and comes after.
    read_errors = [i for i, line in enumerate(stderr) if "tar.gz:pyproject" in line]
    assert read_errors, stderr
    assert all(stderr[i].startswith("ERROR:") for i in read_errors), stderr
    assert all(i > build[0] for i in read_errors), stderr


@pytest.mark.parametrize("kind", ["missing", "plain_file"])
def test_cli_embed_wheel_non_project_target_warns_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    kind: str,
) -> None:
    """A missing path, and a file that is no sdist archive, settle nothing:
    the command fails with its ``ERROR:`` alone, with no build-flag
    warning claiming a target kind it never had."""
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
    target = tmp_path / "nope"
    if kind == "plain_file":
        target.write_text("not an sdist\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", _embed_wheel_argv(wheel, target))

    assert __main__.main() == 1

    stderr = capsys.readouterr().err
    assert _BUILD_WARNING not in stderr, stderr
    assert "ERROR: " in stderr


@pytest.mark.parametrize("command", ["project", "generate"])
def test_cli_directory_without_project_config_warns_before_the_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    """A directory is a project target whatever it holds, so a stray flag
    is reported there even when the run then fails for want of a
    ``pyproject.toml`` -- and by every command alike: ``project`` settling
    only after its own path check would make it the one surface that
    drops the flag silently."""
    target = tmp_path / "nonproj"
    target.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            command,
            str(target),
            "--build-timeout",
            "5",
            "-o",
            str(tmp_path / "o.json"),
        ],
    )

    assert __main__.main() == 1

    stderr = capsys.readouterr().err.splitlines()
    warnings = [i for i, line in enumerate(stderr) if _BUILD_WARNING in line]
    errors = [i for i, line in enumerate(stderr) if line.startswith("ERROR: ")]
    assert len(warnings) == 1, stderr
    assert errors and warnings[0] < errors[0], stderr


@pytest.mark.parametrize("kind", ["missing", "plain_file"])
def test_library_embed_wheel_sbom_missing_project_dir_warns_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, kind: str
) -> None:
    """Library parity with the CLI's
    ``test_cli_embed_wheel_non_project_target_warns_nothing`` above: a
    missing path, and a file that is no sdist archive, both raise
    ``FileNotFoundError`` as the only report, with no build-flag warning
    ahead of it -- ``target_settle_plan()`` must not settle a plain file
    as if it were an sdist archive."""
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
    target = tmp_path / "nope"
    if kind == "plain_file":
        target.write_text("not an sdist\n", encoding="utf-8")
    overrides = ConfigOverrides(build_options=BuildOptions(timeout=900))

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with pytest.raises(FileNotFoundError):
            embed_wheel_sbom(wheel, project_dir=target, overrides=overrides)

    assert [
        r.getMessage() for r in caplog.records if _BUILD_WARNING in r.getMessage()
    ] == []
