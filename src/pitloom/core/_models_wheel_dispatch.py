# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Backend dispatch for wheel file discovery.

Resolves *which* discovery path a project's build backend should use --
a registered backend's own static module, the generic
:mod:`pitloom.core._models_wheel_build_and_read` mechanism (gated behind
``--allow-build``), or the Hatchling-based heuristic fallback -- and
returns the resolved files. Split out of :mod:`pitloom.core._models_wheel`
once that file crossed the ~400-500 line soft limit; the shared per-file
hashing/extraction loop stays there, this module owns only the dispatch
decision.

See also: :mod:`pitloom.core._models_wheel`'s ``get_wheel_files()``, the
sole caller of :func:`_discover_included_files` below.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from pitloom.core import _models_wheel_hatchling
from pitloom.core._models_wheel_lock import _DISCOVERY_LOCK
from pitloom.core._models_wheel_types import (
    BackendDiscoverer,
    IncludedFile,
    has_resolvable_pyproject_config,
    has_uv_build_backend_overrides,
)

log = logging.getLogger(__name__)


_WRITER_BACKENDS = frozenset({"setuptools", "pdm"})
"""Backend names whose ``discover()`` process-wide ``os.chdir()``s and must
therefore run under :meth:`~pitloom.core._models_wheel_lock._DiscoveryLock.write`
(see its docstring). Every backend NOT listed here -- Hatchling, Poetry,
Flit, and any future addition to ``backend_discoverers`` -- is assumed to
be a "reader" and dispatches under
:meth:`~pitloom.core._models_wheel_lock._DiscoveryLock.read` instead. Add
a backend here only when its ``discover()`` genuinely needs the working
directory changed; the default for a new backend should be to stay off
this set. PDM-backend joined setuptools here because its own package
auto-discovery (``pdm.backend.base._find_top_packages``) globs relative
to the process cwd, not the ``Builder``'s ``location`` -- see
:mod:`pitloom.core._models_wheel_pdm`."""


def _skip_hatchling_fallback(
    backend: str, pyproject_data: dict[str, object] | None, project_dir: Path
) -> bool:
    """Log the right ``WARNING:`` for a backend discoverer giving up
    (returning ``None``), and report whether the doomed Hatchling
    fallback attempt should be skipped entirely (``True``) or still
    tried (``False``).

    Hatchling's ``WheelBuilder`` requires a ``pyproject.toml``
    ``[project]`` table -- with none present at all, it is guaranteed to
    also fail, so the confusing "Hatchling"-branded error for a project
    that has nothing to do with Hatchling isn't worth it. Distinguishing
    *why* the backend's own discoverer already gave up -- a
    ``[tool.<backend>]`` table present (approximate but the best
    available signal -- every currently-registered backend names its
    config table after itself) means static config existed but
    introspection itself failed, not that nothing was declared at all --
    only changes the warning's wording, not this return value.
    """
    has_project_table = pyproject_data is not None and "project" in pyproject_data
    if has_project_table:
        log.warning(
            "No static %s config resolvable in %s -- falling back to "
            "Hatchling-based heuristic, file list may be inaccurate",
            backend,
            project_dir,
        )
        return False

    if pyproject_data is not None and has_resolvable_pyproject_config(
        pyproject_data, backend
    ):
        log.warning(
            "%s's static config failed introspection in %s -- file "
            "discovery is unsupported for this project this run "
            "(Hatchling's own WheelBuilder also requires a [project] "
            "table, so that fallback would fail too)",
            backend,
            project_dir,
        )
    else:
        log.warning(
            "No static %s config resolvable in %s and no [project] "
            "table present -- file discovery is unsupported for this "
            "project (packages only resolvable via an imperative "
            "setup.py build)",
            backend,
            project_dir,
        )
    return True


def _unhandled_backend_hint(
    backend: str, pyproject_data: dict[str, object] | None
) -> str:
    """The optional, sharpened suffix for the "not backend-aware"
    fallback ``WARNING:`` below -- non-empty only for the one known,
    confirmed divergence risk (see
    :func:`~pitloom.core._models_wheel_types.has_uv_build_backend_overrides`'s
    docstring), never a general "you might want --allow-build" nudge."""
    if (
        backend == "uv_build"
        and pyproject_data is not None
        and has_uv_build_backend_overrides(pyproject_data)
    ):
        return (
            " (this project's pyproject.toml declares "
            "[tool.uv.build-backend] overrides the heuristic cannot see "
            "-- pass --allow-build for an exact file list via a real "
            "build)"
        )
    return ""


def _noop_cleanup() -> None:
    """Cleanup for every discovery path that never allocates a temp
    directory -- i.e. every path except a successful build-and-read."""


def _try_build_and_read(
    backend: str,
    project_dir: Path,
    *,
    no_build_isolation: bool,
    reason: str,
) -> tuple[list[IncludedFile], Callable[[], None]] | None:
    """Shared entry point for both ``--allow-build`` call sites in
    :func:`_discover_included_files`: logs the one security-relevant
    ``WARNING:`` (wording varies by *reason*), then delegates to the
    generic, backend-agnostic
    :func:`~pitloom.core._models_wheel_build_and_read.build_and_read_wheel`.

    Never invoked unless ``allow_build=True`` at the caller -- enforced
    by the caller, not here, so this function has no ``allow_build``
    parameter of its own to accidentally forget to check.
    """
    # pylint: disable-next=import-outside-toplevel
    from pitloom.core._models_wheel_build_and_read import build_and_read_wheel

    log.warning(
        "Build: --allow-build is invoking a real PEP 517 build for %s "
        "(backend=%r, %s) to discover its file list -- this executes "
        "third-party build-time code%s",
        project_dir,
        backend,
        reason,
        ", without build isolation (--no-build-isolation)"
        if no_build_isolation
        else " in an isolated build environment",
    )
    return build_and_read_wheel(project_dir, isolated=not no_build_isolation)


def _discover_included_files(
    project_dir: Path,
    *,
    assume_backend: str | None = None,
    allow_build: bool = False,
    no_build_isolation: bool = False,
) -> tuple[list[IncludedFile], Callable[[], None]]:
    """Resolve the wheel's file list via the project's build backend.

    Any backend other than Hatchling that doesn't have a dedicated
    discovery module (or whose static config can't be resolved) falls
    back to the Hatchling-based heuristic, with a ``WARNING:`` since
    the result may not accurately reflect that backend's actual
    inclusion rules -- unless *allow_build* opts into a real PEP 517
    build instead (see
    :mod:`pitloom.core._models_wheel_build_and_read`), which is tried
    first in both of those cases (no dedicated module at all, or a
    dedicated module whose own static discovery failed) before falling
    back to Hatchling.

    Returns the resolved files plus a cleanup callback the caller MUST
    invoke once done consuming the files' ``.path`` values -- a no-op
    for every path except a successful build-and-read, whose real files
    live in a temp directory the callback removes.

    *assume_backend*, when given, skips reading ``pyproject.toml`` and
    detecting the backend entirely and dispatches straight to that
    backend -- for callers that already know it by construction (e.g.
    the Hatchling build hook, which is definitionally always Hatchling).
    """
    # pylint: disable=import-outside-toplevel
    from pitloom.core._models_wheel_flit import discover as discover_flit
    from pitloom.core._models_wheel_pdm import discover as discover_pdm
    from pitloom.core._models_wheel_poetry import discover as discover_poetry
    from pitloom.core._models_wheel_setuptools import discover as discover_setuptools
    from pitloom.extract.project.setuptools import (
        detect_build_backend,
        read_pyproject_toml,
    )

    backend_discoverers: dict[str, BackendDiscoverer] = {
        "setuptools": discover_setuptools,
        "poetry": discover_poetry,
        "flit": discover_flit,
        "pdm": discover_pdm,
    }

    pyproject_data: dict[str, object] | None
    if assume_backend is not None:
        backend: str | None = assume_backend
        pyproject_data = None
    else:
        # Parsed once and reused for backend detection and setuptools' own
        # static-config check below -- both read the same pyproject.toml.
        pyproject_data = read_pyproject_toml(project_dir)
        backend = detect_build_backend(project_dir, pyproject_data=pyproject_data)

    if backend not in (None, "hatchling"):
        discoverer = backend_discoverers.get(backend)
        if discoverer is None:
            # No static module for this backend at all -- uv_build
            # today, any future/unrecognized backend, or a Track B
            # backend (maturin, scikit-build-core, meson-python) once
            # its own toolchain happens to be available. No
            # backend-specific code needed for any of these to start
            # working the moment allow_build=True.
            if allow_build:
                build_result = _try_build_and_read(
                    backend,
                    project_dir,
                    no_build_isolation=no_build_isolation,
                    reason="no static discovery module registered",
                )
                if build_result is not None:
                    return build_result
                # _try_build_and_read/build_and_read_wheel() already
                # logged its own specific failure WARNING:; fall
                # through to the generic "not backend-aware" warning.
            log.warning(
                "File discovery for build backend %r is not yet "
                "backend-aware%s -- using Hatchling-based heuristic, "
                "file list may be inaccurate for this project%s",
                backend,
                "" if not allow_build else " (build-and-read failed)",
                _unhandled_backend_hint(backend, pyproject_data),
            )
        else:
            # Only a "writer" backend (setuptools, PDM) process-wide
            # os.chdir()s for the duration of its call and needs
            # _DISCOVERY_LOCK's exclusive write mode -- see the lock's own
            # docstring and _WRITER_BACKENDS' definition. Every other backend
            # (Poetry and Flit included: neither touches cwd) is a "reader"
            # and only needs to be kept out of a concurrent writer's chdir
            # window, not out of each other's way.
            lock_ctx = (
                _DISCOVERY_LOCK.write()
                if backend in _WRITER_BACKENDS
                else _DISCOVERY_LOCK.read()
            )
            with lock_ctx:
                files = discoverer(project_dir, pyproject_data=pyproject_data)
            if files is not None:
                return files, _noop_cleanup
            # The registered backend's own static discoverer gave up.
            # This is the "robustness fallback for Track A" the
            # roadmap names for the build-and-read mechanism -- ANY
            # registered backend (setuptools, poetry, pdm, flit)
            # benefits automatically here, with zero backend-specific
            # wiring, because build_and_read_wheel() doesn't care what
            # backend it is. Must never be reached when the static
            # discoverer already succeeded above (that returns
            # immediately) -- a real build must never run when the
            # fast, safe static rescan already worked.
            if allow_build:
                build_result = _try_build_and_read(
                    backend,
                    project_dir,
                    no_build_isolation=no_build_isolation,
                    reason="its own static discovery failed",
                )
                if build_result is not None:
                    return build_result
            if _skip_hatchling_fallback(backend, pyproject_data, project_dir):
                return [], _noop_cleanup

    # Hatchling's discover() never touches cwd (project_dir is always
    # already absolute here -- see get_wheel_files), so concurrent
    # Hatchling calls only need to be kept out of a concurrent writer's
    # chdir window, never out of each other's way.
    with _DISCOVERY_LOCK.read():
        return _models_wheel_hatchling.discover(project_dir) or [], _noop_cleanup
