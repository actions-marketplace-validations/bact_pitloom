---
Created: 2026-04-14
Last-Modified: 2026-09-17
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Roadmap

> README.md and other docs point here rather than maintaining their own lists.

## Completed

Implementation detail for each item below (design decisions, function
names, PR links) lives in `working-docs/implementation/` where noted --
read the code/that doc for current state rather than this list, which
is not kept in sync with post-ship changes.

- [x] SPDX 3.0 SBOM generation (JSON-LD)
- [x] Hatchling metadata extraction (`pyproject.toml`)
- [x] Dependency tracking and SPDX relationship elements
- [x] Format-neutral internal representation
  (`DocumentModel` -- see [format-neutral-representation.md](format-neutral-representation.md))
- [x] AI/ML package profiles
  (`software_Package` with AI BOM profile, `dataset_DatasetPackage`)
- [x] PEP 770 support (`.dist-info/sboms/` via `build_data["sbom_files"]`)
- [x] Hatchling build hook (`pitloom.plugins.hatch`) with fragment merging
- [x] ML tracking SDK (`pitloom.loom` -- context manager / decorator)
- [x] Metadata provenance tracking (per-field source attribution)
- [x] CLI (`loom`) with verbose mode and creator info options
- [x] Setuptools support -- initial implementation
  (`src/pitloom/extract/project/setuptools.py`; `pyproject.toml` > `setup.cfg` >
  `setup.py` conflict resolution)
- [x] Poetry support -- initial implementation
  (`src/pitloom/extract/project/poetry.py`; `read_pyproject()` falls back to
  `[tool.poetry]` when `[project]` is absent, merges both when present)
- [x] **PDM-backend and Flit-core support** -- metadata extraction
  (`src/pitloom/extract/project/pdm.py`, `flit.py`: dynamic `version`/
  `description` resolved via each backend's own logic --
  `[tool.pdm.version]`'s `file`/`scm` sources, Flit's module
  `__version__`/docstring convention) and wheel file discovery
  (`src/pitloom/core/_models_wheel_pdm.py`, `_models_wheel_flit.py`),
  wired into `read_pyproject()` and `_models_wheel_dispatch.py`'s
  `backend_discoverers` registry. See
  [backend-file-discovery-validation.md](../implementation/backend-file-discovery-validation.md)'s
  Flit-core/PDM-backend round.
- [x] **Multiple creators / tools per `CreationInfo` record** -- `Creator`/
  `Tool` dataclasses, repeatable `--creator-name`/`--creation-tool`,
  array-of-tables config. See [creation-metadata.md](../../docs/creation-metadata.md).
- [x] **SPDX license expression normalization and declared-vs-detected
  conflict detection (G2)** -- via [`py-spdx-license`](https://github.com/JPEWdev/py-spdx-license).
  See [multi-source-conflict.md](../implementation/provenance/multi-source-conflict.md)
  ([PR #121](https://github.com/bact/pitloom/pull/121)).
- [x] **`[project.license-files]` support** -- PEP 639's glob-list field
  for bundling multiple license files. `ProjectMetadata.license_files`
  (resolved by `pyproject_metadata`/Hatchling, not re-globbed by Pitloom);
  each entry gets a `software_File` element at the real wheel's
  `<name>-<version>.dist-info/licenses/<path>` and a `hasDeclaredLicense`
  relationship, deduped against the package-level license element. See
  [license-pipeline.md](../implementation/license-pipeline.md#license-files-bundling-pep-639).
- [x] **Auto-sync the Loom ID registry after SBOM generation** -- `loom
  project`/`wheel`/`env` harvest newly-minted ids back into the resolved
  registry after each run. `ai_AIPackage`/`dataset_DatasetPackage`
  deliberately excluded -- see
  [Loom IDs across fragments](../../README.md#loom-ids-across-fragments-pitloom-ids).
  Open follow-ups: [AI model id stability](#ai-model-id-stability-follow-up-to-178),
  [Sort-order canonicalization](#sort-order-canonicalization-follow-up-to-178)
  below. ([PR #178](https://github.com/bact/pitloom/pull/178))
- [x] **Lock/pin formats as a resolved-dependency source** -- `poetry.lock`,
  `pylock.toml` (PEP 751), `uv.lock`, `pdm.lock`, `Pipfile.lock`, and pinned
  `requirements.txt` feed `locked_dependencies` via one shared cascade
  ([#208](https://github.com/bact/pitloom/pull/208)). See
  [lock-file-cascade.md](../implementation/lock-file-cascade.md).

## 1.0 target (2026-10-15)

Goal: ship 1.0 within one month (by mid-October 2026). GitHub milestone
`1.0.0` already exists (no issues attached yet, no due date set). This
is a **stability/quality release, not a feature release** -- the core
mission (SBOM generation across every major Python build backend, lock
formats, AI/ML profiles, PEP 770 embedding, provenance tracking) is
already feature-complete per [Completed](#completed) above. What's
missing for 1.0 is proof it holds up outside the one environment
(Linux, one developer) it's been built and tested in, plus closing a
couple of correctness/consistency gaps found along the way. One
developer working with an AI pairing agent, ~1 month -- scope is
deliberately narrow; anything not listed below is explicitly **not**
1.0 scope (see "Cut from 1.0" at the end).

| # | Item | Priority | Impact | Size | Status |
| :-- | :--- | :--- | :--- | :--- | :--- |
| 1 | [Real Windows CI run](#testing--ci) | P0 | High | S-M | Done -- CI added ([PR #220](https://github.com/bact/pitloom/pull/220)), fixed test fixtures it exposed |
| 2 | [Real macOS CI run](#testing--ci) | P0 | High | S | Done -- CI added ([PR #220](https://github.com/bact/pitloom/pull/220)) |
| 3 | [`--allow-build` timeout](#medium-term) | P0 | High | S | Not started |
| 4 | [Versioning/compatibility policy decision](#versioning-and-compatibility-policy-new-for-10) | P0 | High | S | Needs a decision |
| 5 | [`loom fragment sign` + hash verification](#sbom-fragments-merge-system) | P1 | Medium | S | Not started |
| 6 | [Generic multi-candidate field representation](#metadata-quality) | P1 | Medium | S-M | Not started |
| 7 | [JAX/Orbax model extractor](#extractors) (stretch) | P2 | Medium | M | Not started |
| 8 | [Merge-policy doc](https://github.com/bact/pitloom/issues/150) (stretch) | P2 | Low | S | Not started |

**Why this order:**

1-2. **CI first, before anything else.** Everything else in this list
   risks a merge conflict or a re-review if CI turns up a real
   Windows/macOS bug mid-month; better to know the size of that problem
   in week 1 than discover it in week 4. Windows before macOS per the
   existing roadmap note (path-separator/tempdir issues are more likely
   on Windows; macOS is comparatively low-risk once Windows is clean).
   CLAUDE.md already commits to "seamlessly across Windows, macOS, and
   Linux" -- shipping 1.0 having only ever run on `ubuntu-latest` means
   that claim is untested, not true.
3. **`--allow-build` timeout**, right after CI is green. `--allow-build`
   shipped in 0.18.0 (PR #215) with a known hang risk (no escape hatch
   but Ctrl-C) already flagged in Medium-term below. A 1.0 release is
   when strangers start depending on default behavior not hanging
   forever; this is the one open correctness gap in already-shipped
   1.0-era code, so it goes first among the code fixes.
4. **Versioning/compatibility policy** needs deciding early, not at
   release time. CLAUDE.md currently states "no backward compat needed
   yet" (true for a private alpha); 1.0 conventionally signals a SemVer
   compatibility commitment starting from that tag. This is a decision
   for the maintainer, not something to infer -- worth resolving in week
   1 so it doesn't become a last-minute scramble, and so any breaking
   cleanup wanted "one last time before the compat clock starts" (e.g.
   CLI flag renames, if any are pending) has time to land before 1.0
   rather than after.
5-6. **Fragment CLI completion and generic multi-candidate fields** --
   both small, both independent of 1-4, both reduce visible
   inconsistency: `fragment list`/`fragment validate`/`FragmentConfig`
   already ship (2026-09-15/16), so `fragment sign` closes out a
   subcommand family that would otherwise look half-finished in a 1.0
   release; the multi-candidate refactor removes a duplication pattern
   before more call sites (a 1.0-era feature freeze makes call sites
   longer-lived, so cheaper to fix now than after 1.0).
7-8. **Stretch, cut first if the schedule slips.** JAX/Orbax is a real
   feature addition (not a stability fix) with a ready design -- include
   only if 1-6 land with time to spare. The merge-policy doc is small
   and safe to defer to a 1.0.1/1.1 doc pass without affecting the
   release itself.

### Versioning and compatibility policy (new for 1.0)

Not yet decided -- flagging as a required 1.0 decision, not proposing
an answer. Questions to resolve before the 1.0 tag:

- Does 1.0 commit to CLI-flag/output-format/library-API stability under
  SemVer (breaking changes only at a major version bump), replacing
  CLAUDE.md's current "no backward compat needed yet"?
- If so, which surfaces are covered by that commitment -- CLI flags and
  output shape, the public library API (`generate_project_sbom()` etc.),
  the Hatchling build hook's `[tool.pitloom]` config schema, the GitHub
  Action's inputs, the Skills/plugin surfaces -- and are they all
  covered from 1.0.0, or staggered (e.g. CLI stable at 1.0, library API
  marked experimental until 1.1)?
- Any deliberately breaking cleanup that should land *before* 1.0 while
  compat is still free, rather than waiting for a 2.0? (No specific
  candidate identified in this pass -- worth a deliberate check, not an
  assumption that none exists.)

### Cut from 1.0 (explicitly deferred)

Named here so scope doesn't creep back in mid-month: OSV.dev
vulnerability lookup, CycloneDX assembler and any other output format,
`pixi.lock`/`conda-lock.yml` support, MLflow/W&B Weave/DVC fragment
extractors and SBOM-fragments Phases 2-4, SARIF output, SCITT
integration, PEP 740 attestations, remote source ingestion
(`loom project <url>`), AI model id stability (auto-harvest), the
provenance/enrichment vocabulary revision (blocked on its own taxonomy
decision), internal codename retirement, and the ~25 other open
`enhancement`-labelled GitHub issues not named in the table above. All
stay on the roadmap; none block 1.0.

## Adoption surfaces

Pitloom's other surfaces (library API, CLI, Hatchling build hook, ML
tracking SDK) all assume the consumer already has Pitloom installed or
wired into a build backend. These two extend reach beyond that. See
[adoption-surfaces.md](../implementation/adoption-surfaces.md) for the
full picture.

- [x] **GitHub Action** (composite `action.yml`) -- generate an SBOM in CI
  with a single `uses:` line, for any Python project regardless of build
  backend. See [github-action.md](../implementation/github-action.md).
- [x] **AI-agent Skills** (`skills/sbom-generate/`, `skills/sbom-enrich/`,
  `skills/sbom-validate/`) -- generate/enrich/validate an SBOM on
  request from Claude Code, the Claude Agent SDK, or similar runtimes.
  See [agent-skill.md](../implementation/agent-skill.md) and
  [sbom-enrichment.md](sbom-enrichment.md).
- [x] **Claude Code plugin** (`.claude-plugin/`) -- bundles all three
  Skills under the `pitloom` plugin namespace (`/plugin install`,
  `/pitloom:sbom-generate` etc). See
  [claude-code-plugin.md](../implementation/claude-code-plugin.md).
- [ ] **Docker container action** (future) -- a `Dockerfile` +
  `action.yml` `using: docker` variant of the GitHub Action for hermetic
  or self-hosted-runner use.
- [ ] **SARIF output** -- emit a SARIF file as a build artifact for CI
  findings (inline PR annotations, Security-tab view), fed by
  `WARNING:`/`ERROR:` output, OSV.dev results (once built), and license
  conflicts. See [sarif-output.md](sarif-output.md).

## Near-term

**Next up:**
[Generic multi-candidate field representation](#metadata-quality) --
[Non-Hatchling file discovery](#non-hatchling-file-discovery-feature-parity)
below is now closed for every backend, including `uv_build` (via the
generic `--allow-build` build-and-read mechanism, not a dedicated static
rescan -- see below).

**Suggested sequencing after that** (2026-09-16, not a commitment --
superseded for the next month by [1.0 target](#10-target-2026-10-15)
below, which is the actual commitment for what ships before mid-October):

1. [Generic multi-candidate field representation](#metadata-quality)
   -- now concretely motivated: license (`deps_license.py`), dependency
   version (`deps_installed.py`), and project metadata fields
   (`extract/project/installed.py`, landed via
   [installed-dist-info-source.md](installed-dist-info-source.md)) each
   hand-build their own `ConflictCandidate` list at their own call
   site -- a third, independent instance of the same duplication is
   usually the right time to generalize.
2. [JAX/Orbax model extractor](#extractors) -- design ready (verified
   against real `orbax-checkpoint` output, not docs alone), independent
   of the item above.
3. [OSV.dev vulnerability lookup](#metadata-quality) -- **not** ready to
   hand to an implementer as-is; needed its own design pass first (SPDX3
   mapping, which dependency pool to query, PEP 440-based range
   matching) -- now resolved, see
   [osv-vulnerability-lookup.md](osv-vulnerability-lookup.md#resolving-the-three-open-design-gaps-2026-09-14).
   Explicitly **not** in the 1.0 scope below -- too large to design,
   build, and review in the time remaining alongside everything else.

### Non-Hatchling file discovery (feature parity)

- [x] **`get_wheel_files()` file discovery is not backend-agnostic** --
  closed (2026-09-15): setuptools, Poetry, PDM-backend, and Flit-core
  each have a dedicated static rescan module; `uv_build` (and any other
  backend with no static module, or whose static discovery fails)
  resolves via a new generic, backend-agnostic build-and-read mechanism
  gated behind `--allow-build` (real PEP 517 build, opt-in, no
  `[tool.pitloom]` equivalent -- see [`docs/cli.md`](../../docs/cli.md#building-a-project-to-discover-its-file-list---allow-build)).
  Track B (compiled/native backends: `maturin`, `scikit-build-core`,
  `meson-python`) is already covered by the same mechanism once their
  own toolchain happens to be available -- no further Pitloom code
  needed. See [non-hatchling-file-discovery.md](non-hatchling-file-discovery.md)
  for the full design/history.
- [ ] **Five smaller follow-ups from PR #215's `--allow-build` review**
  -- two consolidation/dedup cleanups (a duplicated blanket-except
  pattern across Track A modules; a hand-rolled `tool` table walk
  repeated across 6+ modules), one low-priority dev-script dedup, one
  id-registry gap (`--allow-build`-sourced files can't match a
  `loom ids generate`-pinned entry, since their `physical_path` is an
  ephemeral temp path -- **partially addressed** 2026-09-15: a separate,
  previously-unguarded AI-model registry lookup in `_ai_package.py` was
  found and fixed, but `_document_files.py`'s own `software_File` lookup
  still needs the harder fix described below), and one precision gap (a
  real static `uv_build` discoverer for `[tool.uv.build-backend]`, to
  stop the Hatchling fallback from over-including or, worse,
  zero-including files for some real packages -- already
  `WARNING:`-flagged, not silent). None block shipped work; each is
  independently fixable. See
  [non-hatchling-file-discovery.md](non-hatchling-file-discovery.md#open-follow-up-tech-debt-from-pr-215s---allow-build-review)
  for full detail on each.

### Build backend improvements

- [ ] **PEP 517 `prepare_metadata_for_build_wheel`** (opt-in) -- call the build
  backend in a subprocess to resolve dynamic metadata (Git-tag versions,
  computed deps) that static parsing cannot handle.
  See [metadata-sources.md](metadata-sources.md).
- [x] **Setuptools wheel file discovery** -- setuptools' own official
  config-resolution API (`setuptools.config.pyprojecttoml`/`setupcfg`)
  and `build_py` introspection now resolve a setuptools project's file
  set from static config, instead of Hatchling's `WheelBuilder`. See
  [setuptools-support.md](../implementation/setuptools-support.md) and
  [sbom-lifecycle-stages.md](../implementation/sbom-lifecycle-stages.md).
- [x] **`get_wheel_files()` option to skip Merkle root computation** --
  `embed-wheel`'s one caller now skips per-file hashing entirely. See
  [get-wheel-files-skip-merkle-root.md](../implementation/get-wheel-files-skip-merkle-root.md).
- [x] **In-tree `.egg-info`/`.dist-info` as a supplementary metadata
  source** -- an editable-install byproduct left next to
  `pyproject.toml` gap-fills undeclared fields; static source stays
  authoritative on conflict (recorded, never silently substituted).
  See [installed-dist-info-source.md](installed-dist-info-source.md).
- [x] **Unify `extract/project/installed.py`'s RFC 822 Core-Metadata
  parser with `extract/wheel.py`'s** -- closed (2026-09-15, PR #215):
  widened to all four sites found with the same duplicated
  `Project-URL`-splitting shape (`wheel.py`, `installed.py`, `sdist.py`,
  `deps_originator.py`), consolidated into one parametrized
  `extract/_core_metadata.py::parse_project_urls()`. See
  [installed-dist-info-source.md](installed-dist-info-source.md#relationship-to-extractwheelpys-parser).
- [ ] **Real installed `.dist-info` (site-packages) as a metadata
  source** -- the deferred, backend-agnostic phase: a user-supplied
  venv/site-packages path, cross-checked via `direct_url.json`.
  See ["Deferred: real installed dist-info (site-packages)"](installed-dist-info-source.md#deferred-real-installed-dist-info-site-packages).
- [x] **Split `extract/project/installed.py`** -- closed (2026-09-15,
  PR #215): discovery+parsing stayed in `installed.py` (now ~340 lines);
  reconciliation moved to the sibling `_installed_reconcile.py`, exactly
  the seam previously identified.
- [ ] **`resolve_project_with_lockfile()`'s peek/reread pays for
  installed-metadata discovery twice** (once per `read_project()` call)
  when the lock cascade is auto-detected. Already an accepted,
  documented cost; a fix needs care -- the peek's own read may be
  load-bearing for surfacing errors the quiet re-read wouldn't catch on
  its own, so any change here needs a closer look at that ordering
  before changing it, not a quick patch.
- [x] **CLI option `--no-use-lockfile`** -- opt-out flag (also
  `[tool.pitloom] use-lockfile = false`) disabling automatic lock-file
  discovery across every usage surface; on by default. Also fixed a
  related `loom enrich` doc-identity bug found along the way.
  See [lock-file-cascade.md](../implementation/lock-file-cascade.md#--no-use-lockfile-opt-out).
- [x] **Preserve lock file hashes in `--offline` mode** -- SHA-256 digests
  parsed from `pylock.toml`/`uv.lock`/`poetry.lock`/`pdm.lock`/`Pipfile.lock`
  now populate SPDX 3 `verifiedUsing`, taking priority over a PyPI JSON API
  lookup even online.
  See [lock-hash-preservation.md](../implementation/lock-hash-preservation.md).
- [ ] **SHA-512 / BSI TR-03183-2 `verifiedUsing`** -- no lock format or the
  PyPI JSON API carries a SHA-512 digest; producing one means downloading the
  artifact and hashing it, a heavier feature than the SHA-256 lock-hash
  preservation above. `Element.verifiedUsing`'s 0..* cardinality means this
  can append to the same list without restructuring it.
  See [lock-hash-preservation.md](../implementation/lock-hash-preservation.md#scope).
- [ ] **Transitive dependency resolution and lock-hash support in Hatchling build hook** --
  gather transitive dependencies down the n-level dependency tree during build-stage
  hook execution to resolve dependencies and obtain integrity hashes, populating
  `verifiedUsing` in embedded build SBOMs without relying on source-stage lock files.
- [ ] **`pixi.lock` and `conda-lock.yml` as resolved-dependency sources** --
  the two lock-file phases the current cascade doesn't cover, for
  AI/ML stacks mixing PyPI wheels with Conda/CUDA binaries. See
  [lock-files.md](lock-files.md)'s Phase 2 -- its priority table and
  shipped-status notes are current, but its Pydantic/CycloneDX sketch
  predates and doesn't match this codebase's actual shape; follow
  `extract/lock/poetry.py` and `assemble/spdx3/deps.py`'s established
  pattern instead, as the doc itself now says.

### PEP 770 / embed-wheel

- [x] **`loom verify-wheel` / `loom validate-wheel`** ([#202](https://github.com/bact/pitloom/pull/202))
  -- structural location check and schema/SHACL content validation for
  a wheel's embedded SBOM, plus `embed-wheel --verify`/`--validate`
  convenience flags and a pre-embed name/version enforcement check for
  `--sbom`. See
  [wheel-verification-commands.md](../implementation/wheel-verification-commands.md).

### AI model id stability (follow-up to [#178](https://github.com/bact/pitloom/pull/178))

- [ ] **Deterministic same-model identification for auto-harvest** --
  `ai_AIPackage` elements are excluded from the Loom ID registry's
  auto-harvest since `ai_model.name` is extraction-dependent. Open
  design question: whether a content-hash match (narrower than "same
  model" for re-exported/re-quantized models) plus a non-identifying
  "machine ID" scoping tag could safely extend auto-harvest to AI
  models. No implementation direction chosen yet. See
  [ai-model-id-stability.md](ai-model-id-stability.md).

### Sort-order canonicalization (follow-up to [#178](https://github.com/bact/pitloom/pull/178))

- [x] **Audit where element/entry sort order feeds hash or id
  construction.** Every `sorted()`/`.sort()` call in the
  assemble/id-registry path audited; the one genuinely canonical
  (hash/id-affecting) key was renamed and documented as such, the
  non-canonical ones marked as not affecting output. No behavior
  changed. See
  [sort-order-canonicalization.md](../implementation/sort-order-canonicalization.md).

### Extractors

- [ ] **Additional AI model format extractors**
  - JAX (Orbax checkpoints) -- higher priority, design ready to
    implement: findings come from installing `orbax-checkpoint` and
    inspecting real output, not docs alone. See
    [jax-orbax-support.md](jax-orbax-support.md)
  - TensorFlow SavedModel and TensorFlow Lite
  - Scikit-learn (pickle/joblib; no single standard format -- complex)
  - See [model-metadata-extraction.md](model-metadata-extraction.md)
    for the full format table
- [ ] **MLflow run extractor** (`pitloom.extract.mlflow`,
  `loom.from_mlflow_run()`) -- reads a completed/active MLflow run's
  tags/params/metrics into an SPDX 3 AI BOM fragment, keyed against the
  [STAV](https://github.com/bact/stav) vocabulary with a fallback for
  non-STAV tag names; eliminates double-instrumenting a training script
  already using MLflow tracking. Fully designed, not yet built -- see
  [mlflow-extractor.md](mlflow-extractor.md). W&B Weave and DVC
  extractors are the same shape of gap; tracked together with this one
  under [SBOM fragments](#sbom-fragments-merge-system) below since all
  three feed the fragment-merge pipeline.
- [x] **Dataset-to-model relationship linking** -- `AiModelMetadata` carries
  dataset references (`DatasetReference`, `pitloom.core.dataset_metadata`);
  `add_datasets_for_model()` (`src/pitloom/assemble/spdx3/dataset.py`)
  emits `trainedOn`/`testedOn` `Relationship`s natively, falling back to
  `RelationshipType.other` + an explanatory comment for the three SPDX
  3.0.1 lacks (`finetunedOn`, `validatedOn`, `pretrainedOn`). Wired in from
  `assemble/spdx3/ai.py` and `_document_model.py`. See
  [sbom-enrichment.md](sbom-enrichment.md).
- [x] **Croissant dataset size calculation** -- `dataset_DatasetSize`
  extracted dynamically by summing `cr:totalItems` across `cr:recordSet`
  entries (or top-level `cr:totalItems`), with graceful `None` fallback.

### SBOM fragments (merge system)

`working-docs/design/sbom-fragments/` is a 5-file design cluster (index:
[README.md](sbom-fragments/README.md)) that was not linked from this
roadmap until 2026-09-15 -- re-verified against current code before
listing below, since parts of its Phase 1/4 plan turned out to already
be built:

- [x] **Core merge mechanism** -- `merge_fragments()`
  (`assemble/spdx3/fragments.py`) already does dedup, dangling-reference
  detection, unification annotations, and fragment-import tracking; the
  design cluster's "Phase 1 item 2" (`merge_fragments` rewrite) is
  substantially superseded by this. See
  [fragment-merge-design.md](sbom-fragments/fragment-merge-design.md)
  for the mechanism this implements, but read the module itself for
  current behaviour.
- [x] **`loom fragment validate`** -- already ships, already calls
  `spdx3_validate.validate()`'s library API directly as Phase 4 item 2
  specified (`cli/commands/fragment.py`).
- [x] **`FragmentConfig` dataclass** -- `PitloomConfig.fragments` is
  `list[FragmentConfig]` (`role`/`description`/`required`/`sha256`/
  `link-to-main`), backward-compatible with a plain-string loader
  (`core/_config_types.py`, `core/_config_parse.py`).
- [x] **`loom fragment list`** -- surfaces per-fragment status (existence,
  `@graph` element count, SHA-256 match) to developers
  (`cli/commands/fragment.py`).
- [ ] **`loom fragment sign` + SHA-256 verification in merge** --
  genuinely open; the SHA-256 hashing that already exists in
  `_fragments_unify.py` is for same-identity element dedup, not
  fragment-file integrity/tamper checking. `FragmentConfig.sha256` is
  currently display-only (`fragment list`), not enforced before merge.
- [ ] **Fragment-parse-path consolidation** -- `fragment list`'s
  per-fragment read/parse (`_fragment_read_status` in
  `cli/commands/fragment.py`) and `merge_fragments()`'s own read/parse
  (`assemble/spdx3/fragments.py`) are two independently-written code
  paths doing the same "open, JSON-parse, SPDX3-deserialize" job --
  `fragment list` calls `JSONLDDeserializer().deserialize_data()` on
  pre-parsed JSON (to avoid re-parsing bytes it already parsed for the
  SHA-256/element-count checks), `merge_fragments()` calls
  `JSONLDDeserializer().read()` directly on an open file handle. They
  agree today, but nothing keeps them in sync if either the deserializer
  library or one call site changes independently. A shared
  "read+parse+deserialize a fragment, return raw bytes and the SPDX3
  object set" helper would close this; deferred since it isn't a live
  bug and reworking it risks reintroducing the double-JSON-parse
  inefficiency the current split was built to avoid.
- [ ] **`merge_fragments()`'s required-fragment check short-circuits the
  dangling-reference check** -- a missing/unreadable `required=True`
  fragment raises `FragmentMergeError` before
  `_raise_on_dangling_references()` ever runs, even when other,
  successfully-merged fragments introduced a genuine, independent
  dangling reference. Deliberate today (root-cause-first: a missing
  required fragment is usually the cause of downstream dangling refs,
  per the comment in `merge_fragments()`), but means a build with both
  problems only ever reports one per run -- revisit if that turns out to
  cost real debugging time in practice.
- [ ] **`FragmentMergeError` propagates uncaught from the Hatchling build
  hook** -- `required=True` enforcement makes this reachable far more
  often than before (previously only the dangling-reference check could
  raise it from `plugins/hatch.py`'s `initialize()`, which has no
  `try/except` around `merge_fragments()`). A user hits a raw Python
  traceback through Hatchling's hook machinery instead of a clean
  message, unlike the CLI (`cli_error_handler`-wrapped `ERROR:` line).
  Matches existing precedent (`ValueError`/`RuntimeError` from config
  validation already propagate uncaught there the same way), so not a
  regression, but worth a dedicated `try/except FragmentMergeError` with
  a clean message if it turns out to bite users in practice.
- [ ] **`KEY=VALUE` CLI output has no quoting/escaping for values
  containing spaces** -- `pitloom fragment list`'s one-line-per-fragment
  output (`PATH=... ROLE=... REQUIRED=...`) space-separates its fields,
  so a fragment `path` containing a space (legal on all three supported
  platforms) breaks naive whitespace-based field splitting downstream
  (`awk '{print $1}'`-style consumers). Pre-existing risk, not introduced
  by this PR -- shared by every other space-separated `KEY=VALUE` line in
  the codebase (e.g. `scanner.py`'s `FORMAT=%s FILE=%s`). No quoting
  convention defined yet; pick one (shell-style quoting, JSON Lines
  output mode, etc.) if/when a real path-with-spaces bug report lands.
- [ ] **SDK ergonomics (Phase 2)** -- `log_param`/`log_metric`/`log_tag`
  on `_ActiveRun`, a fluent `add_dataset` builder, `log_evaluation`,
  persistent `loom.start_session()`/`end_session()`, an optional
  `%%pitloom_record` IPython cell magic. See
  [loom-sdk-and-notebooks.md](sbom-fragments/loom-sdk-and-notebooks.md).
- [ ] **New extractors (Phase 3)** -- W&B Weave and DVC extractors, plus
  an MLflow dataset-input addition once the base
  [MLflow extractor](#extractors) above exists. See
  [extractor-integrations.md](sbom-fragments/extractor-integrations.md).
- [ ] **Compliance/interop (Phase 4)** -- CycloneDX BOM-Link emission
  (blocked on the CycloneDX assembler under Medium-term) and a
  fragment `completeness` field (`complete`/`incomplete`/`unknown`)
  mapped to an SPDX `Annotation`. See
  [roadmap-and-resources.md](sbom-fragments/roadmap-and-resources.md).
- [ ] **Element-level fragment-merge traceability** -- document-level
  traceability (which fragment *files* contributed) shipped in
  [PR #108](https://github.com/bact/pitloom/pull/108); which
  *unification criterion* matched (same `spdxId` vs. content hash vs.
  structural equality) and which fragments a merged element's
  properties came from is not recorded in the output, only in a
  `log.warning`. Not planned to change without a native SPDX
  field-provenance construct -- see
  [roadmap-and-resources.md](sbom-fragments/roadmap-and-resources.md)
  for the full note.

### Metadata quality

- [ ] **Revise and publish the provenance/enrichment vocabulary reference**
  -- draft `docs/vocabulary.md` page reverted out of `docs/` pending a
  `role`/`method` taxonomy revision; once settled, publish and
  consolidate every place that documents this vocabulary ad hoc into
  one canonical source. See
  [provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md).
- [x] **Generalize multi-source conflict detection beyond license** --
  `build_conflict_annotation`/`ConflictCandidate` (already field-agnostic)
  now also fires for dependency version (declared specifier vs.
  lock-file-resolved version), each field's candidates still hand-built
  at its own assembly call site. See
  [multi-source-conflict.md](../implementation/provenance/multi-source-conflict.md).
- [ ] **Generic multi-candidate field representation** -- today each
  multi-source field (license, dependency version) hand-builds its own
  `ConflictCandidate` list at its own assembly call site; there's no
  shared type carrying a labeled candidate set (declared/detected/
  concluded, or a richer vocabulary such as BSI TR-03183's original/
  distribution/effective) from extraction through assembly, nor a shared
  per-field policy for "which roles map to which native SPDX relationship
  (if any) vs. Annotation-only." Worth designing once a third field needs
  this. See
  [generic-multi-candidate-fields.md](generic-multi-candidate-fields.md).
- [ ] **Enhanced dependency analysis** -- transitive dependencies, optional
  extras, development dependencies.
- [ ] **Auto-discover default license files when `[project.license-files]`
  is undeclared** -- setuptools' `_finalize_license_files()` and
  Hatchling's `CoreMetadata.license_files` both fall back to the same
  glob (`LICEN[CS]E*`, `COPYING*`, `NOTICE*`, `AUTHORS*`, citing the
  `wheel` package's own documented convention) and bundle whatever
  matches into a real wheel's `.dist-info/licenses/`, even with no
  explicit field. Pitloom's `resolve_license_file_entries()`
  (`src/pitloom/extract/_license.py`) deliberately does *not* replicate
  this today -- both extraction paths only trust an explicit
  `[project.license-files]` declaration (see
  [license-pipeline.md](../implementation/license-pipeline.md)'s
  "License-files bundling" section) --
  because the default glob is a build-backend auto-bundling convenience,
  not something PEP 639 itself defines, and because `NOTICE`/`AUTHORS`
  matches don't obviously belong under a `hasDeclaredLicense` relationship
  the way `LICENSE`/`COPYING` do. If this is picked up, it needs its own
  design pass: which stems to trust, whether it holds for every backend
  (only setuptools and Hatchling are confirmed so far), and a provenance
  label that clearly distinguishes "inferred default" from "explicitly
  declared."
- [x] **SBOM enrichment from external sources** (the `enrich/` subpackage)
  -- MVP shipped: local README/model-card YAML frontmatter parsing,
  gated by `[tool.pitloom] enrich` (default off). Code-level and
  deterministic -- distinct from the agent-facing `sbom-enrich` Skill
  above. Exposed across every generation surface (`loom enrich` CLI,
  `--enrich`/`--no-enrich` flags, Hatchling build hook, GitHub Action
  input). Still not started: OpenSSF Scorecard, Hugging Face Hub and
  PyPI metadata sources, per-source enable/disable config.
  See [sbom-enrichment.md](sbom-enrichment.md).
- [ ] **OSV.dev vulnerability lookup** (`--enrich-cve` or similar) -- static
  enrichment only (no exploitability judgement); VEX generation under
  Medium-term is the follow-on triage step. See
  [osv-vulnerability-lookup.md](osv-vulnerability-lookup.md).

### Remote source ingestion

- [ ] **Remote repository and forge ingestion (`loom project <url>`)** --
  generate SBOMs directly from remote git repositories/forges (GitHub, GitLab)
  or remote release archives, capturing upstream VCS provenance (commit SHA,
  tag, repo URL) and delegating parsing to `extract.project` and `extract.lock`.
  See [remote-source-ingestion.md](remote-source-ingestion.md).

### Testing / CI

- [x] **Real Windows and macOS CI runs** -- `test.yml`/`build.yml` now
  cover `windows-latest`/`macos-latest`, not just `ubuntu-latest`. The
  first Windows run immediately surfaced 7 real test failures (all
  test-fixture bugs, no production code changed). See
  [windows-macos-ci.md](../implementation/windows-macos-ci.md).
  ([PR #220](https://github.com/bact/pitloom/pull/220))
- [ ] **`fasttext` Windows/macOS + Python 3.14 gap untested** -- PR #220
  split the `fasttext` extra by `python_version` (`fasttext-community`
  for <3.14, plain `fasttext==0.9.3` for >=3.14, since
  `fasttext-community` caps its own `requires-python` at <3.14). Plain
  `fasttext==0.9.3` has no Windows wheel and fails building from source
  there (the exact bug #220 fixes for <3.14) -- but no CI matrix job
  combines Windows or macOS with Python 3.14, so this known gap stays
  silently untested. Revisit once `fasttext-community` adds 3.14
  wheels, or add a dedicated Windows/macOS + 3.14 job if that's slow to
  land.
- [ ] **CI workflow step duplication** -- the checkout / setup-python /
  pip-install boilerplate is hand-copied across 11 of the 17
  `.github/workflows/*.yml` files with no shared source, so a change to
  one (e.g. a cache key, a Python setup option) has to be repeated by
  hand in every file or silently drifts. (`licenseid update` is a
  narrower sub-case -- only `test.yml` and `action-selftest.yml` run it,
  not all 11.) Candidate fix: a local composite action
  (`.github/actions/setup-pitloom-ci/action.yml`) that each workflow's
  steps call instead of repeating the block. Not urgent -- flagged
  during a CI redundancy audit, no drift has caused a bug yet --
  but matches the "Consolidate Patterns" principle in CLAUDE.md.
  Deliberately kept out of PR #220's scope (a repo-wide CI refactor
  shouldn't land bundled with the first real Windows/macOS CI run) --
  do as its own follow-up PR once #220 is merged and stable.

### Diagnostics / logging

- [x] **Surface `DEBUG:`-level output on request** -- shipped both
  triggers rather than choosing one: a new top-level `--debug` flag
  (parsed before the subcommand, like `-V`; `cli/verbose.py`'s existing
  `--verbose` was left alone since it does something unrelated) and the
  `PITLOOM_DEBUG` environment variable, which also covers entry points
  that don't parse CLI flags themselves (the Hatchling build hook, every
  public library-API generator). `configure_logging(debug=...)`
  resolves `None` (every existing no-argument call site) against the
  env var; an explicit `True`/`False` (the CLI's `--debug`) wins outright.
  See `pitloom.logging_config`. ([PR #201](https://github.com/bact/pitloom/pull/201))
- [x] **Promote silent-data-loss `DEBUG:` messages to `WARNING:`** --
  18 messages across the HF Hub, PyTorch/PT2, fastText, README
  enrichment, and sdist extractors, plus `pitloom.loom` caller-provenance
  detection, now surface by default (not just under `--debug`) when a
  failure drops or degrades an SBOM/AIBOM field. Each names the affected
  field(s) via one shared, grep-able helper, `field_loss_suffix()`
  (`pitloom.logging_config`), instead of hand-duplicated suffix text per
  call site. ([PR #201](https://github.com/bact/pitloom/pull/201))

### Internal codenames

- [ ] **Retire the whole letter-number use-case codename taxonomy**
  (G1-G7, A1-A2, E1-E2, P1, N1-N6, and more -- 500+ occurrences as of
  2026-09-14), not just "G2" -- meaningful only against
  `use-case-catalog.md`'s own numbering, meaningless to a future reader
  in isolation. Sizeable, mechanical-but-not-trivial; an opportunistic
  path (fold into whichever `working-docs/*.md` a routine reorg already
  touches) exists alongside a dedicated-PR path. See
  [codename-retirement.md](codename-retirement.md).

## Medium-term

- [ ] **`--allow-build`'s real PEP 517 build has no timeout** --
  `build_and_read_wheel()` (`_models_wheel_build_and_read.py`) runs the
  isolated build synchronously inside `get_wheel_files()`'s
  single-threaded call chain, unlike `scripts/compare_allow_build.py`'s
  own 600s subprocess timeout for the same operation. Identified during
  PR #215's follow-up review. A hung build (slow/broken network fetch
  for build-requires, a build backend blocking on stdin, a misbehaving
  build script) blocks the whole `loom project`/`generate`/`embed-wheel`
  invocation indefinitely with no escape hatch but Ctrl-C -- a
  `--allow-build` user opted into running third-party build code, not
  into an unbounded hang. Needs a design decision before implementing:
  a hardcoded default timeout vs. a new `--build-timeout` flag, and what
  happens on timeout (warn-and-fall-back-to-Hatchling, matching every
  other build-and-read failure path, is the obvious default but should
  be confirmed).
- [ ] **CycloneDX assembler** -- add a CycloneDX serializer consuming the
  existing `DocumentModel`; no changes to extractors required.
- [ ] **AIDOC / TechOps renderer** -- additional output format consuming
  `DocumentModel`.
- [ ] **Build log extraction** -- capture compiled dependencies, linker flags,
  and bundled libraries from build output logs.
- [ ] **VEX (CSAF/OpenVEX) generation** -- consumes the OSV.dev lookup
  above (once it exists) to classify a component as affected/
  not_affected/fixed/under_investigation, rather than just listing raw
  CVE hits. Depends on the OSV enrichment item under Near-term /
  Metadata quality landing first. Open question: CSAF v2.0
  (ISO/IEC 20153:2025, OASIS-standardized, heavier, product-tree
  formalism, vendor-advisory-oriented) vs. OpenVEX (lighter JSON, the
  more common choice for tool-generated, non-vendor VEX) as the output
  format -- see
  [osv-vulnerability-lookup.md](osv-vulnerability-lookup.md#relationship-to-csafvex).

## Long-term

- [ ] **PEP 740 attestations** -- cryptographic signing and provenance
  tracking for generated SBOMs.
- [ ] **IETF SCITT integration** -- submit a generated SBOM as a signed
  SCITT statement to a transparency service (`loom scitt submit`),
  receive a receipt back as proof of registration; verify a
  dependency's own receipt on consume. Complementary to (not a
  replacement for) the PEP 740 item above. See <https://scitt.io/> and
  [scitt-integration.md](scitt-integration.md) for the receipt-placement
  decision, Pitloom's client-only role, and the tooling landscape.
- [ ] **Performance optimization** -- Rust backend for large-project log
  parsing; parallel file hashing. See
  [performance-optimizations.md](performance-optimizations.md#rust-backend--parallel-hashing).
- [ ] **Agentic skill governance (guardrail mode)** -- extend the
  existing AI-agent Skills (Adoption surfaces above) from "generate an
  SBOM on request" to "veto/flag a coding agent's own action" -- e.g.
  block or require override when an agent attempts to pull an unvetted
  Hugging Face model. Distinct capability from the current Skills:
  needs a hook into the calling agent's tool-use loop, not just a
  callable Skill.
- [ ] **Runtime reachability ("living SBOM")** -- evolve `loom env`
  (currently a static environment graph, see Market signals above)
  toward tracking which dependencies are actually loaded/executed at
  runtime (`sys.modules` introspection or eBPF), to suppress
  vulnerability noise from installed-but-unreachable code. Large scope
  -- needs its own design doc before estimating.
