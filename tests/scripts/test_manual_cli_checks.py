# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Keeps ``scripts/manual_cli_checks`` runnable, and its CLI matrix
complete: a new subcommand or option the matrix plan does not classify
fails here, in every CI run, not only when someone runs the checks.
"""

import subprocess
import sys
from pathlib import Path

from tests.build_and_read_shared import pitloom_subprocess_env


def _run(scripts_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = pitloom_subprocess_env()
    env.pop("PITLOOM_DEBUG", None)
    return subprocess.run(  # nosec B603
        [sys.executable, str(scripts_dir / "manual_cli_checks"), *args],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def test_lists_unique_check_ids(scripts_dir: Path) -> None:
    result = _run(scripts_dir, "--list")
    assert result.returncode == 0, result.stderr
    ids = [line.split()[0] for line in result.stdout.splitlines()]
    assert len(ids) == len(set(ids)), "duplicate check ids"
    # Non-vacuous: every kind of check is registered.
    for expected in (
        "1",
        "B1",
        "S1",
        "M/completeness",
        "M/project/debug/--debug+PITLOOM_DEBUG=0",
    ):
        assert expected in ids


def test_matrix_plan_covers_the_cli_and_fast_checks_pass(scripts_dir: Path) -> None:
    result = _run(
        scripts_dir, "--only", "M/completeness,1,B7,M/project/debug/*", "-j", "4", "-v"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS  M/completeness" in result.stdout
    assert " 0 fail" in result.stdout.splitlines()[-1]
