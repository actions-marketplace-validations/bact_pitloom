# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.inert_options`: the table itself, and the
user-facing copy of it in ``docs/cli.md``.

See also: :mod:`tests.cli.test_cli_option_reach` (every CLI option reaches
the library or warns, end to end).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest

from pitloom.cli.parser import _build_parser
from pitloom.core import inert_options
from pitloom.core.inert_options import INERT, PARAM_TO_FLAG, settle_inert

_CLI_DOC = Path(__file__).resolve().parents[2] / "docs" / "cli.md"
_SECTION = "### Options with no effect"

#: docs/cli.md row label -> target kind.
_ROW_KINDS = {
    "project directory": inert_options.PROJECT,
    "sdist archive": inert_options.SDIST,
    "wheel": inert_options.WHEEL,
    "installed environment": inert_options.ENV,
    "local model file": inert_options.MODEL_FILE,
    "Hugging Face model": inert_options.HF,
    "enrich --project-dir": inert_options.ENRICH,
    "enrich without --project-dir": inert_options.ENRICH_STANDALONE,
    "embed-wheel --project-dir": inert_options.EMBED_PROJECT,
    "embed-wheel without --project-dir": inert_options.EMBED_STANDALONE,
    "embed-wheel --sbom": inert_options.EMBED_SBOM,
    # The same embedded SBOM, and warnings, as embed-wheel without a project.
    "wheel --embed": inert_options.EMBED_STANDALONE,
}


def _documented_rows() -> dict[str, list[str]]:
    """``docs/cli.md``'s "Options with no effect" table: row label -> the
    options it lists, in order."""
    text = _CLI_DOC.read_text(encoding="utf-8")
    section = text[text.index(_SECTION) :]
    rows: dict[str, list[str]] = {}
    for line in section.splitlines()[1:]:
        if line.startswith("#"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 2 or cells[0] in ("Target", "") or set(cells[0]) <= {"-"}:
            continue
        rows[cells[0].strip("`")] = re.findall(r"`([^`]+)`", cells[1])
    return rows


def test_docs_table_matches_inert() -> None:
    """The user docs list exactly the options each target warns about, in
    flag-table order (the order one settle warns in) -- a row added to
    INERT without the docs (or the reverse) fails here."""
    documented = _documented_rows()
    assert set(documented) == set(_ROW_KINDS)
    for label, kind in _ROW_KINDS.items():
        expected = [
            spelling.split("/", maxsplit=1)[0]
            for param, spelling in PARAM_TO_FLAG.items()
            if param in INERT[kind]
        ]
        assert documented[label] == expected, label


def test_every_kind_has_a_docs_row() -> None:
    kinds = {
        value
        for name, value in vars(inert_options).items()
        if name.isupper() and isinstance(value, str) and value in INERT
    }
    assert kinds == set(INERT) == set(_ROW_KINDS.values())


def _subcommand(name: str) -> argparse.ArgumentParser:
    """The real parser of subcommand *name*."""
    parser = _build_parser()
    # pylint: disable-next=protected-access
    for action in parser._actions:
        # pylint: disable-next=protected-access
        if isinstance(action, argparse._SubParsersAction):
            parser_: argparse.ArgumentParser = action.choices[name]
            return parser_
    raise LookupError(name)


def test_every_warned_flag_exists_on_the_cli() -> None:
    """A warning names a real option; a glob names at least one."""
    # pylint: disable-next=protected-access
    actions = _subcommand("project")._actions
    options = {option for action in actions for option in action.option_strings}
    for spelling in PARAM_TO_FLAG.values():
        for part in spelling.split("/"):
            pattern = re.compile(re.escape(part).replace(r"\*", ".*") + "$")
            assert any(pattern.match(option) for option in options), part


def test_every_inert_param_has_a_flag_spelling() -> None:
    for row in INERT.values():
        assert set(row) <= set(PARAM_TO_FLAG)


@pytest.mark.parametrize("value", [False, 0, ""])
def test_a_falsy_given_value_still_warns(
    caplog: pytest.LogCaptureFixture, value: object
) -> None:
    """``None`` alone means "not given"; ``False``/``0`` are choices."""
    with caplog.at_level("WARNING"):
        dropped = settle_inert(inert_options.WHEEL, "w", {"enrich": value})
    assert dropped == {"enrich"}
    assert len(caplog.records) == 1


def test_none_is_not_given(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        assert settle_inert(inert_options.WHEEL, "w", {"enrich": None}) == set()
    assert not caplog.records
