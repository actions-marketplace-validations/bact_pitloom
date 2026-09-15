# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``has_uv_build_backend_overrides()`` -- every malformed/
absent-nesting branch of its ``tool.uv.build-backend`` walk, plus the
tri-state (absent/empty/populated) distinction on the two file-filtering
keys themselves. See also:
tests/core/models_wheel/test_models_wheel_dispatch.py's
``test_get_wheel_files_uv_build_fallback_warns_about_wheel_exclude``/
``test_get_wheel_files_uv_build_fallback_no_hint_without_file_filter_keys``
for the end-to-end (parsed real pyproject.toml -> sharpened WARNING:)
behavior this function feeds into.
"""

from __future__ import annotations

import pytest

from pitloom.core._models_wheel_types import has_uv_build_backend_overrides


@pytest.mark.parametrize(
    ("pyproject_data", "expected"),
    [
        pytest.param({}, False, id="no_tool_table"),
        pytest.param({"tool": "not-a-dict"}, False, id="tool_not_a_dict"),
        pytest.param({"tool": {}}, False, id="tool_present_no_uv"),
        pytest.param({"tool": {"uv": "not-a-dict"}}, False, id="uv_not_a_dict"),
        pytest.param({"tool": {"uv": {}}}, False, id="uv_present_no_build_backend"),
        pytest.param(
            {"tool": {"uv": {"build-backend": "not-a-dict"}}},
            False,
            id="build_backend_not_a_dict",
        ),
        pytest.param(
            {"tool": {"uv": {"build-backend": {}}}},
            False,
            id="build_backend_present_but_empty",
        ),
        pytest.param(
            {"tool": {"uv": {"build-backend": {"module-root": ""}}}},
            False,
            id="only_non_filtering_key_present",
        ),
        pytest.param(
            {"tool": {"uv": {"build-backend": {"module-name": "pkg._core"}}}},
            False,
            id="module_name_alone_is_not_a_filter",
        ),
        pytest.param(
            {"tool": {"uv": {"build-backend": {"wheel-exclude": []}}}},
            False,
            id="wheel_exclude_present_but_empty_list",
        ),
        pytest.param(
            {"tool": {"uv": {"build-backend": {"wheel-include": []}}}},
            False,
            id="wheel_include_present_but_empty_list",
        ),
        pytest.param(
            {"tool": {"uv": {"build-backend": {"wheel-exclude": ["a/**"]}}}},
            True,
            id="wheel_exclude_populated",
        ),
        pytest.param(
            {"tool": {"uv": {"build-backend": {"wheel-include": ["a/**"]}}}},
            True,
            id="wheel_include_populated",
        ),
        pytest.param(
            {
                "tool": {
                    "uv": {
                        "build-backend": {
                            "module-root": "",
                            "wheel-exclude": ["a/**"],
                        }
                    }
                }
            },
            True,
            id="filter_key_alongside_non_filter_key",
        ),
        pytest.param(
            {
                "tool": {
                    "uv": {
                        "build-backend": {
                            "wheel-exclude": [],
                            "wheel-include": ["a/**"],
                        }
                    }
                }
            },
            True,
            id="one_empty_one_populated_still_true",
        ),
    ],
)
def test_has_uv_build_backend_overrides(
    pyproject_data: dict[str, object], expected: bool
) -> None:
    assert has_uv_build_backend_overrides(pyproject_data) is expected
