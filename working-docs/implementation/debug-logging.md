---
Created: 2026-09-17
Last-Modified: 2026-09-17
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# `--debug` flag and DEBUG:-level output ([PR #201](https://github.com/bact/pitloom/pull/201))

See also: [roadmap.md](../design/roadmap.md) (Near-term -- "Diagnostics /
logging"), the "CLI output" section of the top-level `CLAUDE.md`.

Split out of `roadmap.md` (2026-09-17) once this item's detail grew
past a summary.

## Surface `DEBUG:`-level output on request

Shipped both triggers rather than choosing one:

- A new top-level `--debug` flag, parsed before the subcommand (like
  `-V`). `cli/verbose.py`'s existing `--verbose` was left alone since it
  does something unrelated.
- The `PITLOOM_DEBUG` environment variable, which also covers entry
  points that don't parse CLI flags themselves (the Hatchling build
  hook, every public library-API generator).

`configure_logging(debug=...)` resolves `None` (every existing
no-argument call site) against the env var; an explicit `True`/`False`
(the CLI's `--debug`) wins outright. See `pitloom.logging_config`.

## Promote silent-data-loss `DEBUG:` messages to `WARNING:`

18 messages across the HF Hub, PyTorch/PT2, fastText, README
enrichment, and sdist extractors, plus `pitloom.loom`'s
caller-provenance detection, now surface by default (not just under
`--debug`) when a failure drops or degrades an SBOM/AIBOM field.

Each names the affected field(s) via one shared, grep-able helper,
`field_loss_suffix()` (`pitloom.logging_config`), instead of
hand-duplicated suffix text per call site.
