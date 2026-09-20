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
    """An sdist whose member ``pyproject.toml`` is malformed, so reading it
    warns -- the warning a build-flag warning must precede."""
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
    # Non-vacuous: the read's own warning is there, and comes after.
    read_warnings = [i for i, line in enumerate(stderr) if "sdist member" in line]
    assert read_warnings, stderr
    assert all(i > build[0] for i in read_warnings), stderr


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


def test_library_embed_wheel_sbom_missing_project_dir_warns_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Library parity with the CLI above: the raised ``FileNotFoundError``
    is the only report, with no build-flag warning ahead of it."""
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
    overrides = ConfigOverrides(build_options=BuildOptions(timeout=900))

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with pytest.raises(FileNotFoundError):
            embed_wheel_sbom(wheel, project_dir=tmp_path / "nope", overrides=overrides)

    assert [
        r.getMessage() for r in caplog.records if _BUILD_WARNING in r.getMessage()
    ] == []
