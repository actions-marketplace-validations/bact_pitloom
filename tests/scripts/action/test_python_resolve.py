# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``scripts/action/python-resolve.sh`` against stub interpreters."""

from pathlib import Path
from typing import Any

import pytest

WORKING = 'case "$1" in -c) exit 0 ;; esac\n'
BROKEN = "exit 1\n"


@pytest.fixture(name="source")
def source_fixture(stub_bin: Any, scripts_dir: Path) -> Any:
    """Return ``source(snippet, **env)``: run bash code after sourcing the script."""
    script = scripts_dir / "action" / "python-resolve.sh"

    def run(snippet: str, **env: str) -> Any:
        return stub_bin.run(
            ["-c", f'set -eu -o pipefail; . "{script}"; {snippet}'], **env
        )

    return run


@pytest.mark.parametrize(
    ("stubs", "expected"),
    [
        ({"python": WORKING, "python3": WORKING}, "python"),
        ({"python3": WORKING}, "python3"),
        ({"python": WORKING}, "python"),
        ({"python": BROKEN, "python3": WORKING}, "python3"),
        ({"python": BROKEN, "python3": BROKEN}, ""),
        ({}, ""),
    ],
    ids=[
        "prefers-python",
        "python3-only",
        "python-only",
        "skips-broken",
        "all-broken",
        "none",
    ],
)
def test_python_bin_resolution(
    stub_bin: Any, source: Any, stubs: dict[str, str], expected: str
) -> None:
    for name, body in stubs.items():
        stub_bin.add(name, body)
    result = source('echo "[${python_bin}]"')
    assert result.returncode == 0
    assert result.stdout.strip() == f"[{expected}]"


def test_require_python_fails_with_an_annotation_when_none(source: Any) -> None:
    result = source("require_python; echo unreachable")
    assert result.returncode == 1
    assert "::error::" in result.stdout
    assert "unreachable" not in result.stdout


def test_require_python_passes_when_found(stub_bin: Any, source: Any) -> None:
    stub_bin.add("python", WORKING)
    result = source("require_python; echo reached")
    assert result.returncode == 0
    assert "reached" in result.stdout


def test_python_text_drops_cr_and_forces_utf8(stub_bin: Any, source: Any) -> None:
    stub_bin.add(
        "python",
        WORKING + "printf 'a\\r\\n'; printf 'enc=%s\\r\\n' \"$PYTHONIOENCODING\"\n",
    )
    result = source("python_text script.py")
    assert result.returncode == 0
    assert result.stdout == "a\nenc=utf-8\n"


@pytest.mark.parametrize("pipefail", ["-o", "+o"])
def test_python_text_keeps_the_python_exit_status(
    stub_bin: Any, source: Any, pipefail: str
) -> None:
    """Independent of the caller's ``pipefail`` setting."""
    stub_bin.add("python", WORKING + "printf 'partial\\n'; exit 3\n")
    result = source(f"set {pipefail} pipefail; python_text script.py || echo rc=$?")
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["partial", "rc=3"]


def test_python_text_prints_nothing_for_empty_output(
    stub_bin: Any, source: Any
) -> None:
    stub_bin.add("python", WORKING)
    result = source("python_text script.py")
    assert result.returncode == 0
    assert result.stdout == ""


def test_python_text_without_python_fails(source: Any) -> None:
    result = source("python_text script.py")
    assert result.returncode == 127
    assert result.stdout == ""
    assert result.stderr != ""
