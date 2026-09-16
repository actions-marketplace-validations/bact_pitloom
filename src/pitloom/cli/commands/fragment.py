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


def _fragment_read_status(
    fragment_path: Path, *, required: bool
) -> tuple[bytes | None, bool, int | None]:
    """Read and JSON-parse *fragment_path* once, for both the element
    count and the SHA-256 check below -- avoids reading the same fragment
    file twice. Returns ``(raw_bytes, read_ok, element_count)``:

    - ``raw_bytes`` is the file's contents, or ``None`` if it couldn't be
      read at all.
    - ``read_ok`` is False on any read or JSON-parse failure -- this is
      the same condition that also makes ``merge_fragments()`` treat a
      ``required=True`` fragment as unmet, so callers should key exit-code
      decisions on this, not on ``element_count``.
    - ``element_count`` is the fragment's ``@graph`` length, or ``None``
      if the parsed JSON isn't an object (not itself a read failure).

    Logs a WARNING (shared wording with ``merge_fragments()``) on any read
    or parse failure.
    """
    try:
        raw = fragment_path.read_bytes()
    except OSError as exc:
        log.warning(
            _fragment_read_failure_message(fragment_path, exc, required=required)
        )
        return None, False, None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        log.warning(
            _fragment_read_failure_message(fragment_path, exc, required=required)
        )
        return raw, False, None
    elements = len(data.get("@graph", [])) if isinstance(data, dict) else None
    return raw, True, elements


def _fragment_sha256_status(
    raw: bytes | None, expected_sha256: str | None, fragment_path: Path
) -> str:
    """Three-state SHA-256 display: ``-`` (not configured), ``unknown``
    (configured but the file couldn't be read), or ``match``/``mismatch``.
    Logs a WARNING on mismatch. *raw* is checked independently of JSON
    validity -- a fragment with broken JSON can still have its hash
    verified, matching pre-existing behavior."""
    if expected_sha256 is None:
        return "-"
    if raw is None:
        return "unknown"
    actual = hashlib.sha256(raw).hexdigest()
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
    # frag.role is None (not configured) vs "" (explicitly set empty) are
    # distinct states -- only None prints as "-", matching this project's
    # own None-vs-empty convention (see CLAUDE.md "Recurring bug patterns").
    role = frag.role if frag.role is not None else "-"
    print(
        f"PATH={frag.path} ROLE={role} "
        f"REQUIRED={'true' if frag.required else 'false'} "
        f"EXISTS={'true' if exists else 'false'} "
        f"ELEMENTS={elements if elements is not None else '-'} "
        f"SHA256={sha_status} "
        f"MODIFIED={modified if modified is not None else '-'}"
    )


def _report_fragment(project_dir: Path, frag: FragmentConfig) -> bool:
    """Log/print one configured fragment's status; return True if it's a
    ``required=True`` fragment that's missing OR unreadable -- the same
    condition that makes ``merge_fragments()`` raise ``FragmentMergeError``,
    so the exit code stays a reliable predictor of a real build's outcome."""
    fragment_path = project_dir / frag.path
    exists = fragment_path.is_file()
    if not exists:
        log.warning(_missing_fragment_message(fragment_path, required=frag.required))
        raw, read_ok, elements = None, False, None
    else:
        raw, read_ok, elements = _fragment_read_status(
            fragment_path, required=frag.required
        )

    sha_status = _fragment_sha256_status(raw, frag.sha256, fragment_path)
    modified = _fragment_modified(fragment_path) if exists else None

    _print_fragment_list_line(
        frag, exists=exists, elements=elements, sha_status=sha_status, modified=modified
    )
    return frag.required and (not exists or not read_ok)


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
