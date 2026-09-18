# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Fixtures for testing the action's shell helpers against stub programs."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BASH = shutil.which("bash")


class StubBin:
    """A directory used as the entire ``PATH`` of a bash subprocess.

    Holds only the stubs added to it plus ``dirname``, so the host's real
    ``python`` never leaks in.
    """

    def __init__(self, directory: Path, bash: str) -> None:
        self.directory = directory
        self.bash = bash
        directory.mkdir()
        dirname = shutil.which("dirname")
        if dirname is None:
            raise RuntimeError("dirname not found")
        (directory / "dirname").symlink_to(dirname)

    def add(self, name: str, body: str) -> None:
        """Add an executable bash stub called ``name``."""
        stub = self.directory / name
        stub.write_text(f"#!{self.bash}\n{body}", encoding="utf-8")
        stub.chmod(0o755)

    def run(self, args: list[str], **env: str) -> "subprocess.CompletedProcess[str]":
        """Run ``bash <args>`` with ``PATH`` limited to this directory."""
        return subprocess.run(
            [self.bash, *args],
            env={"PATH": str(self.directory), **env},
            capture_output=True,
            text=True,
            check=False,
        )


@pytest.fixture(name="stub_bin")
def stub_bin_fixture(tmp_path: Path) -> StubBin:
    if sys.platform == "win32" or BASH is None:
        pytest.skip("needs POSIX bash and executable stubs")
    return StubBin(tmp_path / "bin", BASH)
