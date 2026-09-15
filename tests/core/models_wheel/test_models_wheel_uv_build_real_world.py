# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Real ``--allow-build`` build-and-read discovery against the two
vendored ``uv_build`` sdist fixtures.

Unlike ``test_models_wheel_real_world.py`` (fast, offline, exercises
every *static* ``discover()`` against a real published wheel's file
list), this test actually invokes PyPA ``build`` -- a real PEP 517
build in an isolated venv, installing ``uv_build`` from the network --
so it's marked ``@pytest.mark.pypi_network`` (opts out of
``tests/conftest.py``'s default socket block) and is slow (creates a
venv, installs build-requires, runs the real ``uv-build`` binary).

Both fixtures were verified empirically (2026-09-15, per the roadmap
plan for this feature) to produce a byte-for-byte exact match against
their real published wheel's non-``.dist-info`` file list -- zero known
gaps for either. If a future ``uv_build`` release for either vendored
version changes its build output, this test's exact-match assertion is
expected to catch that as a failure, not silently mask it via a
``known_gaps`` allowance the way the fast-path fixtures do.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.core._models_wheel import _discover_included_files
from tests.fixtures.real_world import (
    REAL_WORLD_ROOT,
    extract_sdist,
    load_expected,
    sdist_available,
)

UV_BUILD_FIXTURES = [
    project_dir
    for project_dir in sorted((REAL_WORLD_ROOT / "uv_build").iterdir())
    if (project_dir / "expected.json").exists()
]
FIXTURE_IDS = [project_dir.name for project_dir in UV_BUILD_FIXTURES]


def _expected_non_dist_info_paths(manifest: dict[str, object]) -> set[str]:
    """The real wheel's file list minus its own ``.dist-info/*`` entries
    -- build-and-read never reproduces those (see
    ``pitloom.extract._license``'s docstring). Deliberately does not
    consult the manifest's ``known_gaps``/``known_gaps_note`` fields:
    those describe the *static* discovery fast path's fixture-level
    skip, not this real-build path's own (independently verified, see
    module docstring) empty gap set."""
    wheel_files: list[str] = manifest.get("wheel_files") or []  # type: ignore[assignment]
    dist_info_prefix = next(
        (
            f.split(".dist-info/", maxsplit=1)[0] + ".dist-info/"
            for f in wheel_files
            if ".dist-info/" in f
        ),
        None,
    )
    return {
        f
        for f in wheel_files
        if not (dist_info_prefix and f.startswith(dist_info_prefix))
    }


@pytest.mark.pypi_network
@pytest.mark.parametrize("project_dir", UV_BUILD_FIXTURES, ids=FIXTURE_IDS)
def test_build_and_read_matches_real_wheel(project_dir: Path, tmp_path: Path) -> None:
    if not sdist_available(project_dir):
        pytest.skip(
            f"{project_dir.name}: vendored sdist not present (excluded from "
            "Pitloom's own sdist -- run from a full git checkout to "
            "exercise this test)"
        )

    manifest = load_expected(project_dir)
    expected = _expected_non_dist_info_paths(manifest)
    extracted_root = extract_sdist(project_dir, tmp_path)

    included, cleanup = _discover_included_files(
        extracted_root, assume_backend="uv_build", allow_build=True
    )
    try:
        discovered = {f.distribution_path for f in included}
    finally:
        cleanup()

    missing = expected - discovered
    extra = discovered - expected
    assert not missing, f"in real wheel but not discovered: {sorted(missing)}"
    assert not extra, f"discovered but not in real wheel: {sorted(extra)}"
