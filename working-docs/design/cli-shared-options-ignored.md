---
Created: 2026-09-20
Last-Modified: 2026-09-20
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Shared CLI options accepted, then silently ignored

See also: [roadmap.md](roadmap.md) (one-line entry) and
[manual-cli-checks.md](../implementation/manual-cli-checks.md) (checks 11 and
the CLI matrix that found these).

The common parent parser gives every SBOM subcommand the same options, but
several subcommands never pass some of them on. Each gap below should either
warn "has no effect" (as the build flags do) or stop offering the option
there. Cells `M/{wheel,model,enrich,env}/opt/...` of
`scripts/manual_cli_checks` track them.

## Gaps

- **`wheel`, `model`, `enrich`, `env`** never pass `--extract-file-header`,
  `--content-type` or `--content-type-method` on.
- **`--describe-relationship`** has no effect on `embed-wheel` (not in
  `ConfigOverrides`), `model` or `enrich`.
- **`env` and `--max-source-metadata-bytes`**: `env` passes the raw
  `pitloom_config.provenance`, so the flag skips
  `resolve_effective_provenance` (no warning for a too-small value). It has
  no other effect, as `env` has no AI artefacts to cap.
- **Standalone-wheel `embed-wheel`** (no project directory: no
  `--project-dir`, and the current directory is not a project):
  `_build_sbom_standalone_wheel` has no `content_type_method` parameter, so
  `build()` uses `auto`. The same branch drops a supplied `pitloom_config`'s
  `offline`, provenance and `sbom_basename` for a library caller; the CLI
  always passes a resolved `ConfigOverrides`, so it is unaffected.
- **`embed-wheel --sbom`** accepts `--content-type-method`,
  `--max-source-metadata-bytes` and `--content-type`, and ignores them
  without the "no effect" warning the build flags get.

## Already fixed

`embed-wheel --project-dir` hands `--content-type-method` and
`--max-source-metadata-bytes` to the assembler, as `loom project` and the
Hatchling hook do (PR #227), through `PitloomConfig.assemble_options`.
