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

    Holds only the stubs added to it plus the host programs linked in, so the
    host's real ``python`` never leaks in.
    """

    def __init__(self, directory: Path, bash: str) -> None:
        self.directory = directory
        self.bash = bash
        self.cwd: Path | None = None  # working directory of run()
        directory.mkdir()

    def link(self, *names: str) -> None:
        """Expose host programs (``tee``, ``sed``, ...) under their names."""
        for name in names:
            found = shutil.which(name)
            if found is None:
                pytest.skip(f"{name} not found")
            (self.directory / name).symlink_to(found)

    def add(self, name: str, body: str) -> None:
        """Add an executable bash stub called ``name``."""
        stub = self.directory / name
        stub.write_text(f"#!{self.bash}\n{body}", encoding="utf-8")
        stub.chmod(0o755)

    def run(self, args: list[str], **env: str) -> "subprocess.CompletedProcess[str]":
        """Run ``bash <args>`` with ``PATH`` limited to this directory.

        Output is decoded without newline translation, so a stray CR stays
        visible to assertions.
        """
        result = subprocess.run(
            [self.bash, *args],
            cwd=self.cwd,
            env={"PATH": str(self.directory), **env},
            capture_output=True,
            check=False,
        )
        return subprocess.CompletedProcess(
            result.args,
            result.returncode,
            result.stdout.decode("utf-8"),
            result.stderr.decode("utf-8"),
        )


@pytest.fixture(name="stub_bin")
def stub_bin_fixture(tmp_path: Path) -> StubBin:
    if sys.platform == "win32" or BASH is None:
        pytest.skip("needs POSIX bash and executable stubs")
    stub_bin = StubBin(tmp_path / "bin", BASH)
    stub_bin.link("dirname")
    return stub_bin
