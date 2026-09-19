# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.extract._json_io.load_json_bytes`.

See also: :mod:`tests.extract.lock.test_common` and
:mod:`tests.extract.test_extract_utils` for this helper's real callers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom.extract._json_io import load_json_bytes


def test_load_json_bytes_returns_raw_and_parsed(tmp_path: Path) -> None:
    path = tmp_path / "doc.json"
    content = b'{"a": 1}'
    path.write_bytes(content)

    raw, parsed = load_json_bytes(path)

    assert raw == content
    assert parsed == {"a": 1}


def test_load_json_bytes_tolerates_utf8_bom(tmp_path: Path) -> None:
    """A leading UTF-8 BOM must not fail the parse -- json.loads(bytes)
    auto-strips it, unlike json.loads(str) after an explicit .decode()."""
    path = tmp_path / "bom.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'{"a": 1}')

    raw, parsed = load_json_bytes(path)

    assert raw.startswith(b"\xef\xbb\xbf")
    assert parsed == {"a": 1}


def test_load_json_bytes_propagates_json_decode_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_bytes(b"not valid json{{{")

    with pytest.raises(json.JSONDecodeError):
        load_json_bytes(path)


def test_load_json_bytes_propagates_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_json_bytes(tmp_path / "missing.json")
