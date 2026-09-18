# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``scripts/action/pitloom-install.sh`` against a stub ``python``.

No network and no real pip: the stub records the ``pip install`` spec and
answers the version query, so only the script's own decisions are tested.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

# Stub env: STUB_LOG (file recording pip calls), STUB_PIP_EXIT,
# STUB_VERSION, STUB_VERSION_EXIT, STUB_CRLF (end version line with CRLF).
PYTHON_STUB = """\
case "$1" in
  -c) exit 0 ;;
  -m) echo "$*" >> "${STUB_LOG}"; exit "${STUB_PIP_EXIT:-0}" ;;
  *check_version_consistency.py)
    [ "${STUB_VERSION_EXIT:-0}" = 0 ] || exit 1
    if [ -n "${STUB_CRLF:-}" ]; then
      printf '%s\\r\\n' "${STUB_VERSION-1.2.3}"
    else
      echo "${STUB_VERSION-1.2.3}"
    fi ;;
esac
"""


class _Run(NamedTuple):
    returncode: int
    stdout: str
    pip_calls: list[str]


@pytest.fixture(name="run_install")
def run_install_fixture(
    stub_bin: Any, tmp_path: Path, scripts_dir: Path
) -> Callable[..., _Run]:
    """Return ``run(extras, version, *, with_loom, with_python, **stub_env)``."""
    log = tmp_path / "pip.log"
    script = scripts_dir / "action" / "pitloom-install.sh"

    def run(
        extras: str,
        version: str,
        *,
        with_loom: bool = True,
        with_python: bool = True,
        **stub_env: str,
    ) -> _Run:
        stub_bin.remove("python")
        stub_bin.remove("loom")
        if with_python:
            stub_bin.add("python", PYTHON_STUB)
        if with_loom:
            stub_bin.add("loom", "")
        result = stub_bin.run(
            [str(script)],
            PL_EXTRAS=extras,
            PL_VERSION=version,
            STUB_LOG=str(log),
            **stub_env,
        )
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        log.unlink(missing_ok=True)
        return _Run(result.returncode, result.stdout + result.stderr, calls)

    return run


def test_empty_version_installs_the_checkout_version(
    run_install: Callable[..., _Run],
) -> None:
    result = run_install("", "", STUB_VERSION="4.5.6")
    assert result.returncode == 0
    assert result.pip_calls == ["-m pip install pitloom==4.5.6"]
    assert "::notice::" in result.stdout
    assert "4.5.6" in result.stdout


def test_windows_crlf_in_derived_version_is_stripped(
    run_install: Callable[..., _Run],
) -> None:
    result = run_install("", "", STUB_VERSION="4.5.6", STUB_CRLF="1")
    assert result.returncode == 0
    assert result.pip_calls == ["-m pip install pitloom==4.5.6"]
    assert "\r" not in result.stdout


def test_empty_version_with_extras(run_install: Callable[..., _Run]) -> None:
    result = run_install("ai,content-type", "")
    assert result.pip_calls == ["-m pip install pitloom[ai,content-type]==1.2.3"]


@pytest.mark.parametrize(
    ("version", "spec"),
    [
        ("0.18.1", "pitloom==0.18.1"),
        (">=0.18,<1.0", "pitloom>=0.18,<1.0"),
        ("~=0.18", "pitloom~=0.18"),
        ("!=0.18.0", "pitloom!=0.18.0"),
    ],
)
def test_explicit_version_wins_over_the_checkout_version(
    run_install: Callable[..., _Run], version: str, spec: str
) -> None:
    result = run_install("", version, STUB_VERSION="4.5.6")
    assert result.returncode == 0
    assert result.pip_calls == [f"-m pip install {spec}"]
    assert "4.5.6" not in result.stdout
    assert "::notice::" not in result.stdout


def test_unreleased_checkout_version_fails_with_a_hint(
    run_install: Callable[..., _Run],
) -> None:
    result = run_install("", "", STUB_VERSION="9.9.9", STUB_PIP_EXIT="1")
    assert result.returncode == 1
    assert "::error::" in result.stdout
    assert "9.9.9" in result.stdout
    assert "pitloom-version" in result.stdout


def test_explicit_version_pip_failure_adds_no_pin_hint(
    run_install: Callable[..., _Run],
) -> None:
    result = run_install("", "0.18.1", STUB_PIP_EXIT="1")
    assert result.returncode == 1
    assert "::error::" not in result.stdout


def test_unreadable_checkout_version_fails_before_pip(
    run_install: Callable[..., _Run],
) -> None:
    result = run_install("", "", STUB_VERSION_EXIT="1")
    assert result.returncode == 1
    assert "::error::" in result.stdout
    assert "pitloom-version" in result.stdout
    assert result.pip_calls == []


def test_empty_checkout_version_fails_before_pip(
    run_install: Callable[..., _Run],
) -> None:
    result = run_install("", "", STUB_VERSION="")
    assert result.returncode == 1
    assert result.pip_calls == []


def test_missing_loom_after_install_fails(run_install: Callable[..., _Run]) -> None:
    result = run_install("", "", with_loom=False)
    assert result.returncode == 1
    assert "::error::" in result.stdout
    assert result.pip_calls == ["-m pip install pitloom==1.2.3"]


def test_no_python_fails(run_install: Callable[..., _Run]) -> None:
    result = run_install("", "", with_python=False)
    assert result.returncode == 1
    assert "::error::" in result.stdout
    assert result.pip_calls == []
