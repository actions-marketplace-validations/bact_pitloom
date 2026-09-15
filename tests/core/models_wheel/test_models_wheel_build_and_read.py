# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the generic, backend-agnostic build-and-read file discovery
mechanism (:mod:`pitloom.core._models_wheel_build_and_read`).

See also: tests/core/models_wheel/test_models_wheel_dispatch.py for the
facade-level dispatch tests that exercise this mechanism through
``get_wheel_files()``/``--allow-build``.
"""

import dataclasses
import logging
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core._models_wheel_build_and_read import (
    _run_pep517_build_wheel,
    build_and_read_wheel,
)
from pitloom.core._models_wheel_types import is_dist_info_path


def _write_fake_wheel(
    wheel_path: Path, entries: dict[str, bytes], *, dist_info: bool = True
) -> None:
    """Write a small, hand-built ``.whl`` zip at *wheel_path* with
    *entries* (distribution_path -> content), plus an optional
    ``.dist-info/METADATA`` entry (present by default, since a real
    wheel always has one)."""
    with zipfile.ZipFile(wheel_path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
        if dist_info:
            zf.writestr("pkg-1.0.dist-info/METADATA", b"Metadata-Version: 2.1\n")


@dataclasses.dataclass
class _FakeBuildState:
    """Mutable state a test can adjust before calling
    ``build_and_read_wheel()``, backing the ``fake_build`` fixture."""

    entries: dict[str, bytes] = dataclasses.field(
        default_factory=lambda: {"pkg/__init__.py": b"print('hi')\n"}
    )
    dist_info: bool = True
    isolated_seen: list[bool] = dataclasses.field(default_factory=list)


@pytest.fixture
def fake_build(monkeypatch: pytest.MonkeyPatch) -> _FakeBuildState:
    """Monkeypatch ``_run_pep517_build_wheel`` to write a fake wheel
    instead of actually invoking PyPA build -- keeps these tests fast,
    offline, and deterministic. Returns state the test can mutate
    (``entries``/``dist_info``) before calling ``build_and_read_wheel()``."""
    state = _FakeBuildState()

    def _fake_run(project_dir: Path, output_dir: Path, *, isolated: bool) -> Path:
        state.isolated_seen.append(isolated)
        wheel_path = output_dir / "pkg-1.0-py3-none-any.whl"
        _write_fake_wheel(wheel_path, state.entries, dist_info=state.dist_info)
        return wheel_path

    monkeypatch.setattr(
        "pitloom.core._models_wheel_build_and_read._run_pep517_build_wheel",
        _fake_run,
    )
    return state


def test_build_and_read_wheel_extracts_real_non_dist_info_files(
    fake_build: _FakeBuildState, tmp_path: Path
) -> None:
    """A successful build's non-``.dist-info`` entries come back as
    ``IncludedFile`` pairs pointing at real, readable, on-disk files."""
    fake_build.entries = {
        "pkg/__init__.py": b"",
        "pkg/sub/mod.py": b"x = 1\n",
    }

    result = build_and_read_wheel(tmp_path)

    assert result is not None
    files, cleanup = result
    distribution_paths = {f.distribution_path for f in files}
    assert distribution_paths == {"pkg/__init__.py", "pkg/sub/mod.py"}
    for included_file in files:
        assert Path(included_file.path).is_file()
        assert not is_dist_info_path(included_file.distribution_path)
    cleanup()


def test_build_and_read_wheel_excludes_dist_info(
    fake_build: _FakeBuildState, tmp_path: Path
) -> None:
    """``.dist-info/*`` entries -- genuinely present in the real,
    already-built wheel -- must never appear in the returned file list:
    every other backend's ``IncludedFile`` list is pre-build source
    files only."""
    result = build_and_read_wheel(tmp_path)

    assert result is not None
    files, cleanup = result
    assert not any(is_dist_info_path(f.distribution_path) for f in files)
    cleanup()


def test_build_and_read_wheel_cleanup_removes_temp_dir(
    fake_build: _FakeBuildState, tmp_path: Path
) -> None:
    """The returned cleanup callback must actually delete the extraction
    temp directory -- callers rely on this to avoid leaking a temp dir
    per invocation."""
    result = build_and_read_wheel(tmp_path)

    assert result is not None
    files, cleanup = result
    extract_dir = Path(files[0].path).parent
    assert extract_dir.exists()

    cleanup()

    assert not extract_dir.exists()


def test_build_and_read_wheel_returns_none_on_build_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A build failure (network unavailable, backend not installable,
    the build script itself raising) must degrade to ``None`` plus a
    ``WARNING:``, never propagate -- same "None means fall back"
    contract as every static discoverer."""

    def _raise(project_dir: Path, output_dir: Path, *, isolated: bool) -> Path:
        raise RuntimeError("simulated build backend failure")

    monkeypatch.setattr(
        "pitloom.core._models_wheel_build_and_read._run_pep517_build_wheel", _raise
    )

    with caplog.at_level(logging.WARNING):
        result = build_and_read_wheel(tmp_path)

    assert result is None
    assert "build-and-read discovery failed" in caplog.text


def test_build_and_read_wheel_never_leaks_extract_dir_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: the extraction temp directory allocated up front must
    be removed even when the build itself fails -- only the success path
    hands cleanup responsibility to the caller."""
    created_dirs: list[Path] = []
    real_mkdtemp = tempfile.mkdtemp

    def _tracking_mkdtemp(prefix: str | None = None) -> str:
        path = real_mkdtemp(prefix=prefix)
        # tempfile.TemporaryDirectory() (used for the build-output dir)
        # also calls mkdtemp() internally -- only track the *extraction*
        # dir this test cares about, by its distinct prefix.
        if prefix is not None and prefix.startswith("pitloom-build-and-read-"):
            created_dirs.append(Path(path))
        return path

    monkeypatch.setattr(
        "pitloom.core._models_wheel_build_and_read.tempfile.mkdtemp",
        _tracking_mkdtemp,
    )

    def _raise(project_dir: Path, output_dir: Path, *, isolated: bool) -> Path:
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(
        "pitloom.core._models_wheel_build_and_read._run_pep517_build_wheel", _raise
    )

    result = build_and_read_wheel(tmp_path)

    assert result is None
    assert len(created_dirs) == 1
    assert not created_dirs[0].exists()


def test_build_and_read_wheel_returns_none_on_zero_non_dist_info_files(
    fake_build: _FakeBuildState, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A build that produces only ``.dist-info/*`` (zero real files) must
    be treated as a discovery failure, not an authoritative empty
    result -- per CLAUDE.md's None-vs-empty rule, this is a build
    failure, not a legitimately-empty wheel."""
    fake_build.entries = {}

    with caplog.at_level(logging.WARNING):
        result = build_and_read_wheel(tmp_path)

    assert result is None
    assert "no non-.dist-info files" in caplog.text


def test_build_and_read_wheel_isolated_true_by_default(
    fake_build: _FakeBuildState, tmp_path: Path
) -> None:
    """``isolated`` defaults to ``True`` and is forwarded unchanged to
    the actual build invocation."""
    result = build_and_read_wheel(tmp_path)

    assert result is not None
    files, cleanup = result
    assert fake_build.isolated_seen == [True]
    cleanup()


def test_build_and_read_wheel_isolated_false_forwarded(
    fake_build: _FakeBuildState, tmp_path: Path
) -> None:
    """``isolated=False`` (from ``--no-build-isolation``) is forwarded
    unchanged, never silently coerced back to ``True``."""
    result = build_and_read_wheel(tmp_path, isolated=False)

    assert result is not None
    files, cleanup = result
    assert fake_build.isolated_seen == [False]
    cleanup()


def test_run_pep517_build_wheel_isolated_uses_isolated_env(tmp_path: Path) -> None:
    """isolated=True must go through DefaultIsolatedEnv/from_isolated_env
    and install both build_system_requires and get_requires_for_build --
    never call the plain, non-isolated ProjectBuilder constructor."""
    fake_builder = mock.Mock()
    fake_builder.build_system_requires = {"setuptools"}
    fake_builder.get_requires_for_build.return_value = set()
    fake_builder.build.return_value = "pkg-1.0-py3-none-any.whl"
    fake_env = mock.MagicMock()
    fake_env.__enter__.return_value = fake_env

    with (
        mock.patch("build.ProjectBuilder") as mock_project_builder,
        mock.patch("build.env.DefaultIsolatedEnv", return_value=fake_env),
    ):
        mock_project_builder.from_isolated_env.return_value = fake_builder

        result = _run_pep517_build_wheel(tmp_path, tmp_path, isolated=True)

    mock_project_builder.from_isolated_env.assert_called_once_with(fake_env, tmp_path)
    mock_project_builder.assert_not_called()
    fake_env.install.assert_any_call({"setuptools"})
    fake_builder.build.assert_called_once_with("wheel", str(tmp_path))
    assert result == tmp_path / "pkg-1.0-py3-none-any.whl"


def test_run_pep517_build_wheel_no_isolation_uses_plain_builder(
    tmp_path: Path,
) -> None:
    """isolated=False must call the plain ProjectBuilder constructor
    directly -- never create an isolated env at all (no venv, no
    network)."""
    fake_builder = mock.Mock()
    fake_builder.build.return_value = "pkg-1.0-py3-none-any.whl"

    with (
        mock.patch("build.ProjectBuilder", return_value=fake_builder) as mock_pb,
        mock.patch("build.env.DefaultIsolatedEnv") as mock_isolated_env,
    ):
        result = _run_pep517_build_wheel(tmp_path, tmp_path, isolated=False)

    mock_pb.assert_called_once_with(tmp_path)
    mock_isolated_env.assert_not_called()
    fake_builder.build.assert_called_once_with("wheel", str(tmp_path))
    assert result == tmp_path / "pkg-1.0-py3-none-any.whl"


def test_extract_wheel_to_included_files_skips_directory_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An explicit ZIP directory entry (``info.is_dir()``) must never
    produce an ``IncludedFile`` -- only real file entries do."""

    def _fake_run_with_dir_entry(
        project_dir: Path, output_dir: Path, *, isolated: bool
    ) -> Path:
        wheel_path = output_dir / "pkg-1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            zf.writestr(zipfile.ZipInfo("pkg/"), "")  # directory entry
            zf.writestr("pkg/__init__.py", b"")
            zf.writestr("pkg-1.0.dist-info/METADATA", b"Metadata-Version: 2.1\n")
        return wheel_path

    monkeypatch.setattr(
        "pitloom.core._models_wheel_build_and_read._run_pep517_build_wheel",
        _fake_run_with_dir_entry,
    )

    result = build_and_read_wheel(tmp_path)

    assert result is not None
    files, cleanup = result
    assert {f.distribution_path for f in files} == {"pkg/__init__.py"}
    cleanup()


@pytest.mark.parametrize(
    ("distribution_path", "expected"),
    [
        ("pkg-1.0.dist-info/METADATA", True),
        ("pkg-1.0.dist-info/RECORD", True),
        ("pkg/dist-info/x.py", False),
        ("pkg-1.0.dist-infoo/x", False),
        ("pkg/__init__.py", False),
        ("pkg\\dist-info\\x", False),
    ],
)
def test_is_dist_info_path(distribution_path: str, expected: bool) -> None:
    """Must match the full ``.dist-info`` suffix on the first path
    segment only (not a substring), and must not treat a
    backslash-separated (non-normalized) input as having any segments at
    all -- its contract is POSIX-only, enforced by the caller."""
    assert is_dist_info_path(distribution_path) is expected


def test_extract_wheel_to_included_files_cross_platform_nested_path(
    fake_build: _FakeBuildState, tmp_path: Path
) -> None:
    """A wheel with a nested directory entry (the only legal ZIP form is
    ``/``-separated) must produce a real, readable file and a
    ``/``-separated ``distribution_path`` on whatever OS this test runs
    on -- no ``if sys.platform`` branch should be needed for this to
    pass identically on POSIX and Windows."""
    fake_build.entries = {"pkg/sub/deep/mod.py": b"x = 1\n"}

    result = build_and_read_wheel(tmp_path)

    assert result is not None
    files, cleanup = result
    assert len(files) == 1
    entry = files[0]
    assert entry.distribution_path == "pkg/sub/deep/mod.py"
    assert "\\" not in entry.distribution_path
    assert Path(entry.path).is_file()
    assert Path(entry.path).read_bytes() == b"x = 1\n"
    cleanup()
