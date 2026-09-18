# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``scripts/check_version_consistency.py``."""

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from pitloom.__about__ import __version__

SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "check_version_consistency.py"
)


@pytest.fixture(name="module")
def module_fixture(load_script: Callable[[str], ModuleType]) -> ModuleType:
    return load_script("check_version_consistency")


def test_print_version_matches_about_module() -> None:
    """The action learns its Pitloom version from this exact output."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--print-version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == __version__


def test_read_about_version_reads_given_path(
    module: ModuleType, tmp_path: Path
) -> None:
    about = tmp_path / "__about__.py"
    about.write_text('"""Doc."""\n__version__ = "9.8.7"\n', encoding="utf-8")
    assert module.read_about_version(about) == "9.8.7"


@pytest.mark.parametrize(
    "content",
    [
        '\ufeff"""Doc."""\n__version__ = "9.8.7"\n',
        '"""Doc."""\r\n__version__ = "9.8.7"\r\n',
        '\ufeff__version__ = "9.8.7"\r\n',
    ],
    ids=["bom", "crlf", "bom-first-line-crlf"],
)
def test_read_about_version_tolerates_bom_and_crlf(
    module: ModuleType, tmp_path: Path, content: str
) -> None:
    about = tmp_path / "__about__.py"
    about.write_bytes(content.encode("utf-8"))
    assert module.read_about_version(about) == "9.8.7"


@pytest.mark.parametrize(
    "content",
    ["", "version = '1.0'\n", "__version__ = 1.0\n", "  __version__ = '1.0'\n"],
    ids=["empty", "wrong-name", "unquoted", "indented-single-quoted"],
)
def test_read_about_version_rejects_unparseable(
    module: ModuleType, tmp_path: Path, content: str
) -> None:
    about = tmp_path / "__about__.py"
    about.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        module.read_about_version(about)


def test_main_print_version_prints_and_returns_zero(
    module: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert module.main(["--print-version"]) == 0
    assert capsys.readouterr().out.strip() == __version__
