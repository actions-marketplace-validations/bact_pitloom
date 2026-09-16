# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pitloom.assemble.spdx3.fragments import (
    _fragment_read_failure_message,
    _missing_fragment_message,
)
from pitloom.cli.commands.utils import (
    _import_spdx3_validate,
    _validate_spdx3_documents,
    cli_error_handler,
)
from pitloom.core.config import FragmentConfig, read_pitloom_config

log = logging.getLogger(__name__)


@cli_error_handler("fragment validate failed")
def _run_fragment_validate(args: argparse.Namespace) -> int:
    """Run `pitloom fragment validate`."""
    # Both checks run and report independently -- a user missing the
    # optional dependency AND passing a bad path should see both ERROR:
    # lines in one run, not just the first one, for one round trip.
    dependency_ok = _import_spdx3_validate() is not None

    paths: list[Path] = args.paths
    not_files = [p for p in paths if not p.is_file()]
    for p in not_files:
        kind = "directory" if p.is_dir() else "file not found"
        print(f"ERROR: {kind}: {p}", file=sys.stderr)

    if not dependency_ok or not_files:
        return 1

    exit_code = _validate_spdx3_documents(
        [str(p) for p in paths], check_merged=not args.no_merge
    )
    if exit_code == 0:
        print(f"pitloom fragment validate: {len(paths)} document(s) valid")
    return exit_code


def _fragment_element_count(fragment_path: Path, *, required: bool) -> int | None:
    """Return the fragment's ``@graph`` element count, or ``None`` if the
    file couldn't be read/parsed -- logs a WARNING (shared wording with
    ``merge_fragments()``) in that case."""
    try:
        data = json.loads(fragment_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        log.warning(
            _fragment_read_failure_message(fragment_path, exc, required=required)
        )
        return None
    return len(data.get("@graph", [])) if isinstance(data, dict) else None


def _fragment_sha256(path: Path) -> str:
    """Chunked-read SHA-256 hex digest of *path* -- never loads the whole
    file into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fragment_sha256_status(
    fragment_path: Path, expected_sha256: str | None, exists: bool
) -> str:
    """Three-state SHA-256 display: ``-`` (not configured), ``unknown``
    (configured but can't check), or ``match``/``mismatch``. Logs a
    WARNING on mismatch."""
    if expected_sha256 is None:
        return "-"
    if not exists:
        return "unknown"
    actual = _fragment_sha256(fragment_path)
    if actual.lower() == expected_sha256.lower():
        return "match"
    log.warning(
        "SBOM fragment %s SHA-256 mismatch: configured %s, actual %s",
        fragment_path,
        expected_sha256,
        actual,
    )
    return "mismatch"


def _fragment_modified(fragment_path: Path) -> str:
    """ISO 8601 UTC last-modified timestamp for *fragment_path*."""
    return datetime.fromtimestamp(
        fragment_path.stat().st_mtime, tz=timezone.utc
    ).isoformat()


def _print_fragment_list_line(
    frag: FragmentConfig,
    *,
    exists: bool,
    elements: int | None,
    sha_status: str,
    modified: str | None,
) -> None:
    """Print one `pitloom fragment list` output line for *frag*."""
    print(
        f"PATH={frag.path} ROLE={frag.role or '-'} "
        f"REQUIRED={'true' if frag.required else 'false'} "
        f"EXISTS={'true' if exists else 'false'} "
        f"ELEMENTS={elements if elements is not None else '-'} "
        f"SHA256={sha_status} "
        f"MODIFIED={modified if modified is not None else '-'}"
    )


def _report_fragment(project_dir: Path, frag: FragmentConfig) -> bool:
    """Log/print one configured fragment's status; return True if it's a
    ``required=True`` fragment that's missing (the exit-code-affecting
    condition)."""
    fragment_path = project_dir / frag.path
    exists = fragment_path.is_file()
    if not exists:
        log.warning(_missing_fragment_message(fragment_path, required=frag.required))

    elements = (
        _fragment_element_count(fragment_path, required=frag.required)
        if exists
        else None
    )
    sha_status = _fragment_sha256_status(fragment_path, frag.sha256, exists)
    modified = _fragment_modified(fragment_path) if exists else None

    _print_fragment_list_line(
        frag, exists=exists, elements=elements, sha_status=sha_status, modified=modified
    )
    return frag.required and not exists


@cli_error_handler("fragment list failed")
def _run_fragment_list(args: argparse.Namespace) -> int:
    """Run `pitloom fragment list`."""
    project_dir: Path = (args.project_dir or Path.cwd()).resolve()
    pitloom_config = read_pitloom_config(project_dir / "pyproject.toml")

    if not pitloom_config.fragments:
        print("pitloom fragment list: no fragments configured")
        return 0

    unmet_required = [
        _report_fragment(project_dir, frag) for frag in pitloom_config.fragments
    ]
    return 1 if any(unmet_required) else 0


def _run_fragment_command(args: argparse.Namespace) -> int:
    """Dispatch `pitloom fragment <command> ...` arguments."""
    if args.fragment_command == "validate":
        return _run_fragment_validate(args)
    if args.fragment_command == "list":
        return _run_fragment_list(args)
    return 1


def add_parser(subparsers: Any, _parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``fragment`` subcommand to the main parser."""
    fragment_parser = subparsers.add_parser(
        "fragment",
        help="Work with dynamic execution SBOM fragments.",
        description=(
            "Work with dynamic execution SBOM fragments -- see also "
            "'pitloom merge' to combine fragments into one SBOM."
        ),
    )
    fragment_subparsers = fragment_parser.add_subparsers(
        dest="fragment_command", required=True
    )

    validate_parser = fragment_subparsers.add_parser(
        "validate",
        help="Validate SPDX 3 JSON document(s) against schema and SHACL rules.",
    )
    validate_parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        metavar="PATH",
        help="SPDX 3 JSON document(s) to validate.",
    )
    validate_parser.add_argument(
        "--no-merge",
        action="store_true",
        help=(
            "Skip the merged-graph check across multiple PATHs (which "
            "catches type errors across ExternalMap references); validate "
            "each document only in isolation."
        ),
    )

    list_parser = fragment_subparsers.add_parser(
        "list",
        help="List configured SBOM fragments and their status.",
    )
    list_parser.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help="Project directory containing pyproject.toml (default: cwd).",
    )

    fragment_parser.set_defaults(func=_run_fragment_command)
