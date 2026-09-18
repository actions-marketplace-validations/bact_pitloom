# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``scripts/action/python_probe.py``."""

import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import create_autospec

import pytest


@pytest.fixture(name="probe")
def probe_fixture(load_script: Callable[[str], ModuleType]) -> ModuleType:
    return load_script("action/python_probe")


# pylint: disable-next=too-few-public-methods
class _Setup:
    """A usable interpreter layout under ``tmp_path``."""

    def __init__(self, probe: ModuleType, root: Path) -> None:
        self.stdlib = root / "lib" / "python3.12"
        self.site = self.stdlib / "site-packages"
        self.bin = root / "bin"
        for directory in (self.stdlib, self.site, self.bin):
            directory.mkdir(parents=True)
        self.interpreter = probe.Interpreter(
            version_info=(3, 12, 1),
            has_pip=True,
            prefix=str(root),
            base_prefix=str(root),
            stdlib_dir=str(self.stdlib),
            install_dirs=(str(self.site),),
            scripts_dir=str(self.bin),
        )
        self.path_env = os.pathsep.join([str(root / "other"), str(self.bin)])
        self.environ: Mapping[str, str] = {}

    def mark_externally_managed(self) -> None:
        marker = self.stdlib / "EXTERNALLY-MANAGED"
        marker.write_text("[externally-managed]\n", encoding="utf-8")


@pytest.fixture(name="setup")
def setup_fixture(probe: ModuleType, tmp_path: Path) -> _Setup:
    return _Setup(probe, tmp_path)


def _reason(probe: ModuleType, setup: _Setup, **changes: Any) -> str | None:
    path_env = changes.pop("path_env", setup.path_env)
    environ = changes.pop("environ", setup.environ)
    interpreter = setup.interpreter._replace(**changes)
    reason: str | None = probe.unusable_reason(interpreter, path_env, environ)
    return reason


def test_usable_baseline(probe: ModuleType, setup: _Setup) -> None:
    assert _reason(probe, setup) is None


def test_missing_install_dir_uses_nearest_existing_parent(
    probe: ModuleType, setup: _Setup
) -> None:
    missing = str(setup.site / "not" / "yet" / "created")
    assert _reason(probe, setup, install_dirs=(missing,)) is None


def test_python_below_the_floor_is_rejected(probe: ModuleType, setup: _Setup) -> None:
    assert _reason(probe, setup, version_info=(3, 10, 0)) is None
    reason = _reason(probe, setup, version_info=(3, 9, 99))
    assert reason is not None
    assert "older than 3.10" in reason


def test_missing_pip_is_rejected(probe: ModuleType, setup: _Setup) -> None:
    reason = _reason(probe, setup, has_pip=False)
    assert reason is not None
    assert "pip" in reason


def test_externally_managed_is_rejected(probe: ModuleType, setup: _Setup) -> None:
    setup.mark_externally_managed()
    reason = _reason(probe, setup)
    assert reason is not None
    assert "PEP 668" in reason


def test_externally_managed_is_fine_inside_a_venv(
    probe: ModuleType, setup: _Setup
) -> None:
    setup.mark_externally_managed()
    assert _reason(probe, setup) is not None
    assert _reason(probe, setup, base_prefix="/somewhere/else") is None


@pytest.mark.parametrize(
    ("value", "usable"),
    [("1", True), ("true", True), ("YES", True)]
    + [("", False), ("0", False), ("false", False), ("off", False)],
)
def test_externally_managed_honours_pip_override(
    probe: ModuleType, setup: _Setup, value: str, usable: bool
) -> None:
    setup.mark_externally_managed()
    assert _reason(probe, setup) is not None
    reason = _reason(probe, setup, environ={"PIP_BREAK_SYSTEM_PACKAGES": value})
    assert (reason is None) is usable


@pytest.mark.parametrize("which", ["install", "scripts"])
def test_unwritable_directory_is_rejected(
    probe: ModuleType,
    setup: _Setup,
    monkeypatch: pytest.MonkeyPatch,
    which: str,
) -> None:
    # NTFS has no POSIX permission bits, so fake the access check instead.
    blocked = str(setup.site if which == "install" else setup.bin)
    assert _reason(probe, setup) is None

    def fake_access(path: str, mode: int, **_kwargs: Any) -> bool:
        return not (mode == os.W_OK and os.fspath(path) == blocked)

    monkeypatch.setattr(
        probe.os, "access", create_autospec(os.access, side_effect=fake_access)
    )
    reason = _reason(probe, setup)
    assert reason is not None
    assert "not writable" in reason


def test_scripts_dir_must_be_on_path(probe: ModuleType, setup: _Setup) -> None:
    assert _reason(probe, setup) is None
    reason = _reason(probe, setup, path_env=str(setup.bin.parent / "other"))
    assert reason is not None
    assert "PATH" in reason


def test_scripts_dir_on_path_ignores_empty_entries_and_spelling(
    probe: ModuleType, setup: _Setup
) -> None:
    path_env = os.pathsep.join(["", str(setup.bin / ".." / "bin")])
    assert _reason(probe, setup, path_env=path_env) is None


def test_min_python_matches_requires_python(
    probe: ModuleType, scripts_dir: Path
) -> None:
    """The probe's floor must not drift from what Pitloom itself needs."""
    pyproject = (scripts_dir.parent / "pyproject.toml").read_text(encoding="utf-8-sig")
    match = re.search(r'^requires-python\s*=\s*">=(\d+)\.(\d+)"', pyproject, re.M)
    assert match is not None
    assert probe.MIN_PYTHON == (int(match.group(1)), int(match.group(2)))


def test_script_runs_under_the_current_interpreter(scripts_dir: Path) -> None:
    """Exercises the real ``Interpreter.current()`` gathering end to end."""
    script = scripts_dir / "action" / "python_probe.py"
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, check=False
    )
    assert result.returncode in (0, 1)
    assert (result.returncode == 0) == (result.stdout == "")
    assert result.stderr == ""
