# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Config values reach the SBOM assembler identically on every surface.

``content_type_method`` and ``provenance.max_source_metadata_bytes`` are
resolved from the CLI flag / library override / ``[tool.pitloom]`` cascade
by each surface, then handed to ``pitloom.assemble.spdx3.document.build()``.
Each surface writes that hand-off itself, so one can drop a value the
others keep -- ``embed-wheel`` did, and its own scan honoured the value
while the assembler silently used the default.

The seam observed here is ``add_dependencies()``, the one function every
surface's ``build()`` call ends in, so the spy needs no per-surface import
site and survives a refactor of the hand-off.

See also:
- :mod:`tests.assemble.test_embed_overrides` for ``_apply_config_overrides``.
- :mod:`tests.test_build_flag_warnings` for the surface x target matrix this
  module's runners are modelled on.
"""

from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble.spdx3 import document as spdx3_document
from pitloom.assemble.spdx3.deps import add_dependencies
from pitloom.core._config_types import AssembleOptions
from pitloom.core.config import PitloomConfig
from pitloom.core.provenance import ProvenanceConfig
from pitloom.embed import ConfigOverrides, _apply_config_overrides, embed_wheel_sbom
from tests.assemble.conftest import _make_dummy_wheel
from tests.assemble.embed_surfaces_shared import (
    RUNNERS,
    cli_embed,
    config_toml,
    demo_project,
    hatch_hook,
    run_cli,
)


class _Recorded:
    """The ``add_dependencies()`` calls one surface run made."""

    def __init__(self, calls: list[dict[str, Any]]) -> None:
        self.calls = calls

    def method(self) -> str:
        methods = {c["content_type_method"] for c in self.calls}
        assert len(methods) == 1, methods
        return str(methods.pop())

    def max_bytes(self) -> int:
        sizes = {c["provenance_config"].max_source_metadata_bytes for c in self.calls}
        assert len(sizes) == 1, sizes
        return int(sizes.pop())


@pytest.fixture(name="calls")
def _calls_fixture(monkeypatch: pytest.MonkeyPatch) -> _Recorded:
    calls: list[dict[str, Any]] = []

    def _spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return add_dependencies(*args, **kwargs)

    monkeypatch.setattr("pitloom.assemble.spdx3.document.add_dependencies", _spy)
    return _Recorded(calls)


_METHOD_CASES = [
    # (config value, override, expected effective method) -- one tuple
    # parameter keeps each test under the argument-count ceiling.
    pytest.param((None, None, "auto"), id="nothing-given"),
    pytest.param(("extension", None, "extension"), id="config-only"),
    pytest.param((None, "extension", "extension"), id="override-only"),
    # An explicit override equal to the built-in default must still win.
    pytest.param(("extension", "auto", "auto"), id="override-default-beats-config"),
    pytest.param(("auto", "extension", "extension"), id="override-beats-config"),
]


@pytest.mark.parametrize("surface", sorted(RUNNERS))
@pytest.mark.parametrize("case", _METHOD_CASES)
def test_content_type_method_reaches_assembler(
    surface: str,
    case: tuple[str | None, str | None, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    calls: _Recorded,
) -> None:
    """Every surface resolves the same cascade and hands the winner on."""
    config, override, expected = case
    RUNNERS[surface](tmp_path, monkeypatch, config_toml(config, None), override, None)
    assert calls.calls, "surface never reached the assembler"
    assert calls.method() == expected


@pytest.mark.parametrize("surface", ["lib-embed_wheel_sbom", "cli-embed-wheel"])
@pytest.mark.parametrize(
    "case",
    [
        pytest.param((None, 5000, 5000), id="override-only"),
        pytest.param((7000, None, 7000), id="config-only"),
        pytest.param((7000, 5000, 5000), id="override-beats-config"),
    ],
)
def test_embed_max_source_metadata_bytes_reaches_assembler(
    surface: str,
    case: tuple[int | None, int | None, int],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    calls: _Recorded,
) -> None:
    """The byte cap set on ``embed-wheel`` is not lost between the override
    and the assembler (``_apply_config_overrides`` copied four of the five
    ``ProvenanceConfig`` fields)."""
    config, override, expected = case
    RUNNERS[surface](tmp_path, monkeypatch, config_toml(None, config), None, override)
    assert calls.max_bytes() == expected


def test_hatch_hook_reads_method_from_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Recorded
) -> None:
    """Guards the assertion above against a vacuous pass for the hook: its
    only input is the config file, and a non-default value must arrive."""
    hatch_hook(tmp_path, monkeypatch, config_toml("extension", 4321), None, None)
    assert (calls.method(), calls.max_bytes()) == ("extension", 4321)


def test_embed_batch_passes_method_for_every_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Recorded
) -> None:
    """One ``EmbedFileCache`` batch: the method reaches each wheel's build,
    not just the first (the cache holds per-batch state)."""
    project = demo_project(tmp_path, config_toml("extension", None))
    wheels = [
        _make_dummy_wheel(tmp_path / f"dist{i}", "demo", "1.0.0") for i in range(2)
    ]
    run_cli(
        [
            "embed-wheel",
            *map(str, wheels),
            "--project-dir",
            str(project),
            "--offline",
        ],
        monkeypatch,
    )
    assert len(calls.calls) >= 2, "expected one assembler run per wheel"
    assert calls.method() == "extension"


# "" is falsy but not None: an ignored empty override would silently fall
# back to the config value instead of being rejected.
@pytest.mark.parametrize("method", ["mimetypes", ""])
def test_embed_rejects_invalid_method_before_assembling(
    method: str, tmp_path: Path, calls: _Recorded
) -> None:
    project = demo_project(tmp_path)
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
    with pytest.raises(ValueError, match="content_type_method must be one of"):
        embed_wheel_sbom(
            wheel,
            project_dir=project,
            overrides=ConfigOverrides(content_type_method=method),
        )
    assert not calls.calls


def test_embed_sbom_bytes_are_deterministic_with_method(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Recorded
) -> None:
    """Two embeds under the same non-default method give identical bytes.
    Offline, the method changes no output (see the module docstring), so
    this only guards against the hand-off adding run-to-run variation."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    outputs = []
    for run in ("a", "b"):
        base = tmp_path / run
        project = demo_project(base, config_toml("extension", None))
        wheel = _make_dummy_wheel(base / "dist", "demo", "1.0.0")
        _, _, sbom_json, _, _ = embed_wheel_sbom(
            wheel,
            project_dir=project,
            overrides=ConfigOverrides(offline=True),
        )
        outputs.append(sbom_json)
    assert {c["content_type_method"] for c in calls.calls} == {"extension"}
    assert outputs[0] == outputs[1]


def test_too_small_byte_cap_warns_once_and_reaches_assembler_as_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    calls: _Recorded,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``embed-wheel --max-source-metadata-bytes 1`` goes through the same
    normalisation as its siblings: one ``WARNING:``, then 0 (no cap). The
    config carries a non-zero cap, so 0 can only come from the flag."""
    cli_embed(tmp_path, monkeypatch, config_toml(None, 7000), None, 1)
    warnings = [
        line
        for line in capsys.readouterr().err.splitlines()
        if "max-source-metadata-bytes" in line
    ]
    assert len(warnings) == 1, warnings
    assert warnings[0].startswith("WARNING: ")
    assert calls.max_bytes() == 0


def _every_field_non_default(prov: ProvenanceConfig) -> ProvenanceConfig:
    """*prov* with every field changed away from its default."""
    changed: dict[str, Any] = {}
    for f in dataclasses.fields(prov):
        value = getattr(prov, f.name)
        changed[f.name] = value + 1 if isinstance(value, int) else f"{value}-x"
    return dataclasses.replace(prov, **changed)


def test_apply_config_overrides_round_trips_every_provenance_field() -> None:
    """A field added to ``ProvenanceConfig`` but not copied by
    ``_apply_config_overrides`` fails here, whatever its name."""
    prov = _every_field_non_default(ProvenanceConfig())
    assert all(
        getattr(prov, f.name) != getattr(ProvenanceConfig(), f.name)
        for f in dataclasses.fields(prov)
    ), "the input must differ from the default in every field"

    overridden = _apply_config_overrides(
        PitloomConfig(), ConfigOverrides(provenance=prov)
    )
    assert overridden.provenance == prov


def test_assemble_options_mirror_the_config() -> None:
    """Each key carries its own config value (all non-default, so a key
    wired to the wrong source cannot pass by coincidence)."""
    cfg = PitloomConfig(
        provenance_detail="full",
        provenance_max_source_metadata_bytes=999,
        offline=True,
        content_type_method="extension",
    )
    options = cfg.assemble_options
    assert options["provenance"] == cfg.provenance
    assert options["provenance"] != ProvenanceConfig()
    assert options["offline"] is True
    assert options["content_type_method"] == "extension"


# build() parameters a caller supplies per call, not from [tool.pitloom].
_PER_CALL_BUILD_PARAMS = frozenset(
    {"doc", "merkle_root", "sbom_type", "registry", "enrichment_results_by_model"}
)


def test_every_build_parameter_is_classified() -> None:
    """A new ``build()`` parameter must be added to ``AssembleOptions`` (a
    config-sourced setting) or to ``_PER_CALL_BUILD_PARAMS`` (supplied per
    call) -- the converse of the drift this module guards, where a surface
    keeps a setting the shared hand-off never learned about."""
    build_params = set(inspect.signature(spdx3_document.build).parameters)
    assert build_params - _PER_CALL_BUILD_PARAMS == set(AssembleOptions.__annotations__)


def test_provenance_override_replaces_the_config_provenance_whole() -> None:
    """``ConfigOverrides.provenance`` is one object: a partial one resets the
    fields it leaves at their defaults, byte cap included, exactly as it does
    the other four (the CLI always passes a fully resolved object)."""
    cfg = PitloomConfig(
        provenance_detail="full", provenance_max_source_metadata_bytes=8192
    )
    overridden = _apply_config_overrides(
        cfg, ConfigOverrides(provenance=ProvenanceConfig(format="fields"))
    )
    assert overridden.provenance == ProvenanceConfig(format="fields")
    assert cfg.provenance != overridden.provenance
