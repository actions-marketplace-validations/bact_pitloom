# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Both halves of the configuration cascade.

:func:`~pitloom.core.config_cascade.apply_overrides` is where "the flag
wins, the config is the fallback" is decided once for every surface, so
these guard its two easy-to-break properties: an override of ``False``/``0``
is an explicit choice rather than an absence, and the *resulting* config is
what gets validated, not just the override.

:func:`~pitloom.core.config_cascade.resolve_generator_config` reads the
config those overrides land on; its tests pin which failures of that read
are silent (absent source data) and which warn (a source that claimed to
carry settings and could not deliver them).

See also:
- :mod:`tests.assemble.test_embed_build_seam` for the resolved values
  reaching the assembler on each surface.
- :mod:`tests.assemble.test_embed_overrides` for what ``embed-wheel`` does
  with a merged config.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import (
    ConfigOverrides,
    apply_overrides,
    resolve_generator_config,
)
from pitloom.core.enrich_config import EnrichConfig
from pitloom.core.provenance import ProvenanceConfig


def test_apply_overrides_full() -> None:
    """Test apply_overrides applies all CLI override parameters."""
    cfg = PitloomConfig()
    prov = ProvenanceConfig(
        format="fields",
        schema="https://example.com/schema",
        detail="full",
        preserve_source_metadata="always",
    )
    overridden = apply_overrides(
        cfg,
        ConfigOverrides(
            provenance=prov,
            enrich=True,
            extract_file_header=False,
            content_type=True,
            content_type_method="extension",
            offline=True,
        ),
    )
    assert overridden.provenance_format == "fields"
    assert overridden.provenance_schema == "https://example.com/schema"
    assert overridden.provenance_detail == "full"
    assert overridden.provenance_preserve_source_metadata == "always"
    assert overridden.enrich_local is True
    assert overridden.extract_file_header is False
    assert overridden.content_type.enabled is True
    assert overridden.content_type.method == "extension"
    assert overridden.offline is True

    with pytest.raises(ValueError, match="content_type_method must be one of"):
        apply_overrides(
            cfg,
            ConfigOverrides(content_type_method="invalid_method"),
        )


# Each boolean override and the PitloomConfig field it lands on. Two fields
# are renamed on the way across, which is itself worth pinning.
_BOOL_OVERRIDE_TO_CONFIG = {
    "enrich": "enrich_local",
    "extract_file_header": "extract_file_header",
    "content_type": "content_type_enabled",
    "offline": "offline",
    "pretty": "pretty",
    "describe_relationship": "describe_relationship",
    "update_registry": "update_registry",
}


def test_every_config_overrides_field_is_accounted_for() -> None:
    """A new override field must join the map above (and so get the
    both-ways test below), rather than silently going uncovered."""
    non_bool = {"provenance", "content_type_method", "build_options"}
    assert set(_BOOL_OVERRIDE_TO_CONFIG) | non_bool == {
        f.name for f in dataclasses.fields(ConfigOverrides)
    }


@pytest.mark.parametrize("override_name", sorted(_BOOL_OVERRIDE_TO_CONFIG))
@pytest.mark.parametrize("value", [True, False])
def test_explicit_bool_override_beats_the_config_both_ways(
    override_name: str, value: bool
) -> None:
    """``False`` is an explicit choice, not an absence.

    Testing only the ``True`` direction cannot tell ``is not None`` apart
    from a truthiness check, and a truthiness check silently discards
    ``--no-offline``/``--no-pretty`` and every other opt-out (AGENTS.md's
    ``None`` vs empty tri-state rule). The config is seeded to the opposite
    value, so the override is the only possible source of the result.
    """
    config_name = _BOOL_OVERRIDE_TO_CONFIG[override_name]
    # Both field names are only known at run time, so the kwargs dicts are
    # typed Any; the assertion below is what pins the behaviour.
    seed: dict[str, Any] = {config_name: not value}
    override: dict[str, Any] = {override_name: value}
    merged = apply_overrides(PitloomConfig(**seed), ConfigOverrides(**override))
    assert getattr(merged, config_name) is value


def test_invalid_method_from_the_config_alone_is_rejected() -> None:
    """``apply_overrides`` validates the effective method, not just the
    override, so a hand-built config cannot smuggle one past a caller that
    overrode nothing. Only the public library API can reach this: the TOML
    reader and the CLI's ``choices=`` both reject it earlier."""
    with pytest.raises(ValueError, match="content_type_method must be one of"):
        apply_overrides(PitloomConfig(content_type_method="bogus"), ConfigOverrides())


def test_resolve_generator_config_invalid_pyproject_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Invalid TOML warns once and falls back to defaults, for every field
    the generators read off it -- one reader now serves both the offline and
    the enrich lookups the model generator used to resolve separately."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pitloom\ninvalid toml syntax", encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING):
        config = resolve_generator_config(tmp_path)
    assert config.offline is False
    assert config.enrich == EnrichConfig()
    assert "Ignoring invalid pyproject.toml" in caplog.text


def test_resolve_generator_config_unreadable_pyproject_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A pyproject.toml that exists but cannot be read is a failure of a
    source that claimed to carry settings, so it warns and falls back --
    it must not abort SBOM generation with an uncaught OSError.

    A directory standing where the file should be is the portable way to
    provoke this: POSIX raises IsADirectoryError, Windows PermissionError,
    and a chmod-based test would be vacuous as root and inert on Windows
    (see AGENTS.md on POSIX-only assumptions in tests).
    """
    (tmp_path / "pyproject.toml").mkdir()
    with caplog.at_level(logging.WARNING):
        config = resolve_generator_config(tmp_path)
    assert config == PitloomConfig()
    assert "Ignoring unreadable pyproject.toml" in caplog.text


def test_resolve_generator_config_missing_pyproject_is_silent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A target with no project of its own (a wheel, a model file) is a
    normal case, not a failure: defaults, no WARNING."""
    with caplog.at_level(logging.WARNING):
        config = resolve_generator_config(tmp_path)
    assert config == PitloomConfig()
    assert caplog.text == ""


def _serialisation_signals(sbom_json: str) -> tuple[bool, bool]:
    """(pretty-printed, relationships described) for one SBOM."""
    relationships = [
        node
        for node in json.loads(sbom_json)["@graph"]
        if node.get("type") == "Relationship"
    ]
    assert relationships, "fixture must produce relationships to describe"
    return "\n  " in sbom_json, any("description" in r for r in relationships)


@pytest.mark.parametrize(
    ("setting", "via"),
    [
        pytest.param(setting, via, id=f"{setting}-via-{via}")
        for setting in ("pretty", "describe_relationship")
        for via in ("override", "config")
    ],
)
def test_project_serialisation_settings_reach_the_output(
    setting: str, via: str, tmp_path: Path
) -> None:
    """``pretty``/``describe_relationship`` only act at serialisation, the
    last step of ``generate_project_sbom``, so a value the cascade resolved
    correctly can still be dropped on the way out. Each is turned on from
    exactly one source and must show up in the output -- and only that
    one, which is what makes the other's absence a real check.
    """
    toml_key = setting.replace("_", "-")
    config = f"\n[tool.pitloom]\n{toml_key} = true\n" if via == "config" else ""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "cascade-pkg"\nversion = "1.0.0"\n'
        'dependencies = ["somedep"]\n' + config,
        encoding="utf-8",
    )
    overrides: dict[str, Any] = {setting: True} if via == "override" else {}

    pretty, described = _serialisation_signals(
        generate_project_sbom(tmp_path, offline=True, **overrides)
    )

    assert (pretty, described) == (setting == "pretty", setting != "pretty")


def test_project_serialisation_settings_default_off(tmp_path: Path) -> None:
    """The baseline both cases above differ from: with neither given,
    neither signal appears, so their presence is never incidental."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "cascade-pkg"\nversion = "1.0.0"\n'
        'dependencies = ["somedep"]\n',
        encoding="utf-8",
    )
    assert _serialisation_signals(generate_project_sbom(tmp_path, offline=True)) == (
        False,
        False,
    )
