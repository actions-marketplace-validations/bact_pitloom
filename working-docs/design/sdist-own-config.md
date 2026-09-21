---
Created: 2026-09-21
Last-Modified: 2026-09-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Step 6.5: an sdist target reads its own `[tool.pitloom]`

See also: [roadmap.md](roadmap.md) (one-line entry),
[config-sources.md](../implementation/config-sources.md) (the rule this
completes, PR #231).

Planned as its own small PR after #231 and before step 7 (scanner
refactor). Not started.

## Problem

PR #231's rule: a project target reads its own `[tool.pitloom]`; nothing
else is read implicitly. An sdist archive is a project target, but
`read_project()` returns `PitloomConfig()` for one: the archive's root
`pyproject.toml` is read for project metadata (as a PKG-INFO fallback)
and its `[tool.pitloom]` is discarded. So `loom project x.tar.gz` and
`loom project <unpacked x>/` give different SBOMs from the same config.

Mechanically small: `extract/project/sdist.py` already holds the root
`pyproject.toml` bytes (`_read_tar_sdist()`/`_read_zip_sdist()`).

## Decisions to take (proposed defaults)

1. **`ids-file`** points into the archive, not at a file on disk, and
   the archive's directory is not the project (#231). Proposed: ignore
   it, one `WARNING:`.
2. **`[tool.pitloom.fragment]` paths**: fragments merge only for a
   directory target. Proposed: warn that they have no effect for an
   sdist, instead of dropping them silently.
3. **Identity keys** (creators, creation comment/datetime): a third-party
   sdist names its upstream as SBOM creator -- as a cloned project
   directory already does. Proposed: apply, as for a directory.
4. **`setup.cfg` `[tool:pitloom]` inside the archive**: a directory
   target reads it when there is no `pyproject.toml`. Proposed: read it,
   for parity.
5. **An invalid `[tool.pitloom]` inside the archive**: a directory
   target raises. Proposed: raise too (consistency), accepting that a
   broken third-party sdist then blocks generation until `--config`
   replaces it -- which needs item 6.
6. **Bundle: `project --config C` still parses the config it replaces**
   (`resolve_project_with_lockfile()` runs the real `read_project()`),
   so an invalid target config fails a run whose config was replaced.
   Give the reader a way to skip `[tool.pitloom]` parsing when an
   explicit config is given; the same "which config a project target
   reads" question as this step.

## Consequences

- Output bytes change for an sdist that carries `[tool.pitloom]`
  (`pretty`, creators, provenance...): CHANGELOG "Changed".
- `docs/configuration.md` "Where settings come from": the sdist row
  flips from "Never read" to "Read".
- Tests: the reach matrix and `test_cli_no_implicit_config.py` already
  have sdist targets; add one per decision above, plus
  directory-vs-archive parity for the same project.
