# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Guards for files that a runner's bash and YAML parser read verbatim."""

from pathlib import Path

import pytest


def _bash_read_files(scripts_dir: Path) -> list[Path]:
    return [
        *sorted((scripts_dir / "action").glob("*.sh")),
        scripts_dir.parent / "action.yml",
    ]


def test_there_are_files_to_check(scripts_dir: Path) -> None:
    assert len(_bash_read_files(scripts_dir)) >= 3


def test_no_bom_and_no_cr(scripts_dir: Path) -> None:
    """A CR breaks a sourced script; ``.gitattributes`` keeps checkouts LF."""
    for path in _bash_read_files(scripts_dir):
        data = path.read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf"), path.name
        assert b"\r" not in data, path.name


def test_scripts_are_ascii(scripts_dir: Path) -> None:
    """Runner shells and logs handle ASCII identically on every OS."""
    for path in _bash_read_files(scripts_dir):
        try:
            path.read_bytes().decode("ascii")
        except UnicodeDecodeError as error:
            pytest.fail(f"{path.name}: {error}")
