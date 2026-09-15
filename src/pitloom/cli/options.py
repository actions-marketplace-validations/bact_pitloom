# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator.

Shared ``add_*_argument()`` flag-definition helpers and their
``warn_*()`` companions. Config-cascade *resolution* logic (turning
parsed ``args`` plus ``[tool.pitloom]`` into effective settings) lives
in :mod:`pitloom.cli.options_resolve`, split out once this file crossed
the ~400-500 line soft limit -- re-exported below so every existing
``from pitloom.cli.options import ...`` call site needed no changes.
"""

from __future__ import annotations

import argparse
import logging

# Re-exports (mypy's explicit-reexport check under strict=true needs
# either "import X as X" or __all__ membership for a name to count as
# part of this module's own public surface; __all__ below satisfies
# both mypy and pyflakes -- "as X" self-aliasing satisfies mypy but
# pyflakes still flags it as an unused import) -- see the module
# docstring.
from pitloom.cli.options_resolve import (
    _load_pitloom_tool_section,
    _quote_optional,
    _resolve_common_options,
    _resolve_creation_metadata,
    _resolve_describe_relationship,
    _resolve_hf_output_path,
    _resolve_model_output_path,
    _resolve_output_path,
    _resolve_output_source,
    _resolve_pretty,
    _resolve_project_generation_settings,
    _resolve_project_paths,
    _ResolvedCreationMetadata,
    _ResolvedCreators,
    _ResolvedTools,
    _ResolvedValue,
)
from pitloom.core._models_wheel_types import BUILD_LOG_PREFIX

__all__ = [
    "_load_pitloom_tool_section",
    "_quote_optional",
    "_resolve_common_options",
    "_resolve_creation_metadata",
    "_resolve_describe_relationship",
    "_resolve_hf_output_path",
    "_resolve_model_output_path",
    "_resolve_output_path",
    "_resolve_output_source",
    "_resolve_pretty",
    "_resolve_project_generation_settings",
    "_resolve_project_paths",
    "_ResolvedCreationMetadata",
    "_ResolvedCreators",
    "_ResolvedTools",
    "_ResolvedValue",
    "add_offline_argument",
    "add_use_lockfile_argument",
    "add_allow_build_argument",
    "add_no_build_isolation_argument",
    "warn_if_no_build_isolation_without_allow_build",
    "add_debug_argument",
]

log = logging.getLogger(__name__)


def add_offline_argument(parser: argparse.ArgumentParser, effect: str) -> None:
    """Add the shared ``--offline``/``--no-offline`` flag.

    The mechanics (``BooleanOptionalAction``, ``default=None`` so the CLI
    can defer to ``[tool.pitloom] offline`` when omitted) and the closing
    "Defers to..." sentence are identical for every command that offers
    this flag; only what "forbid network access" actually does differs by
    command/target. *effect* is spliced in verbatim right after "Forbid
    network access" (include its own leading punctuation and trailing
    period, e.g. ``" -- skip PyPI lookup, no error (...)."``) so each
    caller keeps its own accurate, command-specific wording instead of one
    generic sentence that would misdescribe some commands' actual behaviour.
    """
    parser.add_argument(
        "--offline",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            f"Forbid network access{effect} Defers to [tool.pitloom] "
            "offline (off by default) when omitted."
        ),
    )


def add_use_lockfile_argument(parser: argparse.ArgumentParser, effect: str) -> None:
    """Add the shared ``--use-lockfile``/``--no-use-lockfile`` flag.

    Unlike ``--offline``/``--enrich`` this is an *opt-out* flag: the lock/pin
    file cascade is on by default. ``default=None`` here still means
    "unset", deferring to ``[tool.pitloom] use-lockfile`` (itself on by
    default) when omitted.
    """
    parser.add_argument(
        "--use-lockfile",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            f"Resolve exact versions from a lock/pin file cascade{effect} "
            "Defers to [tool.pitloom] use-lockfile (on by default) when "
            "omitted."
        ),
    )


def add_allow_build_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--allow-build`` flag.

    Unlike ``--offline``/``--use-lockfile`` above, this is a plain
    ``store_true`` flag with a literal ``False`` default, not a
    ``BooleanOptionalAction`` deferring to ``[tool.pitloom]`` when unset --
    deliberately: the config file being read lives in the (untrusted)
    project being scanned, and it must never be able to silently opt
    itself into third-party code execution. This always defaults to off
    and must be passed explicitly on every invocation that wants it.
    """
    parser.add_argument(
        "--allow-build",
        action="store_true",
        default=False,
        help=(
            "SECURITY: allow Pitloom to invoke a project's own PEP 517 "
            "build backend (subprocess; may install build-requires from "
            "the network) to discover a wheel's real file list -- either "
            "for a backend with no static-config discovery module of its "
            "own (currently: uv_build), or as a fallback when a "
            "supported backend's own static discovery fails on this "
            "project. Executes third-party build-time code. Off by "
            "default -- without it, an unhandled or failed backend falls "
            "back to the Hatchling-based heuristic with a WARNING:, "
            "unchanged. Deliberately has no [tool.pitloom] equivalent, "
            "unlike --offline/--content-type above: a target project's "
            "own pyproject.toml must never be able to silently enable "
            "code execution for whoever scans it."
        ),
    )


def add_no_build_isolation_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--no-build-isolation`` flag. No effect without
    ``--allow-build`` (each caller warns if passed without it)."""
    parser.add_argument(
        "--no-build-isolation",
        action="store_true",
        default=False,
        help=(
            "With --allow-build, skip creating an isolated build "
            "environment and use the current Python environment's "
            "already-installed build backend instead (faster, no "
            "network) -- mirrors 'python -m build --no-isolation'. No "
            "effect without --allow-build (logs a WARNING: if passed "
            "alone)."
        ),
    )


def warn_if_no_build_isolation_without_allow_build(
    args: argparse.Namespace, subject: object
) -> None:
    """Check and, if needed, log the shared ``WARNING:`` for
    ``--no-build-isolation`` passed without ``--allow-build``. Every
    command offering both flags calls this instead of repeating the
    ``if args.no_build_isolation and not args.allow_build:`` guard
    itself, so the check and its wording stay identical everywhere
    (mirrors :func:`warn_use_lockfile_no_effect` in
    :mod:`pitloom.extract.project.reader`)."""
    if args.no_build_isolation and not args.allow_build:
        log.warning(
            "%s%s: --no-build-isolation has no effect without --allow-build",
            BUILD_LOG_PREFIX,
            subject,
        )


def add_debug_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--debug``/``--no-debug`` flag.

    Same ``BooleanOptionalAction``/``default=None`` mechanics as
    :func:`add_offline_argument` -- ``None`` (the flag omitted) means
    "no explicit choice", letting :func:`pitloom.logging_config.apply_debug_override`
    leave an ambient ``PITLOOM_DEBUG`` as it found it, rather than the CLI
    silently forcing debug output off.
    """
    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Surface DEBUG:-level diagnostics on stderr (developer detail, "
            "e.g. why an extraction step was skipped). Same effect as "
            "setting PITLOOM_DEBUG=1; --no-debug overrides an ambient "
            "PITLOOM_DEBUG back off for this invocation. Covers entry "
            "points that don't parse this flag (the Hatchling build hook, "
            "the library API) either way."
        ),
    )
