# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract._extract_utils`."""

from __future__ import annotations

from pitloom.extract._extract_utils import (
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
