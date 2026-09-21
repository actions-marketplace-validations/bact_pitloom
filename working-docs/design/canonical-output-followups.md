---
Created: 2026-09-20
Last-Modified: 2026-09-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Canonical output: ordering, names, datetimes (immediate follow-ups)

See also: [roadmap.md](roadmap.md) (entries) and "SBOM output" in
[CLAUDE.md](../../CLAUDE.md) (bit-for-bit determinism, RFC 8785, UTC).

Found during the PR #227 review; all three are pre-existing and out of that
PR. Planned for the next PR. One principle: **the same input must give the
same bytes, and the same real-world thing must give the same identifier,
whatever the file format or surface.** Each item below is a policy first, then
one shared helper, then a test that runs every format/surface through it.

## 1. Sort metadata keys, for every format

- **Defect:** `safe_open().metadata()` returns keys in a different order on
  every call (six reads gave six orders, even with `PYTHONHASHSEED=0`).
  `extract/ai_model/safetensors.py` keeps that order in `properties`, so
  `ai_AIPackage.comment` differs run to run. The artifact-metadata Annotation
  is immune only because RFC 8785 sorts it.
- **Policy:** any dict-valued or set-like field an extractor emits is in
  canonical (sorted-by-key) order, decided once at a shared choke point
  (`record_dict_field_provenance()` in `extract/_extract_utils.py`, or the
  point where `ai_AIPackage` fields are assembled), not per format.
- **Do not stop at Safetensors.** Audit every reader in `extract/ai_model/`:
  `gguf.py` and `keras.py`/`hdf5.py` iterate `.items()` in file order, which is
  stable per file but not canonical (the same metadata written in another
  order gives different bytes); check `list(f.keys())` (tensor names) and
  every `fasttext`/`onnx`/`pytorch`/`numpy` list or dict the same way.
  Project-metadata sources (`pyproject.toml`, `setup.cfg`, lock files,
  installed metadata) get the same audit.
- **Test:** for each format fixture, permute the input key order (or read
  twice) and assert identical SBOM bytes; compare with `list(...)`, not dict
  equality, because dict equality ignores order.

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

## 3. UTC with `Z` for every datetime

- **Rule:** SPDX 3 `DateTime` is UTC, whole seconds, written with `Z`.
  `assemble/spdx3/creation_info.py` already has the helpers:
  `parse_iso_datetime()` (accepts `Z`, offsets, fractions; naive means UTC)
  and `to_spdx3_datetime()` (converts to UTC, drops microseconds).
- **Defect:** `assemble/spdx3/document.py:134` sets `builtTime` with a raw
  `datetime.fromisoformat()`, bypassing both. On Python 3.10 a pinned
  `creation-datetime` ending in `Z` (the form `docs/cli.md` shows) fails the
  whole Hatchling build; on any Python an offset form such as `+07:00` is not
  converted to UTC and keeps its fractions.
- **Fix:** route it through `parse_iso_datetime()` then `to_spdx3_datetime()`.
  Audit every other datetime input (`--creation-datetime`, config,
  `SOURCE_DATE_EPOCH`, file times, registry, fragments) for the same two calls.
- **Test:** `Z`, `+07:00`, naive, fractional seconds, on Python 3.10 and 3.14,
  through the CLI, the library API and the hook; every output ends in `Z`.

## 4. Enrichment `created` follows the document's datetime

- **Bug:** `build_enrichment_creation_info()` (`assemble/spdx3/creation_info.py`)
  sets `created=spdx3_utc_now()`, ignoring `--creation-datetime` and
  `SOURCE_DATE_EPOCH`, so any SBOM or `loom enrich` fragment with
  enrichment differs between two runs a second apart. Found in PR #231's
  review; pre-existing on `main`.
- **Fix:** pass the main `CreationInfo.created` in; update the docstring
  that calls it "the enrichment run's own timestamp (now)".
- **Test:** `project --enrich` and `enrich` twice with a pinned datetime,
  byte-identical.


## 5. `\n` line endings on every platform

- **Bug:** SBOM files are written in text mode (`Path.write_text()`), so a
  pretty SBOM gets CRLF on Windows and differs from the POSIX bytes for the
  same input. Seen in PR #231's Windows CI. Pre-existing.
- **Fix:** write with `newline="\n"` (or bytes) at every SBOM write site.
- **Test:** a pretty SBOM contains no `\r`, on the Windows leg.
