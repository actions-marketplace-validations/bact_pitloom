# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI fragment command."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import __main__
from pitloom.assemble.spdx3.fragments import (
    _missing_fragment_message,
)
from pitloom.cli.commands.fragment import _run_fragment_command

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
VALID_FRAGMENT = FIXTURE_DIR / "fragments" / "dataset-fragment.spdx3.json"
CONFLICTING_FRAGMENT = FIXTURE_DIR / "fragments" / "training-run-fragment.spdx3.json"

_MINIMAL_PROJECT = '[project]\nname = "smoke"\nversion = "0.1.0"\n'


def _write_pyproject(tmp_path: Path, fragment_toml: str) -> None:
    (tmp_path / "pyproject.toml").write_text(_MINIMAL_PROJECT + fragment_toml)


@pytest.mark.pypi_network
def test_fragment_validate_command_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A valid SPDX 3 document exits 0 and reports success on stdout.

    Needs a live socket: spdx3-validate fetches its JSON Schema from
    schema_url rather than shipping it bundled.
    """
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "validate", str(VALID_FRAGMENT)]
    )
    result = __main__.main()
    assert result == 0

    captured = capsys.readouterr()
    assert "pitloom fragment validate: 1 document(s) valid" in captured.out


def test_fragment_validate_command_invalid_document(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An invalid SPDX 3 document exits 1 and prints each finding as its
    own ERROR: line."""
    doc_path = tmp_path / "bad.spdx3.json"
    doc_path.write_text('{"@graph": []}', encoding="utf-8")

    monkeypatch.setattr("sys.argv", ["loom", "fragment", "validate", str(doc_path)])
    result = __main__.main()
    assert result == 1

    captured = capsys.readouterr()
    for line in captured.err.splitlines():
        assert line.startswith("ERROR: ")


@pytest.mark.pypi_network
def test_fragment_validate_command_multiline_shacl_error_every_line_tagged(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A SHACL violation's message embeds newlines (Severity/Source
    Shape/Focus Node breakdown); every resulting stderr line must carry
    its own ERROR: tag, not just the finding's first line.

    Needs a live socket: spdx3-validate fetches its JSON Schema from
    schema_url rather than shipping it bundled.
    """
    monkeypatch.setattr(
        "sys.argv",
        [
            "loom",
            "fragment",
            "validate",
            str(VALID_FRAGMENT),
            str(CONFLICTING_FRAGMENT),
        ],
    )
    result = __main__.main()
    assert result == 1

    captured = capsys.readouterr()
    lines = captured.err.splitlines()
    assert len(lines) > 1  # a genuine multi-line SHACL violation
    for line in lines:
        assert line.startswith("ERROR: ")


def test_fragment_cli_invalid_command() -> None:
    # argparse catches this normally; test `_run_fragment_command` directly
    # for the fallback branch (mirrors test_cli_ids.py's equivalent check).
    args = argparse.Namespace(fragment_command="invalid")
    result = _run_fragment_command(args)
    assert result == 1


def test_fragment_validate_command_directory_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A directory PATH is rejected with a clear ERROR:, not an opaque
    IsADirectoryError from deep inside spdx3-validate."""
    directory = tmp_path / "somedir"
    directory.mkdir()

    monkeypatch.setattr("sys.argv", ["loom", "fragment", "validate", str(directory)])
    result = __main__.main()
    assert result == 1

    captured = capsys.readouterr()
    assert f"ERROR: directory: {directory}" in captured.err


def test_fragment_validate_command_file_not_found(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test fragment validate fails gracefully when a path is missing."""
    missing_path = tmp_path / "missing.spdx3.json"

    monkeypatch.setattr("sys.argv", ["loom", "fragment", "validate", str(missing_path)])
    result = __main__.main()
    assert result == 1

    captured = capsys.readouterr()
    assert f"ERROR: file not found: {missing_path}" in captured.err


def test_fragment_validate_command_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test fragment validate reports a clear ERROR when the optional
    'spdx3-validate' dependency isn't installed."""
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "validate", str(VALID_FRAGMENT)]
    )
    with patch.dict("sys.modules", {"spdx3_validate": None}):
        result = __main__.main()
    assert result == 1

    captured = capsys.readouterr()
    assert (
        "ERROR: the 'spdx3-validate' package is required for SPDX 3 "
        "validation" in captured.err
    )
    assert 'pip install "pitloom[validate]"' in captured.err


def test_fragment_validate_command_missing_dependency_and_bad_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Both problems are reported in one run -- a missing optional
    dependency doesn't hide an unrelated bad-path error, or vice versa."""
    missing_path = tmp_path / "missing.spdx3.json"

    monkeypatch.setattr("sys.argv", ["loom", "fragment", "validate", str(missing_path)])
    with patch.dict("sys.modules", {"spdx3_validate": None}):
        result = __main__.main()
    assert result == 1

    captured = capsys.readouterr()
    assert "ERROR: the 'spdx3-validate' package is required" in captured.err
    assert f"ERROR: file not found: {missing_path}" in captured.err


@pytest.mark.pypi_network
def test_fragment_validate_command_no_merge_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--no-merge is passed through as check_merged=False.

    Needs a live socket: spdx3-validate fetches its JSON Schema from
    schema_url rather than shipping it bundled.
    """
    monkeypatch.setattr(
        "sys.argv",
        ["loom", "fragment", "validate", str(VALID_FRAGMENT), "--no-merge"],
    )
    result = __main__.main()
    assert result == 0

    captured = capsys.readouterr()
    assert "pitloom fragment validate: 1 document(s) valid" in captured.out


# ---------------------------------------------------------------------------
# fragment list
# ---------------------------------------------------------------------------


def test_fragment_list_no_fragments_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_pyproject(tmp_path, "")
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 0
    assert "pitloom fragment list: no fragments configured" in capsys.readouterr().out


def test_fragment_list_plain_string_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A plain-string files entry (no role/sha256/etc.) shows ROLE=- and
    SHA256=- -- the "backward-compatible" shorthand form."""
    (tmp_path / "a.spdx3.json").write_text('{"@graph": [{"x": 1}]}')
    _write_pyproject(tmp_path, '\n[tool.pitloom.fragment]\nfiles = ["a.spdx3.json"]\n')
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 0
    out = capsys.readouterr().out
    assert (
        "PATH=a.spdx3.json ROLE=- REQUIRED=false EXISTS=true ELEMENTS=1 SHA256=-" in out
    )


def test_fragment_list_table_entry_sha256_match(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A full table entry with role and a correct sha256 shows ROLE=ai_model
    and SHA256=match."""
    import hashlib

    content = '{"@graph": [{"x": 1}, {"y": 2}]}'
    (tmp_path / "model.spdx3.json").write_text(content)
    digest = hashlib.sha256(content.encode()).hexdigest()
    _write_pyproject(
        tmp_path,
        "\n[tool.pitloom.fragment]\nfiles = ["
        f'{{ path = "model.spdx3.json", role = "ai_model", sha256 = "{digest}" }}'
        "]\n",
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 0
    out = capsys.readouterr().out
    assert "ROLE=ai_model" in out
    assert "SHA256=match" in out
    assert "ELEMENTS=2" in out


def test_fragment_list_sha256_mismatch_warns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    (tmp_path / "model.spdx3.json").write_text('{"@graph": []}')
    _write_pyproject(
        tmp_path,
        '\n[tool.pitloom.fragment]\nfiles = [{ path = "model.spdx3.json", '
        'sha256 = "deadbeef" }]\n',
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    with caplog.at_level("WARNING", logger="pitloom.cli.commands.fragment"):
        result = __main__.main()
    assert result == 0
    assert any(
        "SHA-256 mismatch" in r.message and "deadbeef" in r.message
        for r in caplog.records
    )


def test_fragment_list_sha256_configured_but_file_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """sha256 configured but the file doesn't exist -> SHA256=unknown, the
    missing-file WARNING fires, not the mismatch one."""
    _write_pyproject(
        tmp_path,
        '\n[tool.pitloom.fragment]\nfiles = [{ path = "gone.spdx3.json", '
        'sha256 = "deadbeef" }]\n',
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    with caplog.at_level("WARNING"):
        result = __main__.main()
    assert result == 0
    out = capsys.readouterr().out
    assert "SHA256=unknown" in out
    assert "EXISTS=false" in out
    assert not any("mismatch" in r.message for r in caplog.records)
    assert any("not found" in r.message for r in caplog.records)


def test_fragment_list_required_missing_exits_1(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    _write_pyproject(
        tmp_path,
        '\n[tool.pitloom.fragment]\nfiles = [{ path = "gone.spdx3.json", '
        "required = true }]\n",
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    expected_warning = _missing_fragment_message(
        tmp_path / "gone.spdx3.json", required=True
    )
    with caplog.at_level("WARNING"):
        result = __main__.main()
    assert result == 1
    out = capsys.readouterr().out
    assert "EXISTS=false" in out
    assert any(r.message == expected_warning for r in caplog.records)


def test_fragment_list_optional_missing_exits_0(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _write_pyproject(
        tmp_path, '\n[tool.pitloom.fragment]\nfiles = ["gone.spdx3.json"]\n'
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    expected_warning = _missing_fragment_message(
        tmp_path / "gone.spdx3.json", required=False
    )
    with caplog.at_level("WARNING"):
        result = __main__.main()
    assert result == 0
    assert any(r.message == expected_warning for r in caplog.records)
    assert "merge will fail" not in expected_warning


def test_fragment_list_unparseable_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    frag_path = tmp_path / "broken.spdx3.json"
    frag_path.write_text("not valid json{{{")
    _write_pyproject(
        tmp_path, '\n[tool.pitloom.fragment]\nfiles = ["broken.spdx3.json"]\n'
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    with caplog.at_level("WARNING"):
        result = __main__.main()
    assert result == 0
    assert "ELEMENTS=-" in capsys.readouterr().out
    assert any(
        r.message.startswith(f"Failed to read SBOM fragment {frag_path}: ")
        for r in caplog.records
    )


def test_fragment_list_valid_json_no_graph_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Valid JSON with no @graph key is a real 0-element count, not an
    unparseable-file case."""
    (tmp_path / "empty.spdx3.json").write_text('{"foo": "bar"}')
    _write_pyproject(
        tmp_path, '\n[tool.pitloom.fragment]\nfiles = ["empty.spdx3.json"]\n'
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 0
    assert "ELEMENTS=0" in capsys.readouterr().out


def test_fragment_list_project_dir_no_pyproject(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 1
    assert "ERROR: fragment list failed:" in capsys.readouterr().err


def test_fragment_list_two_fragments_both_reported(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One missing (non-required) and one with a good sha256 -- both
    problems are reported in the same run's output, loop doesn't
    short-circuit."""
    import hashlib

    content = '{"@graph": [{"x": 1}]}'
    (tmp_path / "good.spdx3.json").write_text(content)
    digest = hashlib.sha256(content.encode()).hexdigest()
    _write_pyproject(
        tmp_path,
        "\n[tool.pitloom.fragment]\nfiles = [\n"
        '  "missing.spdx3.json",\n'
        f'  {{ path = "good.spdx3.json", sha256 = "{digest}" }},\n'
        "]\n",
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 0
    out = capsys.readouterr().out
    assert "PATH=missing.spdx3.json" in out
    assert "EXISTS=false" in out
    assert "PATH=good.spdx3.json" in out
    assert "SHA256=match" in out


def test_fragment_list_modified_field_pinned(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """MODIFIED reflects the fragment file's actual mtime, pinned via
    os.utime for a deterministic assertion."""
    frag_path = tmp_path / "a.spdx3.json"
    frag_path.write_text('{"@graph": []}')
    fixed_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    os.utime(frag_path, (fixed_ts, fixed_ts))
    _write_pyproject(tmp_path, '\n[tool.pitloom.fragment]\nfiles = ["a.spdx3.json"]\n')
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    result = __main__.main()
    assert result == 0
    assert "MODIFIED=2026-01-01T12:00:00+00:00" in capsys.readouterr().out
