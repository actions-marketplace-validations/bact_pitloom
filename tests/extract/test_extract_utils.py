# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract._extract_utils`."""

from __future__ import annotations

import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pitloom.extract._extract_utils import (
    fetch_json,
    filename_from_url,
    sanitize_provenance_text,
    sanitize_url_credentials,
)


def test_sanitize_url_credentials_redacts_user_and_password() -> None:
    assert (
        sanitize_url_credentials("https://user:password123@example.com/repo.git")
        == "https://***:***@example.com/repo.git"
    )
    assert (
        sanitize_url_credentials("git+ssh://token@gitlab.com/repo.git")
        == "git+ssh://***:***@gitlab.com/repo.git"
    )
    assert (
        sanitize_url_credentials("Error fetching https://token:secret@pypi.org/simple")
        == "Error fetching https://***:***@pypi.org/simple"
    )
    assert (
        sanitize_url_credentials("https://example.com/plain/url")
        == "https://example.com/plain/url"
    )


def test_filename_from_url_extracts_basename() -> None:
    assert (
        filename_from_url("https://example.com/packages/foo-1.0-py3-none-any.whl")
        == "foo-1.0-py3-none-any.whl"
    )
    assert (
        filename_from_url(
            "https://example.com/pkg-1.0.whl?key=val&other=1#sha256=abcdef"
        )
        == "pkg-1.0.whl"
    )
    assert filename_from_url("https://example.com/") is None
    assert filename_from_url("https://example.com") is None


def test_filename_from_url_windows_path() -> None:
    assert (
        filename_from_url("file:///C:/Users/dist/pkg-1.0-py3-none-any.whl")
        == "pkg-1.0-py3-none-any.whl"
    )
    assert filename_from_url("https://example.com/a\\b\\pkg-1.0.whl") == "pkg-1.0.whl"
    assert filename_from_url("https://example.com/dir\\") is None


def test_sanitize_provenance_text() -> None:
    assert sanitize_provenance_text("foo|bar|baz") == "foo/bar/baz"
    assert sanitize_provenance_text("clean text") == "clean text"


def test_fetch_json_local_file(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text('{"project": "pitloom"}', encoding="utf-8")
    assert fetch_json(path) == {"project": "pitloom"}


def test_fetch_json_url_success() -> None:
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"status": "ok"}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch.object(urllib.request, "urlopen", return_value=mock_resp):
        res = fetch_json("https://example.com/api.json")
    assert res == {"status": "ok"}


def test_fetch_json_url_exceeds_max_bytes() -> None:
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"0123456789extra"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch.object(urllib.request, "urlopen", return_value=mock_resp):
        with pytest.raises(ValueError, match="exceeds maximum limit"):
            fetch_json("https://example.com/large.json", max_bytes=10)


def test_fetch_json_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        fetch_json(path)


def test_fetch_json_non_dict(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a JSON object"):
        fetch_json(path)


def test_fetch_json_read_error(tmp_path: Path) -> None:
    path = tmp_path / "nonexistent.json"
    with pytest.raises(ValueError, match="Cannot read source"):
        fetch_json(path)
