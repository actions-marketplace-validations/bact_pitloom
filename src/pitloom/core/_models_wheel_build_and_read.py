# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generic, backend-agnostic PEP 517 build-and-read file discovery.

Actually invokes whatever build hooks the target project's own
``pyproject.toml`` declares to produce a real wheel, then reads that
wheel's own file list -- for a backend with no static-config discovery
module of its own (e.g. ``uv_build``, a thin PEP 517 shim with no
in-process introspection API), or as a fallback when a backend that
*does* have one fails to resolve on a given project. This mechanism
never needs to know a backend's name -- it just runs the project's
declared PEP 517 hooks via :mod:`build`, whatever they are -- see
:mod:`pitloom.core._models_wheel`'s ``_try_build_and_read``, the sole
caller.

Gated everywhere it's called from behind ``--allow-build``: this is the
first mechanism in Pitloom that executes third-party build-time code.
Every other backend discovery module deliberately avoids this (Flit's
AST-only version scan, PDM's ``WheelBuilder``/``Context``-not-``.build()``
avoidance).

See also: ``working-docs/design/non-hatchling-file-discovery.md``
(Track A/B split, "build-and-read" as roadmap item #4).
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path

from pitloom.core._models_wheel_types import (
    IncludedFile,
    is_dist_info_path,
    to_posix_distribution_path,
)

log = logging.getLogger(__name__)


def _run_pep517_build_wheel(
    project_dir: Path, output_dir: Path, *, isolated: bool
) -> Path:
    """Build a real wheel for *project_dir* into *output_dir* via PyPA
    ``build``, returning the built wheel's path.

    *isolated* mirrors ``python -m build``'s own default: a fresh temp
    virtualenv is created and the project's declared
    ``[build-system] requires`` (plus any ``get_requires_for_build``
    additions) are installed into it -- this is where a network fetch
    happens, reusing pip's normal cache. ``isolated=False`` (from
    ``--no-build-isolation``) skips all of that and calls the currently
    running Python's own importable build backend directly -- faster, no
    network, but only correct if the caller's environment genuinely
    already has it installed.

    Never catches an exception itself -- the caller
    (:func:`build_and_read_wheel`) wraps this in one broad
    ``except Exception`` alongside every other step, matching every
    other backend module's single blanket-except-and-warn contract.
    """
    # pylint: disable-next=import-outside-toplevel
    from build import ProjectBuilder

    if isolated:
        # pylint: disable-next=import-outside-toplevel
        from build.env import DefaultIsolatedEnv

        with DefaultIsolatedEnv() as env:
            builder = ProjectBuilder.from_isolated_env(env, project_dir)
            env.install(builder.build_system_requires)
            env.install(builder.get_requires_for_build("wheel"))
            wheel_filename = builder.build("wheel", str(output_dir))
    else:
        builder = ProjectBuilder(project_dir)
        wheel_filename = builder.build("wheel", str(output_dir))
    return output_dir / wheel_filename


def _extract_wheel_to_included_files(
    wheel_path: Path, extract_dir: Path
) -> list[IncludedFile]:
    """Extract *wheel_path*'s real, non-``.dist-info`` entries into
    *extract_dir*, returning ordinary :class:`IncludedFile` pairs -- the
    same shape every static discoverer already produces, so the shared
    per-file loop in :mod:`pitloom.core._models_wheel` (hashing,
    header/content-type scanning) needs no special-casing for this
    mechanism.

    ``.dist-info/*`` is excluded even though it's genuinely present in
    this real, already-built wheel -- every other backend's
    ``IncludedFile`` list represents pre-build *source* files only, and
    ``.dist-info`` is a build-generated artifact with no source-stage
    equivalent (see CLAUDE.md's "stage-scoped helpers" principle);
    including it here would make this mechanism's Source-SBOM file list
    diverge in kind from every other backend's for no benefit --
    ``embed-wheel``'s own ``_merge_file_extras`` already gets
    ``.dist-info`` entries from ``read_wheel()`` directly, so nothing is
    lost.

    A wheel's own internal entries are always ``/``-separated per the ZIP
    spec (so ``to_posix_distribution_path()`` is a safety net here, not a
    live bug on any platform), but ``target`` (a real, on-disk path) is
    composed via :class:`~pathlib.Path`'s own ``/`` operator, which
    accepts a ``/``-separated string as multiple path components on
    every platform including Windows -- never raw string concatenation.

    Zip-slip guard: unlike every static discoverer (which only ever
    walks real files already inside *project_dir*), this one writes
    bytes to disk from a zip archive a real, external build process
    just produced -- a ``../``-containing or absolute entry name (from
    a buggy or malicious build backend) must never be allowed to
    resolve outside *extract_dir* and overwrite an unrelated file
    elsewhere on the filesystem.
    """
    resolved_extract_dir = extract_dir.resolve()
    files: list[IncludedFile] = []
    with zipfile.ZipFile(wheel_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            distribution_path = to_posix_distribution_path(info.filename)
            if is_dist_info_path(distribution_path):
                continue
            target = extract_dir / distribution_path
            if not target.resolve().is_relative_to(resolved_extract_dir):
                log.warning(
                    "Build: %s: wheel entry %r resolves outside the "
                    "extraction directory -- skipped, not written to disk",
                    wheel_path,
                    distribution_path,
                )
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            files.append(
                IncludedFile(path=str(target), distribution_path=distribution_path)
            )
    return files


def build_and_read_wheel(
    project_dir: Path, *, isolated: bool = True
) -> tuple[list[IncludedFile], Callable[[], None]] | None:
    """Build a real wheel for *project_dir* and return its file list as
    ordinary, on-disk :class:`IncludedFile` entries, plus a cleanup
    callback the caller MUST invoke once done consuming them (deletes the
    temp extraction directory backing ``.path``).

    Returns ``None`` on any failure (backend not installable, network
    unavailable under isolation, the build script itself fails, or the
    build produced a wheel with zero non-``.dist-info`` files) -- same
    "``None`` means fall back" contract as every static discoverer,
    logged with a ``WARNING:`` here (the caller's own fallback-to-Hatchling
    warning fires on top of this one, same two-tier pattern
    setuptools'/PDM's/Flit's own failure paths already have).

    Never leaves a temp directory behind on the failure path: the
    build-output tempdir is always a context manager; only the
    *extraction* tempdir survives past this function's return on success
    (its contents are what the returned ``IncludedFile.path`` values
    point at), via the returned cleanup callback.
    """
    extract_dir = Path(tempfile.mkdtemp(prefix="pitloom-build-and-read-"))
    try:
        with tempfile.TemporaryDirectory(prefix="pitloom-build-output-") as build_out:
            wheel_path = _run_pep517_build_wheel(
                project_dir, Path(build_out), isolated=isolated
            )
            files = _extract_wheel_to_included_files(wheel_path, extract_dir)
        if not files:
            log.warning(
                "Build: %s's real build produced a wheel with no "
                "non-.dist-info files -- treating as a discovery "
                "failure, not an authoritative empty result",
                project_dir,
            )
            shutil.rmtree(extract_dir, ignore_errors=True)
            return None
        return files, lambda: shutil.rmtree(extract_dir, ignore_errors=True)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        shutil.rmtree(extract_dir, ignore_errors=True)
        log.warning(
            "Build: build-and-read discovery failed for %s: %s", project_dir, exc
        )
        return None
