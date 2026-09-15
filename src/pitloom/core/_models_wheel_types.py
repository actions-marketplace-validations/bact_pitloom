# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared types for per-backend wheel file discovery.

See also: :mod:`pitloom.core._models_wheel` (dispatch facade),
:mod:`pitloom.core._models_wheel_hatchling`,
:mod:`pitloom.core._models_wheel_setuptools`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, Protocol, TypedDict

from pitloom.core.content_type_config import ContentTypeOverride

if TYPE_CHECKING:
    from pitloom.extract._file_headers import FileHeaderMetadata


class IncludedFile(NamedTuple):
    """One file that belongs in the wheel, as resolved by a backend.

    Mirrors the two attributes every backend-specific discoverer and
    Hatchling's own ``hatchling.builders.plugin.interface.IncludedFile``
    both expose, so the shared per-file processing loop in
    :mod:`pitloom.core._models_wheel` can consume either uniformly.
    """

    path: str
    distribution_path: str


# pylint: disable-next=too-few-public-methods
class BackendDiscoverer(Protocol):
    """Call signature every backend discovery module's ``discover()`` must
    share, so the dispatch registry in :mod:`pitloom.core._models_wheel`
    can call any of them uniformly -- adding a new backend is then one
    module implementing this signature plus one registry entry, never a
    special case at the call site. *pyproject_data*, when given, is the
    already-parsed ``pyproject.toml`` (see
    :func:`pitloom.extract.project.setuptools.read_pyproject_toml`); a backend
    that doesn't need it (e.g. Hatchling, which re-reads config itself via
    ``WheelBuilder``) still accepts and ignores the keyword."""

    def __call__(
        self, project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile] | None: ...


def has_resolvable_pyproject_config(
    pyproject_data: dict[str, object], backend: str
) -> bool:
    """Whether the parsed ``pyproject.toml`` declares enough for *backend*
    to resolve packages from: a PEP 621 ``[project]`` table (every
    registered backend's own zero-config auto-discovery applies here,
    even without an explicit ``[tool.<backend>]`` table) or an explicit
    ``[tool.<backend>]`` table. A ``pyproject.toml`` with only
    ``[build-system]`` (e.g. packages declared imperatively in
    ``setup.py`` instead) declares neither.

    Shared by :mod:`pitloom.core._models_wheel_setuptools` (deciding
    whether to attempt static discovery at all) and
    :mod:`pitloom.core._models_wheel` (deciding what a failed
    discoverer's fallback ``WARNING:`` should say), so the two stay in
    sync rather than re-deriving the same check independently."""
    tool = pyproject_data.get("tool", {})
    return "project" in pyproject_data or (
        backend in tool if isinstance(tool, dict) else False
    )


def is_dist_info_path(distribution_path: str) -> bool:
    """Whether *distribution_path* falls under a wheel's own
    ``<name>-<version>.dist-info/`` directory -- build-generated,
    never a project source file.

    No existing static backend module needs this: each one's underlying
    library (``recurse_included_files()``, ``find_files_to_add()``,
    ``WheelBuilder.get_files()``, ``Module.iter_files()``, setuptools'
    ``build_py``) never surfaces ``.dist-info`` paths from its own
    file-discovery entry point in the first place. This is the first
    consumer -- :mod:`pitloom.core._models_wheel_build_and_read`, which
    reads an already-built wheel's real zip contents (which genuinely
    does contain ``.dist-info``) and must filter it back out to match
    every other backend's ``IncludedFile`` contract of pre-build source
    files only.

    *distribution_path* MUST already be POSIX-normalized (see
    :func:`to_posix_distribution_path`) -- this function does no
    normalization of its own and will not recognize a
    backslash-separated path as a ``.dist-info`` path.
    """
    return "/" in distribution_path and distribution_path.split("/", 1)[0].endswith(
        ".dist-info"
    )


def to_posix_distribution_path(path: str) -> str:
    """Normalize *path* to forward-slash separators for use as an
    ``IncludedFile.distribution_path`` -- a wheel's internal paths are
    always ``/``-separated regardless of the platform Pitloom runs on.

    Shared so this one-line normalization doesn't keep getting
    hand-copied per backend discovery module (setuptools, Hatchling,
    Poetry, Flit each needed it independently) -- see CLAUDE.md's note
    that a pattern repeated across 3+ call sites drifts."""
    return path.replace("\\", "/")


class FileScanConfig(NamedTuple):
    """Optional per-file header/content-type scanner config, bundled so
    it threads through :mod:`pitloom.core._models_wheel`'s per-file
    helpers as one object instead of four separate parameters each.

    ``parse_header``/``detect_content`` are ``None`` when their
    respective scan (``scan_file_headers``/``detect_content_type``) is
    off -- see :func:`~pitloom.core._models_wheel._resolve_file_header_extras`,
    the sole consumer.
    """

    parse_header: Callable[[bytes], FileHeaderMetadata | None] | None
    detect_content: Callable[[bytes, str, str], tuple[str | None, str | None]] | None
    content_type_overrides: tuple[ContentTypeOverride, ...]
    content_type_method: str


class FileHeaderExtras(TypedDict):
    """Keyword arguments for :class:`~pitloom.core.project.ProjectFile`'s
    header/content-type fields."""

    copyright_text: str | None
    copyright_source: str | None
    file_contributors: list[str]
    file_type: str | None
    spdx_license_identifier: str | None
    content_type: str | None
    content_type_method: str | None
