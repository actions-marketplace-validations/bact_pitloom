# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Decide whether the ``python`` on ``PATH`` can host a Pitloom install.

Used at runtime by ``action.yml`` (the "Check workflow Python" step) when the
``python-version`` input is empty: a usable interpreter is left alone, an
unusable one is replaced via ``actions/setup-python``.

The script runs under whatever interpreter the runner has, including one
too old for Pitloom, so it must import and parse on Python 3.7+ and check
the version before anything else. Exit status 0 means usable; otherwise the
reason is printed on stdout and the exit status is 1.

See also: ``pitloom-install.sh`` and ``python-resolve.sh`` in this directory.
"""

from __future__ import annotations

import os
import sys
import sysconfig
from collections.abc import Mapping, Sequence
from importlib import util as importlib_util
from typing import NamedTuple

# Keep equal to the lower bound of ``requires-python`` in pyproject.toml.
MIN_PYTHON = (3, 10)

_FALSE_VALUES = ("", "0", "false", "no", "off")


def _is_writable(path: str) -> bool:
    """Whether pip could write ``path``, judged by its nearest existing parent."""
    probe = os.path.abspath(path)
    while not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            return False
        probe = parent
    return os.access(probe, os.W_OK)


def _canonical(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def _on_path(directory: str, path_env: str) -> bool:
    wanted = _canonical(directory)
    entries = (entry for entry in path_env.split(os.pathsep) if entry)
    return any(_canonical(entry) == wanted for entry in entries)


def _externally_managed(
    prefix: str, base_prefix: str, stdlib_dir: str, environ: Mapping[str, str]
) -> bool:
    """PEP 668 marker present and pip's own override not in effect."""
    if prefix != base_prefix:
        return False  # in a virtual environment
    override = environ.get("PIP_BREAK_SYSTEM_PACKAGES", "").strip().lower()
    if override not in _FALSE_VALUES:
        return False
    return os.path.exists(os.path.join(stdlib_dir, "EXTERNALLY-MANAGED"))


class Interpreter(NamedTuple):
    """The facts about one interpreter that the probe inspects."""

    version_info: Sequence[int]
    has_pip: bool
    prefix: str
    base_prefix: str
    stdlib_dir: str
    install_dirs: Sequence[str]
    scripts_dir: str

    @classmethod
    def current(cls) -> Interpreter:
        """Describe the running interpreter."""
        return cls(
            version_info=tuple(sys.version_info[:3]),
            has_pip=importlib_util.find_spec("pip") is not None,
            prefix=sys.prefix,
            base_prefix=sys.base_prefix,
            stdlib_dir=sysconfig.get_path("stdlib"),
            install_dirs=(
                sysconfig.get_path("purelib"),
                sysconfig.get_path("platlib"),
            ),
            scripts_dir=sysconfig.get_path("scripts"),
        )


def unusable_reason(
    interpreter: Interpreter, path_env: str, environ: Mapping[str, str]
) -> str | None:
    """Return why ``interpreter`` cannot host a Pitloom install, or ``None``."""
    if tuple(interpreter.version_info[:2]) < MIN_PYTHON:
        found = ".".join(str(part) for part in interpreter.version_info[:3])
        wanted = ".".join(str(part) for part in MIN_PYTHON)
        return f"Python {found} is older than {wanted}"
    if not interpreter.has_pip:
        return "pip is not installed"
    if _externally_managed(
        interpreter.prefix, interpreter.base_prefix, interpreter.stdlib_dir, environ
    ):
        return "environment is externally managed (PEP 668)"
    for directory in (*interpreter.install_dirs, interpreter.scripts_dir):
        if not _is_writable(directory):
            return f"{directory} is not writable"
    if not _on_path(interpreter.scripts_dir, path_env):
        return f"{interpreter.scripts_dir}, where pip puts loom, is not on PATH"
    return None


def main() -> int:
    """Probe the running interpreter; print the reason and return 1 if unusable."""
    reason = unusable_reason(
        Interpreter.current(), os.environ.get("PATH", ""), os.environ
    )
    if reason is None:
        return 0
    print(reason)
    return 1


if __name__ == "__main__":
    sys.exit(main())
