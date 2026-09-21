---
Created: 2026-09-20
Last-Modified: 2026-09-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Shared CLI options accepted, then silently ignored

See also: [roadmap.md](roadmap.md) (one-line entry) and
[manual-cli-checks.md](../implementation/manual-cli-checks.md) (checks 11 and
the CLI matrix that found these).

The common parent parser gives every SBOM subcommand the same options, but
several subcommands never pass some of them on. Settle each gap per option:
warn "has no effect" (as the build flags do) or stop offering it where the
absence is structural; thread it through the shared mechanism where it
governs a data source that any surface may meet (see the `env` item). Cells
`M/{wheel,model,enrich,env}/opt/...` of `scripts/manual_cli_checks` track
them.

## Gaps

- **`wheel`, `model`, `enrich`, `env`** never pass `--extract-file-header`,
  `--content-type` or `--content-type-method` on.
- **`--describe-relationship`** has no effect on `embed-wheel`, `model` or
  `enrich`. `ConfigOverrides` now carries the field (and `pretty`,
  `update_registry`), but `_build_sbom_from_project_and_wheel` hardcodes
  `to_json(pretty=False)` and reads neither -- the plumbing is the
  remaining half.
- **`env` and `--max-source-metadata-bytes`**: `env` passes the raw
  `pitloom_config.provenance`, so the flag skips
  `resolve_effective_provenance` (no warning for a too-small value). Do not
  "fix" this by warning "no effect": the cap governs a *data source* (large
  artefact metadata, today from AI model files, possibly other sources
  later), and any surface may meet one. It is inert on `env` today only
  because `env` never scans for AI models (next item). Thread it through the
  shared resolver on every surface, whether or not the surface currently
  finds such a source.
- **Surfaces that never scan for AI models**: only `project`/`generate` and
  `embed-wheel --project-dir` scan (`ai_models=` is `[]` in
  `generate_wheel_sbom`, `generate_env_sbom` and the standalone-wheel embed),
  so a built wheel or an installed package that carries a model file gets no
  `AIPackage`. Decide whether they should. Either way the provenance
  settings must already be wired when they do.
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

`generate_wheel_sbom`/`generate_env_sbom` take `content_type_method` and
resolve the current directory's `[tool.pitloom]` for policy settings
(identity settings -- `creators`/`creation-datetime`/`creation-comment` --
and `ids-file` deliberately excluded); `build_deployed()` no longer drops
`content_type_method` (PR #228). The `wheel`/`env` CLI commands pass
`update_registry`/`offline` straight through as `None` when the flag is
omitted and never pass `content_type_method`, so those three already reach
the cascade from the CLI. `pretty`, `describe_relationship` and provenance
do not: the CLI resolves them against a default `PitloomConfig()` and
passes a concrete value, which pre-empts the cascade.

## Found while doing this, not fixed here

- **Registry id minting does not reserve registry-supplied numbers.** When
  a registry supplies ids for some elements, the counter that mints the
  rest restarts at 1 and can hand out a number the registry already used,
  so two `software_File` elements collide on one spdxId and a second run
  of the same target is not byte-identical. Reproduced on `main` with a
  default-named `loom-ids.json` in the current directory and three
  consecutive `generate_wheel_sbom()` runs: run 1 differs from runs 2-3,
  and runs 2-3 carry a duplicate `#File-2`. This is why the wheel/env
  cascade deliberately stops short of `ids-file` -- routing those surfaces
  into a registry would have spread the defect, not caused it. Fixing the
  minting is a prerequisite for cascading `ids-file` there.
- **`read_pitloom_config` gates on `Path.exists()`**
  (`core/_config_parse.py`), which swallows a different errno set on
  Python 3.14 than on 3.10-3.13 (see AGENTS.md). An unreadable *parent*
  directory therefore warns on 3.10-3.13 and falls through to the silent
  "missing config" branch on 3.14. `os.path.isfile` is the
  version-independent spelling. Unverified on 3.14 -- only 3.10 was to
  hand.
- **`ConfigOverrides.update_registry` is accepted and dropped on the embed
  surface.** `pretty`/`describe_relationship` are inert there by design (a
  wheel-embedded SBOM is JCS-canonical per PEP 770), but silently ignoring
  `update_registry=True` is a "no silent deviations" violation. It belongs
  with the inert-flag warning mechanism, not with the cascade.
- **`file-map.md`'s per-directory test counts are stale** for `cli/` (says
  14, is 18) and `core/` (says 42, is 27), independently of any change
  here.
