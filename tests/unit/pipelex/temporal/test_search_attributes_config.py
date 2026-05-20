"""Unit tests for ``SearchAttributesConfig`` validation.

Phase 6 introduces a config block that controls the custom Temporal search
attribute surface. The pydantic model rejects unknown attribute names so a
typo like ``"PipelineRunID"`` (wrong casing) fails at config-load instead of
silently producing no attribute at workflow-start time.
"""

import pytest
from pydantic import ValidationError

from pipelex.temporal.config_temporal import BUILTIN_SEARCH_ATTRIBUTES, SearchAttributesConfig


class TestSearchAttributesConfig:
    def test_default_full_subset_accepts_all_built_in_names(self) -> None:
        config = SearchAttributesConfig(
            enabled=True,
            attributes=list(BUILTIN_SEARCH_ATTRIBUTES),
        )

        assert config.enabled is True
        assert config.attributes == list(BUILTIN_SEARCH_ATTRIBUTES)

    def test_partial_subset_is_accepted(self) -> None:
        config = SearchAttributesConfig(
            enabled=True,
            attributes=["PipeCode", "DomainCode"],
        )

        assert config.attributes == ["PipeCode", "DomainCode"]

    def test_disabled_with_empty_attributes_is_accepted(self) -> None:
        config = SearchAttributesConfig(enabled=False, attributes=[])

        assert config.enabled is False
        assert config.attributes == []

    def test_unknown_attribute_name_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            SearchAttributesConfig(
                enabled=True,
                # Note the wrong casing on the last segment — this is the kind
                # of typo the validator is designed to catch.
                attributes=["PipeCode", "PipelineRunID"],
            )

        message = str(exc_info.value)
        assert "PipelineRunID" in message
        # The error message lists the known good names so the operator can
        # fix the typo without grepping the source.
        for name in BUILTIN_SEARCH_ATTRIBUTES:
            assert name in message

    def test_arbitrary_custom_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SearchAttributesConfig(enabled=True, attributes=["MyCustomAttribute"])
