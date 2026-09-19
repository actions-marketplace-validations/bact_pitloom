---
Created: 2026-09-17
Last-Modified: 2026-09-17
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Auto-sync the Loom ID registry after SBOM generation

See also: [roadmap.md](../design/roadmap.md) (Completed), the "Loom IDs
across fragments" section of the top-level [README.md](../../README.md#loom-ids-across-fragments-pitloom-ids).

Split out of `roadmap.md` (2026-09-17) once this item's detail grew
past a summary.

## What shipped ([PR #178](https://github.com/bact/pitloom/pull/178))

`loom project`/`wheel`/`env` harvest newly-minted spdxIds back into the
resolved id registry after each run, so a subsequent run against the
same project reuses the same ids for the same elements instead of
minting fresh ones.

`ai_AIPackage`/`dataset_DatasetPackage` elements are deliberately
excluded from auto-harvest -- their identity (`ai_model.name`) is
extraction-dependent, not a stable key the way a file path or a
dependency name/version pair is. Auto-harvesting them risks silently
pinning the wrong element under a name that later re-extracts
differently.

## Open follow-ups

- [AI model id stability](../design/ai-model-id-stability.md) -- the
  excluded `ai_AIPackage`/`dataset_DatasetPackage` case above; no
  implementation direction chosen yet.
- [Sort-order canonicalization](sort-order-canonicalization.md) -- a
  related audit of whether registry/hash construction depends on
  non-canonical sort order anywhere in the id-registry path.
