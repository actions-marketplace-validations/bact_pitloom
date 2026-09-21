---
Created: 2026-09-21
Last-Modified: 2026-09-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Step 6.5: an sdist reads its own `[tool.pitloom]`

See also: [config-sources.md](config-sources.md) (the rule this completes,
PR #231), [roadmap.md](../design/roadmap.md) (steps 7-10),
[canonical-output-followups.md](../design/canonical-output-followups.md)
(item #2, still open; #1/#3/#4 were folded in here).

## What was built

An sdist archive is a project target, so it now reads its own config as
the unpacked directory does. Before, `read_project()` returned
`PitloomConfig()` for an archive, so `loom project x.tar.gz` and
`loom project <unpacked x>/` gave different SBOMs from the same config.

- `extract/project/sdist.py`: one member scan shared by tar and zip
  (`_scan()` over `(name, open)` pairs). It keeps the first root-level
  (`<top>/<name>`) `PKG-INFO`, `pyproject.toml` and `setup.cfg`, streams
  everything in 8192-byte chunks, and caps a config member at 1 MiB
  (`CONFIG_MEMBER_MAX_BYTES`; over it is a read failure, below).
  `read_sdist()` returns `SdistContents(metadata, files, config,
  config_member)`.
- One selection rule for both targets:
  `core/_config_parse.py:select_project_config()` -- the pyproject
  config when it names the project or sets anything, else `setup.cfg`'s
  `[tool:pitloom]`, else the defaults. `reader._fallback_to_setuptools`
  and `sdist._config` both call it; the drift test runs the same shapes
  through a directory and a `.tar.gz`/`.zip`.
- The TOML is decoded as `tomllib.load()` decodes a file
  (`_toml_io.load_toml_bytes`, strict UTF-8).
- A config member that cannot be read (not TOML, not UTF-8 or a BOM, over
  the cap, a `setup.cfg` `configparser` error such as a bare `%`) or is
  invalid raises `ValueError("config file
  demo-1.0.0.tar.gz:pyproject.toml: ...")`, the `load_config_file()`
  wording with the member in place of a path -- as a directory fails.
  Never a fall-through to `setup.cfg`: an over-cap member still counts as
  the first of its name. Without the config read, a PKG-INFO-less
  archive's unparseable `pyproject.toml` is one `WARNING:` naming the
  metadata fields lost, as before.
- `read_project()` returns `archive/member` as the config path;
  `config_source_label()` turns it into `demo-1.0.0.tar.gz:pyproject.toml`
  for `-v` (`config_file_display()` gives `<archive path>:<member>` for the
  "Config file" row), and `sdist_config_source()` re-reads only the root
  members to find the raw table. `-v` runs after generation, and with
  `--config` it reports that file, so it never re-reads a broken archive.

## Decisions

1. **`ids-file` and fragments: documented, not warned.** #231's rule: a
   config *key* a target cannot use is documented; a *flag* warns. The
   `ids-file` could only name a file inside the archive, so `read_sdist()`
   drops it -- and the fragments -- at the source, so the CLI, the
   library, `enrich --project-dir` and `embed-wheel --project-dir` all get
   the same config with no caller-side "explicit or own" branch (the
   first version dropped fragments only in `_generators.py`, and
   `embed-wheel --project-dir <sdist>` still merged them). A `required =
   true` fragment does not fail an sdist. Rejected: one `WARNING:` per key (the design doc's
   first proposal) -- it would warn on every third-party sdist that
   ships a normal config.
2. **Identity keys apply** (creators, creation comment and datetime), as
   for a cloned directory.
3. **`setup.cfg` is read** when the pyproject has no usable config, for
   parity with a directory.
4. **An invalid config raises**, as for a directory.
5. **`--config`/`pitloom_config=` does not parse the config it replaces.**
   `read_config` is threaded through `read_project()` ->
   `read_pyproject()`/`read_setuptools()`/`read_setup_cfg()`/
   `read_sdist()`; `resolve_project_with_lockfile()` passes
   `read_config=explicit_config is None`. Without this, decision 4
   would make a broken third-party sdist unusable. An explicit flag, not
   call-site discipline (AGENTS.md "stage-scoped helpers").

Rejected: warn-and-defaults for an unparseable `pyproject.toml` (the
first plan). With a `setup.cfg` beside it, the selection then fell
through to `setup.cfg`'s config while the directory failed.

Rejected: rescanning the archive inside `config_source_label()`, which
runs on every invocation, not only under `-v`.

## Canonical output folded in

- **LF and UTF-8** (#4): `pitloom/_sbom_io.py` is the one writer for
  SBOM, fragment and registry text, stdout included (UTF-8 bytes, one
  trailing `\n`). `tests/test_sbom_io.py` scans `src/` for any other
  text-mode write.
- **UTC `Z`** (#3): `builtTime` goes through `parse_iso_datetime()` and
  `to_spdx3_datetime()`; a raw `fromisoformat()` rejected `Z` on 3.10
  (the Hatchling build failed) and kept offsets. A scan in
  `tests/test_wall_clock_sources.py` confines raw parsing to
  `creation_info.py`.
- **Sorted keys** (#1): at the choke points, not per reader --
  `record_dict_field_provenance()`, `_populate_ai_pkg_hyperparameters()`
  (quantization stays first) and the `pitloom.loom` run's
  hyperparameters and their provenance.

## Found, not fixed here

- `embed-wheel --project-dir <sdist>` runs Hatchling file discovery
  against the archive path and warns `Hatchling file discovery failed`;
  also on `main` before this change.
- `-v` labels a value from `setup.cfg`'s `[tool:pitloom]` `[default]`, for
  a directory and an sdist alike.
- A `%` in any `setup.cfg` value fails the config read
  (`configparser` interpolation), for a directory and now an sdist;
  setuptools itself may read such a file. Not checked against setuptools.

- `import pitloom._loom_active_run` as the *first* Pitloom import fails:
  it imports `pitloom.loom`, which imports it back. Every real entry
  point imports `pitloom.loom` first, so nothing is affected; also on
  `main` before this change.
