# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``EmbedFileCache`` under threads, and when its block's exit is
interrupted: one discovery and one settle per batch however many threads
share it, and an exit that cannot wait for a discovery still releases the
batch's :class:`~pitloom.core.build_signals.TerminationGuard`, with the
late discovery cleaning up after itself.

Split from :mod:`tests.assemble.test_embed_build_options` (the rest of
the cache's single-threaded behaviour and the build-options threading)
once that file crossed the ~400-500 line soft limit.
"""

from __future__ import annotations

import contextlib
import logging
import signal
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core.build_options import BuildOptions
from pitloom.core.config import PitloomConfig
from pitloom.embed import EmbedFileCache
from tests.build_and_read_shared import spied_raise_signal

_GET_WHEEL_FILES = "pitloom._embed_build_sbom.get_wheel_files"


@pytest.fixture(name="raise_spy")
def fixture_raise_spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[mock.Mock]:
    with spied_raise_signal(monkeypatch) as spy:
        yield spy


def test_embed_file_cache_resolves_once_across_threads(tmp_path: Path) -> None:
    """Threads sharing one batch get one discovery (one build) and one
    cleanup: a second discovery's cleanup would overwrite the first's,
    leaking its extraction dir."""
    cleanups = [mock.Mock(), mock.Mock()]
    all_cleanups = list(cleanups)

    def cleanup_calls() -> int:
        return sum(c.call_count for c in all_cleanups)

    barrier = threading.Barrier(2)

    def slow_get_wheel_files(*_args: object, **_kwargs: object) -> object:
        time.sleep(0.3)  # both threads are past the barrier by now
        return None, [], cleanups.pop()

    with mock.patch(_GET_WHEEL_FILES, side_effect=slow_get_wheel_files) as mocked:
        with EmbedFileCache() as cache:

            def resolve() -> None:
                barrier.wait(timeout=30)
                cache.resolve(tmp_path, PitloomConfig(), BuildOptions())

            threads = [threading.Thread(target=resolve) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
                assert not thread.is_alive()
        assert mocked.call_count == 1

    # The one discovery's cleanup ran at the batch's exit; no other exists.
    assert len(cleanups) == 1
    assert all(c.call_count == 0 for c in cleanups)
    assert cleanup_calls() == 1


def test_embed_file_cache_exit_waits_for_a_thread_still_resolving(
    tmp_path: Path,
) -> None:
    """Leaving the block while a thread is still inside ``resolve()`` must
    still run that discovery's cleanup -- an unsynchronised exit sees no
    cached result, cleans up nothing and leaves the cache poisoned for the
    next batch."""
    cleanup = mock.Mock()
    started = threading.Event()

    def slow_get_wheel_files(*_args: object, **_kwargs: object) -> object:
        started.set()
        time.sleep(0.3)  # the owner leaves its block during this
        return None, [], cleanup

    with mock.patch(_GET_WHEEL_FILES, side_effect=slow_get_wheel_files):
        cache = EmbedFileCache()
        with cache:

            def resolve() -> None:
                with contextlib.suppress(RuntimeError):  # block already closed
                    cache.resolve(tmp_path, PitloomConfig(), BuildOptions())

            worker = threading.Thread(target=resolve)
            worker.start()
            assert started.wait(timeout=30)
        worker.join(timeout=30)
        assert not worker.is_alive()
        cleanup.assert_called_once()

        # Not poisoned: the next batch resolves afresh, as documented.
        with cache as reentered:
            reentered.resolve(tmp_path, PitloomConfig(), BuildOptions())


class _InterruptingLock:
    """A lock whose acquire is interrupted, as Ctrl-C interrupts a real
    one while a thread still inside ``resolve()`` holds it."""

    def __enter__(self) -> None:
        raise KeyboardInterrupt

    def __exit__(self, *_args: object) -> None:
        """Never entered."""


def test_embed_file_cache_interrupted_exit_still_releases_the_guard(
    monkeypatch: pytest.MonkeyPatch, raise_spy: mock.Mock
) -> None:
    """Ctrl-C while the block's exit waits for the lock (a thread inside
    resolve() holds it for a whole build): the guard must still be
    released, or its handlers stay installed and every later block in
    this thread nests under a dead owner."""
    del raise_spy

    cache = EmbedFileCache()
    with pytest.raises(KeyboardInterrupt):
        with cache:
            monkeypatch.setattr(cache, "_lock", _InterruptingLock())

    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL

    # Not stale: a later block owns its own guard, so its fallback runs.
    fallback: list[str] = []
    with pytest.raises(RuntimeError):
        with EmbedFileCache() as later:
            guard = later._guard
            assert guard is not None
            guard.add_cleanup(lambda: fallback.append("removed"))
            raise RuntimeError("batch failed")
    assert fallback == ["removed"]


def test_embed_file_cache_resolve_cleans_up_when_the_block_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raise_spy: mock.Mock
) -> None:
    """The other half of an interrupted exit: the discovery it could not
    wait for finishes afterwards, so resolve() runs that cleanup itself
    and refuses the result -- nothing else would."""
    del raise_spy
    cleanup = mock.Mock()
    release = threading.Event()
    inside = threading.Event()
    failures: list[BaseException] = []

    def blocking_get_wheel_files(*_args: object, **_kwargs: object) -> object:
        inside.set()
        assert release.wait(timeout=30)
        return None, [], cleanup

    cache = EmbedFileCache()
    with mock.patch(_GET_WHEEL_FILES, side_effect=blocking_get_wheel_files):

        def resolve() -> None:
            try:
                cache.resolve(tmp_path, PitloomConfig(), BuildOptions())
            except BaseException as exc:  # pylint: disable=broad-exception-caught
                failures.append(exc)

        worker = threading.Thread(target=resolve)
        with pytest.raises(KeyboardInterrupt):
            with cache:
                worker.start()
                assert inside.wait(timeout=30)
                # The Ctrl-C lands while the exit waits for that discovery.
                monkeypatch.setattr(cache, "_lock", _InterruptingLock())
        release.set()
        worker.join(timeout=30)

    assert not worker.is_alive()
    cleanup.assert_called_once()
    assert [type(exc) for exc in failures] == [RuntimeError]


def test_embed_file_cache_settles_once_across_threads(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """One ``WARNING:`` per ineffective flag for the batch, threads
    included: settling emits the warning, so it must not race."""
    options = BuildOptions(timeout=900)
    real_settle = BuildOptions.settle
    inside = threading.Event()

    def slow_settle(self: BuildOptions, subject: object) -> BuildOptions:
        inside.set()  # the second thread reaches settle() during this
        time.sleep(0.3)
        return real_settle(self, subject)

    monkeypatch.setattr(BuildOptions, "settle", slow_settle)

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with EmbedFileCache() as cache:
            first = threading.Thread(
                target=lambda: cache.settle(options, "demo-1.0.whl")
            )
            first.start()
            assert inside.wait(timeout=30)
            cache.settle(options, "demo-1.0.whl")
            first.join(timeout=30)
            assert not first.is_alive()

    warnings = [
        r.getMessage() for r in caplog.records if "has no effect" in r.getMessage()
    ]
    assert len(warnings) == 1, warnings
