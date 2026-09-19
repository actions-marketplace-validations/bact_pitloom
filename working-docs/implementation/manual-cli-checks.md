---
Created: 2026-09-17
Last-Modified: 2026-09-17
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Manual CLI integration checks (post-pytest, pre-commit)

See also: [CLAUDE.md](../../CLAUDE.md) ("Testing" section -- short summary
and when to run these).

pytest exercises functions in-process. It does not exercise the `loom`
entry point, subprocess argv parsing, real filesystem/archive I/O across
subcommands, or drift between the CLI/library-API/Hatchling-hook/skills
surfaces (see "Usage surfaces" in CLAUDE.md). Run these by hand -- or have
an agent run them -- against a real project after any change touching
`assemble/`, `extract/`, `core/`, `embed.py`, `__main__.py`, or
`plugins/hatch.py`, before committing. Use a scratch dir (`mktemp -d`),
never the repo tree, for generated output.

**1. Determinism (bit-for-bit, per "SBOM output" in CLAUDE.md)**

```bash
loom project . -o /tmp/a.json --creation-datetime 2026-01-01T00:00:00Z
loom project . -o /tmp/b.json --creation-datetime 2026-01-01T00:00:00Z
diff /tmp/a.json /tmp/b.json && echo DETERMINISTIC
```

Re-run with `--pretty` and without; both must diff-clean against
themselves across repeats. A pinned `--creation-datetime` is required --
without it the `created` timestamp legitimately differs run-to-run.

**2. CLI vs library API vs Hatchling hook parity**

Three entry points must converge on the same document per project
(see "Metadata sources" in CLAUDE.md). Compare with the same pinned
`--creation-datetime`/`SOURCE_DATE_EPOCH` on all three, then diff the
`@graph` bodies (ignore `creationInfo.created`/tool-version fields that
legitimately vary by invocation):

```bash
loom project . -o /tmp/cli.json --creation-datetime 2026-01-01T00:00:00Z
python -c "
from pitloom.assemble.spdx3.document import build
from pitloom.extract.project import read_project
import json
doc = build(read_project('.'), creation_datetime='2026-01-01T00:00:00Z')
json.dump(doc, open('/tmp/api.json', 'w'), indent=2, sort_keys=True)
"
SOURCE_DATE_EPOCH=1767225600 python -m build --wheel -o /tmp/wheelout .
# hook-produced SBOM lands under .dist-info/sboms/ inside the built wheel
diff <(jq -S 'del(.["@graph"][] | select(.type=="CreationInfo"))' /tmp/cli.json) \
     <(jq -S 'del(.["@graph"][] | select(.type=="CreationInfo"))' /tmp/api.json)
```

**3. embed-wheel vs standalone `wheel` SBOM parity**

`embed-wheel` (project-dir-aware) and `wheel --embed` (wheel-only) must
embed an equivalent SBOM for the same wheel -- this is the class of gap
`--debug` fell into (one surface updated, sibling surfaces not):

```bash
python -m build --wheel -o /tmp/wheelout .
cp /tmp/wheelout/*.whl /tmp/wheelout/copy.whl
loom embed-wheel /tmp/wheelout/*.whl --project-dir . --sbom-basename a
loom wheel /tmp/wheelout/copy.whl --embed --sbom-basename a
unzip -p /tmp/wheelout/*.whl '*.dist-info/sboms/a*' > /tmp/embedded.json
unzip -p /tmp/wheelout/copy.whl '*.dist-info/sboms/a*' > /tmp/standalone.json
diff <(jq -S 'del(.["@graph"][] | select(.type=="CreationInfo"))' /tmp/embedded.json) \
     <(jq -S 'del(.["@graph"][] | select(.type=="CreationInfo"))' /tmp/standalone.json)
```

**4. Round trip: embed -> verify -> validate**

```bash
loom embed-wheel /tmp/wheelout/*.whl --verify --validate
loom verify-wheel /tmp/wheelout/*.whl --fail-on-mismatch
loom validate-wheel /tmp/wheelout/*.whl
```

**5. `--debug`/`PITLOOM_DEBUG` reaches every subcommand and every
non-CLI entry point** (see "Usage surfaces" in CLAUDE.md -- exactly the
bug class that motivated this check):

```bash
for sub in generate project wheel embed-wheel model enrich env merge fragment ids; do
  echo "=== $sub ==="
  loom --debug "$sub" --help >/dev/null 2>&1  # smoke: flag parses on every subcommand
done
PITLOOM_DEBUG=1 loom project . -o /tmp/dbg.json 2>&1 | grep -c '^DEBUG:' # expect >0
```

**6. Skills/plugin surface drift** (`skills/*/SKILL.md` has no test
suite -- see "Usage surfaces" in CLAUDE.md): grep each `SKILL.md` for
flags and subcommand names it documents invoking, then confirm each
still exists:

```bash
grep -n -- '--[a-z-]\+\|loom [a-z-]\+' skills/*/SKILL.md
loom <subcommand> --help  # for each one named above
```

**7. Fragment merge determinism** (dynamic-execution / `pitloom.loom` path):

```bash
loom merge /path/to/fragments/ -o /tmp/m1.json
loom merge /path/to/fragments/ -o /tmp/m2.json
diff /tmp/m1.json /tmp/m2.json && echo DETERMINISTIC
loom fragment validate /tmp/m1.json
```

**8. Offline mode has zero network calls**: run any AI-model-involving
command under a network sandbox/firewall (or `strace -e network` /
Little Snitch) with `--offline` and confirm no outbound connections,
vs. confirming at least one occurs without `--offline` against a
Hugging Face Hub URL.

**9. Registry round trip**: `loom ids generate` on a project, then
regenerate the SBOM with `--registry` pointing at that file and confirm
IDs are stable (byte-identical `@id` values) across repeated runs --
this is what "Auto-sync the Loom ID registry" in `roadmap.md` depends on.

**10. `--allow-build` with vs. without, and vs. ground truth**: general
pattern for any change touching backend file-discovery dispatch or the
build-and-read mechanism -- run `loom project` twice (with/without
`--allow-build`) against the same project and diff the `software_File`
results; a registered backend whose static discovery already succeeds
must produce byte-identical output either way (a real build must never
run then), and for a backend with no static module the two runs show
exactly what the heuristic fallback gets wrong relative to a real
build. Automated as `scripts/compare_allow_build.py` (works against a
project directory, an sdist archive, or a vendored fixture via
`--fixture BACKEND/NAME`; cross-checks against a fixture's own
`expected.json` when one exists) -- see
[allow-build-validation.md](allow-build-validation.md)'s
"`--allow-build` build-and-read" round for a worked example and
`scripts/compare_allow_build.py`'s own docstring for usage.
