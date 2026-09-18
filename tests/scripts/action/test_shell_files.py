# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Guards for files that a runner's bash and YAML parser read verbatim."""

from pathlib import Path

import pytest


def _bash_read_files() -> list[Path]:
    repo = Path(__file__).resolve().parents[3]
    return [*sorted((repo / "scripts" / "action").glob("*.sh")), repo / "action.yml"]


@pytest.mark.parametrize("path", _bash_read_files(), ids=lambda path: path.name)
def test_plain_ascii_with_lf_endings(path: Path) -> None:
    """A CR or BOM breaks a sourced script; ``.gitattributes`` keeps LF."""
    data = path.read_bytes()
    assert b"\r" not in data
    assert data.isascii()


def test_the_shell_scripts_are_found() -> None:
    names = {path.name for path in _bash_read_files()}
    assert {"pitloom-install.sh", "python-resolve.sh", "action.yml"} <= names
