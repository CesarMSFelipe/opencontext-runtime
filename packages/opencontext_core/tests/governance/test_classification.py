"""DataSensitivity / classify() acceptance (REQ-data-gov-001, PR-R2-B).

Spec contract:
- `DataSensitivity` enum exposes PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED.
- `classify(path, content_type, overrides=None) -> ClassifiedNode`:
    * default = INTERNAL when no override matches
    * matches the first glob in `overrides` and returns that sensitivity
    * carries the matching override rule on the result for audit
- `ClassifiedNode` is a dataclass carrying `path`, `sensitivity`, `rule`, `node_id`.
"""

from __future__ import annotations

from opencontext_core.governance.classification import (
    ClassifiedNode,
    DataSensitivity,
    classify,
)


class TestDataSensitivityEnum:
    def test_enum_has_all_four_levels(self) -> None:
        assert {s.name for s in DataSensitivity} == {
            "PUBLIC",
            "INTERNAL",
            "CONFIDENTIAL",
            "RESTRICTED",
        }

    def test_enum_values_are_stable_strings(self) -> None:
        assert DataSensitivity.PUBLIC.value == "PUBLIC"
        assert DataSensitivity.INTERNAL.value == "INTERNAL"
        assert DataSensitivity.CONFIDENTIAL.value == "CONFIDENTIAL"
        assert DataSensitivity.RESTRICTED.value == "RESTRICTED"


class TestClassifyDefault:
    def test_no_overrides_returns_internal(self) -> None:
        node = classify(path="src/app.py", content_type="text/python")
        assert isinstance(node, ClassifiedNode)
        assert node.sensitivity is DataSensitivity.INTERNAL
        assert node.path == "src/app.py"
        assert node.rule is None  # no override matched

    def test_empty_overrides_dict_returns_internal(self) -> None:
        node = classify(path="README.md", content_type="text/markdown", overrides={})
        assert node.sensitivity is DataSensitivity.INTERNAL
        assert node.rule is None


class TestClassifyOverrides:
    def test_glob_override_applies_restricted(self) -> None:
        node = classify(
            path="secrets/api_keys.py",
            content_type="text/python",
            overrides={"secrets/**": DataSensitivity.RESTRICTED},
        )
        assert node.sensitivity is DataSensitivity.RESTRICTED
        assert node.rule == "secrets/**"

    def test_first_matching_override_wins(self) -> None:
        # More specific rule first; first match wins (deterministic, no surprises).
        node = classify(
            path="secrets/api_keys.py",
            content_type="text/python",
            overrides={
                "secrets/**": DataSensitivity.RESTRICTED,
                "secrets/public/**": DataSensitivity.PUBLIC,  # never reached
            },
        )
        assert node.sensitivity is DataSensitivity.RESTRICTED

    def test_no_match_means_internal_even_with_overrides(self) -> None:
        node = classify(
            path="src/app.py",
            content_type="text/python",
            overrides={"secrets/**": DataSensitivity.RESTRICTED},
        )
        assert node.sensitivity is DataSensitivity.INTERNAL
        assert node.rule is None

    def test_override_supports_double_star_glob(self) -> None:
        node = classify(
            path="a/b/c/d/e.py",
            content_type="text/python",
            overrides={"a/**": DataSensitivity.CONFIDENTIAL},
        )
        assert node.sensitivity is DataSensitivity.CONFIDENTIAL
        assert node.rule == "a/**"


class TestClassifiedNodeDataclass:
    def test_dataclass_carries_id_and_rule(self) -> None:
        node = classify(
            path="secrets/x.py",
            content_type="text/python",
            overrides={"secrets/**": DataSensitivity.RESTRICTED},
        )
        assert node.node_id  # non-empty id minted
        assert node.path == "secrets/x.py"
        assert node.content_type == "text/python"
        assert node.sensitivity is DataSensitivity.RESTRICTED
        assert node.rule == "secrets/**"
