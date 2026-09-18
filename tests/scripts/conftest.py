# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Fixtures for testing the helper scripts under ``scripts/``.

The scripts are not an importable package (they also run standalone on the
GitHub Actions runner), so each is loaded by file path.
"""

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture(name="scripts_dir")
def scripts_dir_fixture() -> Path:
    """The repository's ``scripts/`` directory."""
    return SCRIPTS_DIR


@pytest.fixture(name="load_script")
def load_script_fixture() -> Callable[[str], ModuleType]:
    """Return a loader: ``load_script("action/python_probe")``."""

    def load(name: str) -> ModuleType:
        path = SCRIPTS_DIR / f"{name}.py"
        module_name = "scripts_" + name.replace("/", "_")
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        # NamedTuple/dataclass resolution needs the module registered.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    return load
