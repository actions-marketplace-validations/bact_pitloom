# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``content_type_method`` decides whether the remote authors file is fetched.

A dependency whose author is "and others (see AUTHORS.txt)" has its authors
file fetched from the repository host, unless ``content_type_method`` is
``extension`` (stdlib-only, no detector needing the content). The method
reaches that decision only through the assembler, so a surface that drops it
fetches anyway -- ``embed-wheel --project-dir`` did.

No real network access: ``urllib.request.urlopen`` is replaced and records
every request. See :mod:`tests.assemble.test_embed_build_seam` for the
argument-level counterpart, and :mod:`tests.assemble.embed_surfaces_shared`
for the surfaces run here.
"""

from __future__ import annotations

import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest

from pitloom.assemble.spdx3 import deps_originator
from tests.assemble.conftest import _FakeMetadata
from tests.assemble.embed_surfaces_shared import RUNNERS, config_toml

_AUTHORS_HOST = "raw.githubusercontent.com"
_AUTHORS_URL = f"https://{_AUTHORS_HOST}/example/fakedep/HEAD/AUTHORS.txt"


class _Response:
    """A minimal ``urlopen()`` result."""

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self, _size: int = -1) -> bytes:
        return b"Jane Doe\n"


# The memoised fetch has no public reset.
# pylint: disable=protected-access
@pytest.fixture(autouse=True)
def _fresh_authors_cache() -> Iterator[None]:
    """The fetch is memoised per process: a hit from an earlier test would
    hide a fetch that should have happened."""
    deps_originator._resolve_remote_authors_file.cache_clear()
    yield
    deps_originator._resolve_remote_authors_file.cache_clear()


@pytest.fixture(name="requests")
def _requests_fixture(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every URL opened; serve the authors host, refuse the rest
    (PyPI's fallback lookup fails as it would offline)."""
    urls: list[str] = []

    def _urlopen(request: Any, *_args: Any, **_kwargs: Any) -> _Response:
        url = getattr(request, "full_url", str(request))
        urls.append(url)
        if _AUTHORS_HOST not in url:
            raise URLError("blocked in test")
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    return urls


@pytest.fixture(autouse=True)
def _installed_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    """``fakedep`` 1.0 is "installed", authored by "and others"."""
    meta = _FakeMetadata(
        {"Version": "1.0", "Author": "and others (see AUTHORS.txt)"},
        project_urls=["Repository, https://github.com/example/fakedep"],
    )
    monkeypatch.setattr(
        "pitloom.assemble.spdx3.deps_installed.get_pkg_metadata", lambda _name: meta
    )


_CASES = [
    # (config method, per-run override, expected authors-file fetches)
    # "auto" is the control: it proves the fixture reaches the fetch at all.
    pytest.param((None, None, 1), id="default-fetches"),
    pytest.param(("extension", None, 0), id="config-extension"),
    pytest.param((None, "extension", 0), id="override-extension"),
    pytest.param(("auto", "extension", 0), id="override-extension-beats-auto"),
    pytest.param(("extension", "auto", 1), id="override-auto-beats-extension"),
]


@pytest.mark.parametrize("surface", sorted(RUNNERS))
@pytest.mark.parametrize("case", _CASES)
def test_authors_file_fetch_follows_content_type_method(
    surface: str,
    case: tuple[str | None, str | None, int],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    requests: list[str],
) -> None:
    config, override, expected = case
    RUNNERS[surface](
        tmp_path, monkeypatch, config_toml(config, None), override, None, offline=False
    )
    fetched = [url for url in requests if _AUTHORS_HOST in url]
    assert fetched == [_AUTHORS_URL] * expected
