---
Created: 2026-09-21
Last-Modified: 2026-09-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Explicit config sources (`--config`/`pitloom_config=`): implementation record

See also:
[cli-shared-options-ignored.md](../design/cli-shared-options-ignored.md)
(the gap survey this fixes; trimmed to what's still open),
[docs/configuration.md](../../docs/configuration.md#where-settings-come-from)
(the published per-surface table), [manual-cli-checks.md](manual-cli-checks.md)
(check 12).

## The problem

Before this change, a wheel/env/model target read whichever
`pyproject.toml` happened to sit in the current working directory --
`resolve_generator_config()` walked from `Path.cwd()`. That directory
has no necessary relationship to the wheel/model/environment being
scanned: running `loom wheel dist/other-package.whl` from inside an
unrelated project silently picked up *that* project's settings
(`enrich`, `update-registry`, creator identity, `ids-file`). There was
also no way to point any of these targets at a config file at all --
only a project directory's own `pyproject.toml` was reachable.

## Decisions

- **Precedence**: per-run flag/parameter > `--config FILE`/
  `pitloom_config=` > the target's own `[tool.pitloom]` (project
  directory, sdist -- see below, `embed-wheel --project-dir`, the
  Hatchling hook only) > hardcoded default.
- **Replace, not merge**: `--config`/`pitloom_config=` replaces the
  target's own config outright. A field the given config leaves unset
  reverts to the built-in default, never to the target's own value --
  merging field-by-field would make the two configs' precedence order
  depend on which fields either happens to set, impossible to reason
  about from the CLI alone.
- **No implicit reads, ever, for a target with no project of its own**:
  a wheel, an installed environment, a model file, a Hugging Face
  model, `enrich` without `--project-dir`, and `embed-wheel` without
  `--project-dir` never read the current directory or the target's own
  location. `resolve_standalone_config()` (`core/config_cascade.py`) is
  the one function every such generator calls: overrides, then an
  explicit `pitloom_config`, then `PitloomConfig()`'s defaults --
  nothing else.
- **`INERT` by target kind, not by command**: `core/inert_options.py`
  keys the "options that don't apply" table by target kind (`PROJECT`,
  `SDIST`, `WHEEL`, `ENV`, `MODEL_FILE`, `HF`, `ENRICH`,
  `EMBED_PROJECT`, `EMBED_STANDALONE`, `EMBED_SBOM`), not by CLI
  subcommand, so `loom wheel`, `loom generate x.whl` and
  `generate("x.whl")` share one row and one wording. `PARAM_TO_FLAG`
  gives each library parameter's CLI spelling for the warning; a
  `BooleanOptionalAction` flag names both spellings since either one may
  be the one given. `settle_inert()` warns in `PARAM_TO_FLAG` order, not
  the caller's mapping order, so the warning sequence is deterministic
  regardless of which dict a caller happened to build.
- **The deepest layer that drops a parameter warns about it, exactly
  once**: `forward_options()` reads the callee's signature to decide
  what it accepts; what it doesn't accept and `INERT` declares inert for
  that kind is settled there. An option the callee *does* accept is left
  for the callee's own `settle_inert()` call -- never double-warned, and
  a parameter neither the callee accepts nor `INERT` declares is a
  wiring bug (`ValueError`), not a silent drop.
- **A whole-batch warning fires once, not once per wheel**:
  `embed-wheel`'s `_settle_batch_options()` settles every option before
  the per-wheel loop starts, mirroring `EmbedFileCache.once()` for the
  build flags. `_generate_embed_sbom_json()`'s own `_settle_embed_options()`
  uses `EmbedFileCache.once()` too when a cache is given, keyed on the
  inert set and on the byte cap, so a shared batch warns once for the
  whole batch, not once per call.
- **The byte cap normalises once, not per generator**:
  `max_source_metadata_bytes` used to be normalised independently inside
  each provenance-resolution call site; it now normalises once inside
  `apply_overrides()`/`_settle_embed_options()`, so a too-small value
  warns once regardless of how many downstream calls read the resolved
  `ProvenanceConfig`.
- **`load_config_file()` fails loudly**: unlike a target's own
  (optional) config, a file the user named with `--config` is a source
  that claimed to carry settings -- missing, a directory, non-UTF-8,
  invalid TOML, or an invalid setting each raise, naming the file,
  instead of degrading to defaults. A file with no `[tool.pitloom]`
  table is not an error (empty is valid TOML) but does warn, since a
  wrong path would otherwise pass unnoticed.
- **A relative `ids-file` inside `--config` resolves against the config
  file's own directory**, not the current directory and not a symlink
  target's directory -- the config means the same thing regardless of
  where Pitloom runs from.
- **A relative `--registry` on the command line resolves against the
  current directory, on every command** -- unlike a target's own
  `ids-file`, which is project-relative. This is a path given on the
  command line, so it follows shell-path convention, not the config's.
- **`embed-wheel` never infers a project from the current directory**:
  `--project-dir` is required to have it rescan one; without it (and
  without `--sbom`), it embeds a standalone-wheel SBOM built from the
  wheel's own contents alone.
- **`resolve_project_with_lockfile()` still does the real project
  read**: an explicit config never skips reading `project_target`'s
  metadata -- only its `[tool.pitloom]` is swapped in afterward
  (`_with_config()`). A malformed target `pyproject.toml` still raises
  even under `project --config C`, since the real read runs regardless.

## Tests

- `tests/cli/test_cli_option_reach.py` -- every `INERT` row reachable
  from its CLI subcommand warns with the right flag spelling and
  reason.
- `tests/cli/test_cli_no_implicit_config.py` -- CLI-level: no
  `wheel`/`env`/`model`/`enrich`/`embed-wheel` invocation reads a decoy
  `pyproject.toml`/`loom-ids.json` from the current directory.
- `tests/assemble/test_generator_no_implicit_config.py` -- the same
  guarantee at the library level, per generator function.
- `tests/assemble/test_explicit_config_edges.py` -- `--config`/
  `pitloom_config=` edge cases: missing file, directory, non-UTF-8,
  invalid TOML, no `[tool.pitloom]` table, relative `ids-file`
  resolution, replace-not-merge.
- Manual check 12 in
  [manual-cli-checks.md](manual-cli-checks.md#the-checks) runs the same
  no-implicit-config guarantee against the real `loom` entry point (a
  decoy project directory, `--offline`, byte-identical SBOMs, registry
  untouched).

## Paths rejected

- **The PR #228 cwd cascade** (`resolve_generator_config()` walking
  `Path.cwd()` for wheel/env/model) -- the problem this whole change
  fixes; see "The problem" above. Removed outright, not deprecated,
  since it never shipped in a release.
- **Reading a config from the target's parent directory** (e.g. a
  wheel's own containing folder) -- considered and rejected: a
  `dist/*.whl` typically sits next to unrelated build artefacts, not a
  `pyproject.toml`, and even when one exists there is no more
  trustworthy a signal than the current directory is. Only an explicit
  `--config`/`pitloom_config=` earns trust.
- **Merging `--config` with the target's own config** -- rejected for
  precedence clarity (see "Replace, not merge" above). A merge would
  also need its own tri-state semantics per field (unset vs.
  explicitly-default), which none of `PitloomConfig`'s fields carry
  today.
- **A command-keyed inert table** (one row per CLI subcommand instead of
  per target kind) -- rejected: `loom generate x.whl` and `loom wheel`
  reach the same generator, so a command-keyed table would need two
  entries kept in lockstep by hand, reintroducing the drift class
  `INERT` exists to prevent.

## Found, not fixed here

- **Id-minting collision, now also reachable via an explicit config's
  `ids-file`.** The pre-existing registry-id-collision defect (see
  [cli-shared-options-ignored.md](../design/cli-shared-options-ignored.md#found-while-doing-this-not-fixed-here))
  was previously unreachable from `wheel`/`env`/`model` because those
  surfaces never resolved an `ids-file` at all. An explicit
  `--config`/`pitloom_config=` now lets a wheel/env/model target resolve
  one, which widens this defect's surface without changing its cause.
- **A latent import cycle**, hidden by import order:
  `core._config_parse` imports `extract._toml_io`, which (via
  `extract/__init__.py`) reaches `extract.project.reader`, which imports
  `core.config`. Not exercised today only because `core.config` happens
  to finish importing before `extract` does in every current entry
  point.
- **`--use-lockfile`'s no-effect warning stays outside `INERT`.** It
  uses the same `Options:` prefix now, but is settled by
  `warn_use_lockfile_no_effect()` in `extract/project/reader.py`, not by
  `settle_inert()` -- a CLI target that never offers the flag (`wheel`,
  `model`, `env`, `embed-wheel`) can't warn about it at all, so there is
  no `INERT` row for it; `generate()`/`enrich_model()` order the
  sdist-archive warning differently between the CLI and the library
  path.
- **`embed-wheel --project-dir D --sbom FILE` drops `D` silently.**
  `--sbom` takes the `EMBED_SBOM` kind regardless of whether
  `--project-dir` was also given, and `_generate_embed_sbom_json()`
  returns *FILE*'s bytes before `project_dir` is ever consulted. No
  warning names `--project-dir` itself, since it isn't a `PARAM_TO_FLAG`
  entry.
- **`--describe-relationship` warns on `embed-wheel`/`enrich`.** A
  current decision (a wheel-embedded SBOM is always canonical; a
  fragment has no relationships of its own to describe), not
  necessarily permanent -- revisit if either target's shape changes.
- **`-v` source reporting is project-only.** `wheel`/`env`/`model`/
  `enrich` print resolved values with `--verbose`, but no per-value
  source label (config file vs. default); only `project`/`generate` on
  a project directory or sdist label sources, via `cli/verbose.py`.
- **The Hatchling build hook ignores `[tool.pitloom]`
  `pretty`/`describe-relationship`.** It always writes canonical
  (`pretty=False`) JSON with no relationship descriptions, per PEP 770,
  regardless of what the project's own config sets (already noted in
  the hook's own docstring, `plugins/hatch.py`).
- **`loom wheel --embed` embeds the `-o`-shaped SBOM**, unlike
  `embed-wheel`'s own path (always canonical). `--pretty`/
  `--describe-relationship` reach the embedded copy with no warning,
  since `--embed` on `wheel` is deliberately the wheel's own SBOM as
  generated for `-o`, not `embed-wheel`'s stricter always-canonical
  contract.
- **An sdist archive's own `[tool.pitloom]` is never read.** Its
  bundled `pyproject.toml`/`PKG-INFO` is read for project metadata
  only; `read_project()` returns `PitloomConfig()` (defaults) for an
  sdist target. Only `--config`/`pitloom_config=` can set one.
- **An invalid target `[tool.pitloom]` still fails `project --config
  C`.** `resolve_project_with_lockfile()`'s real metadata read
  (`read_project()`/`read_pyproject()`) always runs first and can raise
  `ValueError` on malformed TOML; the config swap in `_with_config()`
  happens only after that succeeds, so `--config` cannot rescue a
  target with its own broken `pyproject.toml`.
- **A no-effect warning's subject differs by command.** `wheel`/`model`
  use the target as typed on the command line (not resolved to an
  absolute path) for `wheel`, but a resolved absolute `Path` for a
  local model file; `embed-wheel`'s batch settle uses the literal
  string `"embed-wheel"` as the subject for a standalone embed, not a
  per-wheel name.
- **`loom.Run(registry=None)` still walks up from the current
  directory for a registry.** The `pitloom.loom` tracking-decorator/
  context-manager surface was not brought in line with the "no
  implicit cwd reads" rule this change applied to every CLI command and
  generator function.
- **`-v` does not read `setup.cfg`'s `[tool:pitloom]`
  `pretty`/`describe-relationship` keys for source labelling.**
  `_load_pitloom_tool_section()` returns `{}` for a `setup.cfg`/
  `setup.py` config path, so `--verbose` reports `"default"` for
  `pretty`/`describe_relationship` even when `setup.cfg` set one and it
  took effect.
