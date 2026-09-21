---
Created: 2026-09-20
Last-Modified: 2026-09-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Canonical output: names and key-order residue (follow-ups)

See also: [roadmap.md](roadmap.md) (entries) and "SBOM output" in
[CLAUDE.md](../../CLAUDE.md) (bit-for-bit determinism, RFC 8785, UTC).

Found during the PR #227 review. One principle: **the same input must give
the same bytes, and the same real-world thing must give the same identifier,
whatever the file format or surface.** Each item below is a policy first, then
one shared helper, then a test that runs every format/surface through it.

Sorted dict keys (for AI model metadata), UTC `Z` datetimes and LF line
endings were built in step 6.5 -- see
[sdist-own-config.md](../implementation/sdist-own-config.md). What is left:

## 1. Key-order residue

- **Not audited yet:** project-metadata sources (`pyproject.toml`,
  `setup.cfg`, lock files, installed metadata) for any dict/set emitted in
  source order.
- **Deliberately unsorted:** list-valued fields such as `inputs`/`outputs`
  (tensor or I/O names) keep the source order, which can be meaningful
  (ONNX I/O). Decide per field whether that order is semantic before
  sorting it.

## 2. One name-normalisation policy, across file types

- **Defect:** an AI model name with a space (`modelspec.title = "Stable
  Diffusion XL"`) becomes the id segment `AIPackage-{name}` unsanitised
  (`_ai_package.py`, `_document_model.py`), an invalid IRI that fails SHACL.
  `generate_spdx_id()` (`core/models.py`) also puts `doc_name` into the
  namespace (`spdxdocs/{doc_name}-{uuid}`) unsanitised, and is called from
  about 35 sites.
- **Policy to decide, for every named thing** (AI model, dataset, package,
  file, fragment): keep the *display* `name` faithful to the source, and derive
  the *identifier segment* deterministically (case, Unicode normalisation,
  which characters are percent-encoded or replaced, length). Package names
  already follow PEP 503 where compared; this extends one rule to the rest.
- **One helper** used by `generate_spdx_id()` (so all 35 sites inherit it),
  not a fix at each of the three AI sites.
- **Open questions:** does the Loom ID registry key on names (a change would
  re-mint ids, so it needs a migration or a compatibility rule)? Is the
  identifier segment lossy (two names colliding) and how is a collision
  broken deterministically?
- **Test:** a name table (spaces, non-ASCII, `#`/`/`/`?`, empty, very long)
  through every named-thing type, each result a valid IRI and validated with
  `spdx3-validate`.
