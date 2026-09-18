# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Check that structured version fields agree with ``__about__.py``.

``--print-version`` instead prints ``__about__.py``'s version and exits; the
GitHub Action (``scripts/action/pitloom-install.sh``) runs it at runtime to learn which
Pitloom version its pinned checkout carries.

Covers the version *fields* that must always exactly equal the released
version: ``codemeta.json``, ``.claude-plugin/plugin.json``, and
``pyproject.toml`` (indirectly, via its ``[tool.hatch.version]`` source).

Excludes ``CITATION.cff`` -- ``codemeta2cff.yml`` already
regenerates and validates it from ``codemeta.json`` on every push.

Also deliberately does not check prose version *mentions*
(README.md, action.yml examples, docs/index.md, ...) -- those are free-text
and change shape per file, unlike these structured fields;
see the manual grep step in working-docs/implementation/release-checklist.md
for that broader, still-manual check.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def read_about_version(about_path: Path | None = None) -> str:
    """Read ``__version__`` from ``src/pitloom/__about__.py`` -- the
    single source of truth ``[tool.hatch.version]`` resolves from."""
    if about_path is None:
        about_path = REPO_ROOT / "src" / "pitloom" / "__about__.py"
    text = about_path.read_text(encoding="utf-8-sig")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if match is None:
        raise ValueError(f"Could not find __version__ in {about_path}")
    return match.group(1)


def read_codemeta_version() -> str:
    path = REPO_ROOT / "codemeta.json"
    data = json.loads(path.read_bytes())
    return str(data["version"])


def read_plugin_json_version() -> str:
    path = REPO_ROOT / ".claude-plugin" / "plugin.json"
    data = json.loads(path.read_bytes())
    return str(data["version"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that structured version fields agree with __about__.py."
    )
    parser.add_argument(
        "--print-version",
        action="store_true",
        help="print the __about__.py version and exit",
    )
    args = parser.parse_args(argv)
    if args.print_version:
        print(read_about_version())
        return 0

    expected = read_about_version()
    checks = {
        "codemeta.json": read_codemeta_version(),
        ".claude-plugin/plugin.json": read_plugin_json_version(),
    }

    mismatches = {name: actual for name, actual in checks.items() if actual != expected}

    if mismatches:
        print(
            f"ERROR: version mismatch -- src/pitloom/__about__.py says {expected!r}",
            file=sys.stderr,
        )
        for name, actual in mismatches.items():
            print(f"ERROR: {name} says {actual!r}", file=sys.stderr)
        return 1

    print(f"OK: version {expected!r} consistent across all checked files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
