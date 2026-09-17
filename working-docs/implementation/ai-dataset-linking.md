---
Created: 2026-09-17
Last-Modified: 2026-09-17
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Dataset-to-model relationship linking

See also: [roadmap.md](../design/roadmap.md) (Near-term -- "Extractors"),
[sbom-enrichment.md](../design/sbom-enrichment.md) (the enrichment
design this feeds into).

Split out of `roadmap.md` (2026-09-17) once this item's detail grew
past a summary.

## What shipped

`AiModelMetadata` carries dataset references (`DatasetReference`,
`pitloom.core.dataset_metadata`). `add_datasets_for_model()`
(`src/pitloom/assemble/spdx3/dataset.py`) emits `trainedOn`/`testedOn`
`Relationship`s natively, falling back to `RelationshipType.other` plus
an explanatory comment for the three relationship types SPDX 3.0.1
itself lacks: `finetunedOn`, `validatedOn`, `pretrainedOn`.

Wired in from `assemble/spdx3/ai.py` and `_document_model.py`.
