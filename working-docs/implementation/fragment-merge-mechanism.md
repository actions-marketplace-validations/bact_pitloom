---
Created: 2026-09-17
Last-Modified: 2026-09-17
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Fragment merge mechanism (what actually shipped)

See also: [roadmap.md](../design/roadmap.md) (Near-term -- "SBOM
fragments (merge system)"),
[fragment-merge-design.md](../design/sbom-fragments/fragment-merge-design.md)
(the original, mostly-superseded design this documents the shipped
version of -- read this file, not that one, for current behaviour).

Split out of `roadmap.md` (2026-09-17) once this item's detail grew
past a summary.

## Core merge mechanism

`merge_fragments()` (`src/pitloom/assemble/spdx3/fragments.py`) already
does more than the original design cluster's "Phase 1 item 2"
(`merge_fragments` rewrite) asked for -- that item is substantially
superseded by what's actually here:

- Pre-merge validation and duplicate-ID detection via `_MergeIndex`.
- Dangling-reference detection (`_raise_on_dangling_references()`),
  raising `FragmentMergeError` when the merged graph is left
  referentially broken.
- Unification annotations (`_emit_unification_annotations()`) -- one
  `unification` Annotation per (survivor element, unification
  criterion), recording which fragments were folded into which
  survivor and by what matching rule (same `spdxId`, content hash, or
  structural equality).
- Fragment-import tracking (`_add_fragment_imports()`) -- populates
  `SpdxDocument.import_` with an `ExternalMap` per merged fragment
  document, giving document-level traceability of which fragment files
  contributed.

Also already shipped, matching the original design cluster's Phase 4
item 2 exactly: `loom fragment validate` calls
`spdx3_validate.validate()`'s library API directly
(`cli/commands/fragment.py`), not by shelling out to a CLI and parsing
stdout.

## Reading the code vs. this doc

This document summarizes shape and intent. For exact current behavior
(which properties are merged vs. skipped, the unification priority
order, error conditions), read `fragments.py` and
`_fragments_unify.py` directly -- this doc is not kept in lockstep with
every subsequent change to those modules.
