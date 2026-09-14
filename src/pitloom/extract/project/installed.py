# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""In-tree ``.egg-info``/``.dist-info`` as a supplementary project-metadata
source (V1: in-tree only -- a build backend's editable-install byproduct
left next to ``pyproject.toml``, not the real installed record in a venv's
``site-packages``; see ``working-docs/design/installed-dist-info-source.md``
for the full design, including the deferred site-packages-aware phase).

Three concerns, kept in this order to match the plan they came from:

- Discovery (:func:`find_installed_metadata_candidate`): bounded-glob
  search for an in-tree candidate whose declared ``Name`` matches the
  project already resolved by the static tiers (``pyproject.toml``/
  ``setup.cfg``/``setup.py``).
- Parsing (:func:`_parse_installed_metadata`): RFC 822 Core Metadata
  fields into a :class:`~pitloom.core.project.ProjectMetadata`.
- Reconciliation (:func:`reconcile_installed_metadata`): fold the parsed
  installed metadata into the static metadata -- static always wins on a
  genuine disagreement (recorded, never silently substituted); installed
  only fills gaps the static source left undeclared.

Written so a future site-packages-aware discovery function can reuse
parsing and reconciliation unchanged, swapping only discovery.
"""

from __future__ import annotations

import dataclasses
import email
import email.message
import logging
from collections.abc import Callable
from pathlib import Path

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name

from pitloom.core.project import (
    _PROVENANCE_KEY_ALIASES,
    ConflictCandidate,
    ProjectMetadata,
)
from pitloom.extract._extract_utils import field_declared, to_str_list
from pitloom.extract._license import normalize_license_expression
from pitloom.extract.lock._common import is_same_version

log = logging.getLogger(__name__)

#: Bounded, non-recursive glob patterns searched for an in-tree
#: ``.egg-info``/``.dist-info`` directory -- never ``rglob``/a recursive
#: walk (perf and safety: must not descend into an accidentally-vendored
#: ``node_modules``/``vendor/`` tree sitting inside the project directory).
#:
#: ``src/*.egg-info``/``src/*.dist-info`` (one path segment under ``src/``)
#: is the empirically-verified real case: setuptools' own ``egg_info``
#: command writes ``<name>.egg-info`` directly under ``src/`` for a
#: ``package_dir={"": "src"}`` project (verified via a real
#: ``python setup.py egg_info`` run against a ``src/``-layout project --
#: it does **not** nest it inside an extra package-name directory).
#: ``src/*/*.egg-info``/``src/*/*.dist-info`` (two segments) is kept
#: alongside it defensively for a layout/backend this project hasn't
#: independently verified writes there, since the bounded, shallow glob
#: costs little to keep broad.
_CANDIDATE_GLOBS = (
    "*.egg-info",
    "*.dist-info",
    "src/*.egg-info",
    "src/*.dist-info",
    "src/*/*.egg-info",
    "src/*/*.dist-info",
)

#: Fields checked for a genuine disagreement between static and installed
#: metadata: a real conflict is recorded (never silently substituted) and
#: static's value wins.
_CONFLICT_CHECKED_FIELDS = frozenset({"version", "requires_python", "license_name"})

#: Fields only ever gap-filled from installed metadata when static left
#: them undeclared -- equality semantics are too fuzzy to flag as a
#: conflict (e.g. ``Summary`` free text), so no comparison is attempted.
_GAP_FILL_ONLY_FIELDS = frozenset({"description", "keywords", "urls"})


def _requires_python_equal(a: str, b: str) -> bool:
    """PEP 440 specifier-set equality (``'>=3.9'`` == ``'>= 3.9'``), not
    raw string equality. Falls back to stripped-string equality if either
    side fails to parse as a :class:`~packaging.specifiers.SpecifierSet`
    (never raise)."""
    try:
        return SpecifierSet(a) == SpecifierSet(b)
    except InvalidSpecifier:
        return a.strip() == b.strip()


_FIELD_COMPARATORS: dict[str, Callable[[str, str], bool]] = {
    "version": is_same_version,
    "license_name": lambda a, b: (
        normalize_license_expression(a) == normalize_license_expression(b)
    ),
    "requires_python": _requires_python_equal,
}


def _marker_filename(candidate_dir: Path) -> str:
    """Return the defining marker filename for *candidate_dir*'s format."""
    return "PKG-INFO" if candidate_dir.name.endswith(".egg-info") else "METADATA"


def _read_marker_text(marker_path: Path) -> str | None:
    """Read *marker_path* leniently, decoding with ``errors="replace"``
    (mirrors :mod:`pitloom.extract.wheel`'s existing decode pattern) so a
    malformed/binary marker file never raises. Returns ``None`` on a
    genuine access failure (``OSError``)."""
    try:
        raw = marker_path.read_bytes()
    except OSError:
        return None
    return raw.decode("utf-8", errors="replace")


@dataclasses.dataclass
class _Candidate:
    """One surviving in-tree metadata candidate: its marker file, human
    label, and already-parsed message (kept in memory so the winner
    doesn't need re-parsing by a second discovery pass)."""

    marker_path: Path
    label: str
    message: email.message.Message


def _sort_key(candidate: _Candidate) -> tuple[int, str]:
    """Deterministic tie-break: ``.dist-info`` before ``.egg-info``
    (rank 0 vs 1), then alphabetical marker path -- never filesystem/glob
    iteration order."""
    is_egg_info = candidate.marker_path.parent.name.endswith(".egg-info")
    return (1 if is_egg_info else 0, str(candidate.marker_path))


def _evaluate_candidate_dir(
    candidate_dir: Path, resolved_name: str, project_dir: Path, *, quiet: bool
) -> _Candidate | None:
    """Evaluate one glob-matched directory: marker-file presence,
    readability, and name match. Returns ``None`` (after logging the
    appropriate ``WARNING:`` unless *quiet*) for anything that doesn't
    survive to become a genuine candidate.

    Split out of :func:`find_installed_metadata_candidate` purely to keep
    that function's own cognitive-complexity ratchet -- no behavior
    split, just a named per-candidate step.
    """
    label = candidate_dir.name
    marker_name = _marker_filename(candidate_dir)
    marker_path = candidate_dir / marker_name
    if not marker_path.exists():
        if not quiet:
            log.warning(
                "%s: %s exists but has no %s -- ignoring it",
                project_dir,
                label,
                marker_name,
            )
        return None
    text = _read_marker_text(marker_path)
    if text is None:
        if not quiet:
            log.warning(
                "%s: %s exists but %s could not be read -- ignoring it",
                project_dir,
                label,
                marker_name,
            )
        return None
    msg = email.message_from_string(text)
    candidate_name = msg.get("Name") if field_declared(msg, "Name") else None
    if not candidate_name or (
        canonicalize_name(candidate_name) != canonicalize_name(resolved_name)
    ):
        if not quiet:
            log.warning(
                "%s: %s declares name %r, which does not match the "
                "resolved project name %r -- ignoring it entirely",
                project_dir,
                label,
                candidate_name,
                resolved_name,
            )
        return None
    return _Candidate(marker_path=marker_path, label=label, message=msg)


def _discover_candidate(
    project_dir: Path, resolved_name: str, *, quiet: bool = False
) -> _Candidate | None:
    """Search *project_dir* for an in-tree ``.egg-info``/``.dist-info``
    directory whose declared ``Name`` canonically matches *resolved_name*,
    returning the winning :class:`_Candidate` -- marker path, human label,
    and its already-parsed :class:`email.message.Message` -- so a caller
    that needs the parsed metadata (:func:`reconcile_installed_metadata`'s
    caller in ``reader.py``) never has to re-read and re-parse the exact
    bytes this function already read. :func:`find_installed_metadata_candidate`
    is the public, tuple-returning wrapper for callers that only need the
    path/label.

    A name-mismatched candidate is rejected entirely -- before the
    dist-info-vs-egg-info tie-break ever runs, not after -- so a
    wrong-name ``.dist-info`` can never out-rank a correct-name
    ``.egg-info`` on format alone (see "Name/identity safety gate" in
    ``working-docs/design/installed-dist-info-source.md``).

    Silent when nothing was found at all in the initial glob (the normal,
    common case). Every candidate that *was* found but rejected (missing
    marker file, unreadable marker file, name mismatch) gets its own
    ``WARNING:`` unless *quiet*.
    """
    found_dirs = sorted(
        {d for pattern in _CANDIDATE_GLOBS for d in project_dir.glob(pattern)}
    )

    survivors: list[_Candidate] = []
    for candidate_dir in found_dirs:
        if not candidate_dir.is_dir():
            continue
        candidate = _evaluate_candidate_dir(
            candidate_dir, resolved_name, project_dir, quiet=quiet
        )
        if candidate is not None:
            survivors.append(candidate)

    if not survivors:
        return None
    if len(survivors) == 1:
        return survivors[0]

    survivors.sort(key=_sort_key)
    winner = survivors[0]
    if not quiet:
        found_labels = ", ".join(c.label for c in survivors)
        log.warning(
            "%s: multiple installed-metadata candidates found (%s) -- using %s",
            project_dir,
            found_labels,
            winner.label,
        )
    return winner


def find_installed_metadata_candidate(
    project_dir: Path, resolved_name: str, *, quiet: bool = False
) -> tuple[Path, str] | None:
    """Search *project_dir* for an in-tree ``.egg-info``/``.dist-info``
    directory whose declared ``Name`` canonically matches *resolved_name*.

    Returns ``(marker_file_path, human_label)`` for the single winning
    candidate (e.g. ``(Path(".../mypkg.egg-info/PKG-INFO"),
    "mypkg.egg-info")``), or ``None`` when nothing usable was found. See
    :func:`_discover_candidate` for the full behavior this wraps.
    """
    candidate = _discover_candidate(project_dir, resolved_name, quiet=quiet)
    if candidate is None:
        return None
    return candidate.marker_path, candidate.label


def _parse_installed_urls(msg: email.message.Message) -> dict[str, str]:
    """Extract ``urls`` from ``Project-URL`` (multiple, ``Label, URL``)
    plus legacy ``Home-page`` mapped to key ``"Homepage"`` only if no
    ``Project-URL`` already used that key.

    Splits each ``Project-URL`` value on the first comma only (matching
    :mod:`pitloom.extract.wheel`'s existing convention) -- a URL's own
    query string can legally contain commas.
    """
    urls: dict[str, str] = {}
    for entry in msg.get_all("Project-URL") or []:
        if "," in entry:
            label, url = entry.split(",", 1)
            urls[label.strip()] = url.strip()
    homepage = msg.get("Home-page")
    if homepage and "Homepage" not in urls:
        urls["Homepage"] = homepage
    return urls


def _parse_installed_metadata(
    msg: email.message.Message, source_label: str
) -> ProjectMetadata:
    """Map RFC 822 Core Metadata fields from *msg* into a
    :class:`~pitloom.core.project.ProjectMetadata`.

    Presence is gated via :func:`~pitloom.extract._extract_utils.field_declared`
    (works on :class:`email.message.Message` via ``in``), never via the
    resolved value's truthiness -- an explicit ``Keywords:`` header with
    an empty value is a declared-empty, not absent.

    Not extracted in V1 (see ``working-docs/design/installed-dist-info-source.md``):
    ``license_files`` (``License-File`` paths use a different base than
    :attr:`ProjectMetadata.license_files`), ``authors`` (collapsing PEP
    621's structured ``project.authors`` list down to one flat ``Author``
    string is lossy in a way that can't be cleanly reversed), and
    ``dependencies`` (``Requires-Dist`` mixes base dependencies and
    extras, needing marker inspection to separate).
    """
    name_declared = field_declared(msg, "Name")
    name = msg.get("Name", "") if name_declared else ""
    metadata = ProjectMetadata(name=name)
    provenance = metadata.provenance

    if name_declared:
        provenance["name"] = source_label
    if field_declared(msg, "Version"):
        metadata.version = msg.get("Version")
        provenance["version"] = source_label
    if field_declared(msg, "Summary"):
        metadata.description = msg.get("Summary")
        provenance["description"] = source_label
    if field_declared(msg, "Requires-Python"):
        metadata.requires_python = msg.get("Requires-Python")
        provenance["requires_python"] = source_label

    # Spec 2.4+ makes License-Expression/License mutually exclusive, but
    # real files can be non-compliant (hand-edited, buggy tool) -- never
    # assume exclusivity, just prefer License-Expression when both present.
    if field_declared(msg, "License-Expression"):
        metadata.license_name = msg.get("License-Expression")
        provenance["license"] = source_label
    elif field_declared(msg, "License"):
        metadata.license_name = msg.get("License")
        provenance["license"] = source_label

    if field_declared(msg, "Keywords"):
        metadata.keywords = to_str_list(msg.get("Keywords"))
        provenance["keywords"] = source_label

    urls = _parse_installed_urls(msg)
    if urls:
        metadata.urls = urls
        provenance["urls"] = source_label

    return metadata


def read_installed_metadata(
    marker_path: Path, source_label: str, *, quiet: bool = False
) -> ProjectMetadata | None:
    """Read and parse *marker_path* (the winning candidate returned by
    :func:`find_installed_metadata_candidate`) into a
    :class:`~pitloom.core.project.ProjectMetadata`.

    Returns ``None`` on a genuine read failure -- discovery already
    confirmed the file was readable moments earlier, so a failure here is
    a real disruption (the file vanished/became unreadable between calls),
    not an expected absence; logged as a ``WARNING:`` unless *quiet*, never
    raised (installed metadata is always optional enrichment).
    """
    text = _read_marker_text(marker_path)
    if text is None:
        if not quiet:
            log.warning(
                "%s: %s could not be re-read -- skipping installed metadata",
                marker_path.parent,
                marker_path.name,
            )
        return None
    msg = email.message_from_string(text)
    return _parse_installed_metadata(msg, source_label)


def _reconcile_conflict_checked_field(
    merged: ProjectMetadata,
    static: ProjectMetadata,
    installed: ProjectMetadata,
    field_name: str,
    warn_subject: str,
    *,
    quiet: bool,
) -> None:
    """Reconcile one of :data:`_CONFLICT_CHECKED_FIELDS` in place on *merged*.

    *warn_subject* is the pre-formatted ``"<project_dir>: installed
    metadata (<label>)"`` prefix for the disagreement ``WARNING:`` --
    precomputed once by :func:`reconcile_installed_metadata` rather than
    passed as two separate parameters, to stay within this repo's
    max-args ratchet.
    """
    provenance_key = _PROVENANCE_KEY_ALIASES.get(field_name, field_name)
    installed_declared = field_declared(installed.provenance, provenance_key)
    if not installed_declared:
        return
    static_declared = field_declared(static.provenance, provenance_key)
    installed_value = getattr(installed, field_name)
    if not static_declared:
        setattr(merged, field_name, installed_value)
        merged.provenance[provenance_key] = installed.provenance[provenance_key]
        return

    static_value = getattr(static, field_name)
    # static_value can be None even though static_declared is True: every
    # producer of these three fields collapses an explicitly-declared-empty
    # source value to None (`str(x) if x else None` -- `requires-python =
    # ""`, PEP 621's "no constraint" convention matching Poetry's
    # `python = "*"`; likewise an empty/undetected `license`). None is not
    # a valid comparator input -- SpecifierSet(None) and
    # normalize_license_expression(None) both raise instead of comparing
    # -- so compare against the empty string it's semantically equivalent
    # to. The real (possibly-None) static_value is still what's logged and
    # what a future gap-fill would see; only the comparator call and the
    # recorded candidate's ``value`` (typed ``str``, never ``None``) use
    # the normalized form.
    comparable_static_value = static_value if static_value is not None else ""
    comparator = _FIELD_COMPARATORS[field_name]
    if comparator(comparable_static_value, installed_value):
        return

    static_source = static.provenance[provenance_key]
    installed_source = installed.provenance[provenance_key]
    candidates: list[ConflictCandidate] = [
        {"value": comparable_static_value, "role": "declared", "source": static_source},
        {"value": installed_value, "role": "declared", "source": installed_source},
    ]
    # Keyed by provenance_key, not field_name, so license_name's conflict
    # lands under "license" -- matching deps_license.py's own declared-
    # vs-concluded conflict field label for the same underlying concept,
    # rather than a second, inconsistent "license_name" label for what a
    # consumer would otherwise read as two different fields.
    merged.field_conflicts[provenance_key] = candidates
    if not quiet:
        log.warning(
            "%s disagrees on %s (declared %r, installed %r) -- keeping declared",
            warn_subject,
            field_name,
            static_value,
            installed_value,
        )


def _reconcile_gap_fill_field(
    merged: ProjectMetadata,
    static: ProjectMetadata,
    installed: ProjectMetadata,
    field_name: str,
) -> None:
    """Reconcile one of :data:`_GAP_FILL_ONLY_FIELDS` in place on *merged*."""
    provenance_key = _PROVENANCE_KEY_ALIASES.get(field_name, field_name)
    if field_declared(static.provenance, provenance_key):
        return
    if not field_declared(installed.provenance, provenance_key):
        return
    setattr(merged, field_name, getattr(installed, field_name))
    merged.provenance[provenance_key] = installed.provenance[provenance_key]


def reconcile_installed_metadata(
    static: ProjectMetadata,
    installed: ProjectMetadata,
    installed_label: str,
    project_dir: Path,
    *,
    quiet: bool = False,
) -> ProjectMetadata:
    """Fold *installed* (parsed from an in-tree ``.egg-info``/``.dist-info``)
    into *static* (``pyproject.toml``/``setup.cfg``/``setup.py``). *static*
    stays authoritative on any genuine disagreement; *installed* only fills
    gaps *static* left undeclared. A real disagreement is recorded in the
    result's ``field_conflicts`` and logged as a ``WARNING:``, never
    silently substituted.

    *project_dir* identifies the project in the ``WARNING:`` line (it is
    not part of the reconciliation logic itself) -- it is not literally
    part of the plan's own reconciliation pseudocode, but the plan's
    specified wording (``WARNING: %s: installed metadata ...``) needs a
    project label to fill that first ``%s``, so this signature adds it as
    an explicit parameter rather than reaching for a global.

    Only :data:`_CONFLICT_CHECKED_FIELDS` and :data:`_GAP_FILL_ONLY_FIELDS`
    participate -- iterated in :func:`dataclasses.fields`'s stable
    declaration order (never a ``set``'s iteration order, which is not
    guaranteed stable across processes) so the result -- including
    ``field_conflicts`` insertion order -- is deterministic. Every other
    field (``name``, ``provenance``, ``files``, ``locked_dependencies``,
    ``locked_dependency_hashes``, ``license_files``, ``authors``,
    ``dependencies``, ``readme``, ``field_conflicts`` itself) is left
    untouched: a newly-added :class:`ProjectMetadata` field must not
    silently start participating here with no comparator/provenance
    thought through for it.
    """
    # replace_with_fresh_containers() (never a bare dataclasses.replace(),
    # which would alias every container field -- including provenance and
    # field_conflicts -- to *static*'s own object) gives every dict/list
    # field a fresh shallow copy up front, since this function writes into
    # both `merged.provenance[key] = ...` and
    # `merged.field_conflicts[field] = ...` below and neither write may
    # leak back into the caller's own *static* object (see
    # working-docs/design/installed-dist-info-source.md).
    merged = static.replace_with_fresh_containers()
    warn_subject = f"{project_dir}: installed metadata ({installed_label})"
    for f in dataclasses.fields(ProjectMetadata):
        if f.name in _CONFLICT_CHECKED_FIELDS:
            _reconcile_conflict_checked_field(
                merged, static, installed, f.name, warn_subject, quiet=quiet
            )
        elif f.name in _GAP_FILL_ONLY_FIELDS:
            _reconcile_gap_fill_field(merged, static, installed, f.name)
    return merged


__all__ = [
    "find_installed_metadata_candidate",
    "read_installed_metadata",
    "reconcile_installed_metadata",
]
