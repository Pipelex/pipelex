"""Tests for model deck validation helper methods with intentionally bad data.

These tests verify that the validation logic correctly detects invalid references.
"""

import pytest

from pipelex.cogt.model_backends.model_type import ModelType
from tests.unit.pipelex.cogt.models.model_deck_validation_utils import (
    find_circular_aliases,
    find_invalid_alias_targets,
    find_invalid_waterfall_entries,
)


class TestModelDeckValidationHelpers:
    """Test validation helper methods with synthetic bad data."""

    # ============================================================
    # Test data fixtures
    # ============================================================

    @pytest.fixture
    def known_model_handles(self) -> dict[str, ModelType]:
        """A small set of valid model handles with their types for testing."""
        return {
            "gpt-4o": ModelType.LLM,
            "claude-3-opus": ModelType.LLM,
            "gemini-pro": ModelType.LLM,
            "mistral-ocr": ModelType.TEXT_EXTRACTOR,
            "dall-e-3": ModelType.IMG_GEN,
        }

    @pytest.fixture
    def valid_aliases(self) -> dict[str, str]:
        """Valid aliases pointing to known handles."""
        return {
            "smart": "gpt-4o",
            "default": "@smart",
        }

    @pytest.fixture
    def valid_waterfalls(self) -> dict[str, list[str]]:
        """Valid waterfalls containing known handles and aliases."""
        return {
            "fallback": ["gpt-4o", "claude-3-opus"],
        }

    # ============================================================
    # Alias validation tests
    # ============================================================

    def test_detects_alias_pointing_to_unknown_handle(
        self,
        valid_aliases: dict[str, str],
        valid_waterfalls: dict[str, list[str]],
        known_model_handles: dict[str, ModelType],
    ):
        """Alias pointing to non-existent model handle is detected."""
        bad_aliases = {"broken": "nonexistent-model"}

        invalid_refs = find_invalid_alias_targets(
            aliases=bad_aliases,
            all_aliases=valid_aliases,
            all_waterfalls=valid_waterfalls,
            known_model_handles=known_model_handles,
            expected_model_type=ModelType.LLM,
        )

        assert len(invalid_refs) == 1
        assert invalid_refs[0][0] == "broken"
        assert "not found in backends" in invalid_refs[0][2]

    def test_detects_alias_pointing_to_preset(
        self,
        valid_aliases: dict[str, str],
        valid_waterfalls: dict[str, list[str]],
        known_model_handles: dict[str, ModelType],
    ):
        """Alias pointing to a preset ($ prefix) is detected as invalid."""
        bad_aliases = {"broken": "$some_preset"}

        invalid_refs = find_invalid_alias_targets(
            aliases=bad_aliases,
            all_aliases=valid_aliases,
            all_waterfalls=valid_waterfalls,
            known_model_handles=known_model_handles,
            expected_model_type=ModelType.LLM,
        )

        assert len(invalid_refs) == 1
        assert "cannot reference presets" in invalid_refs[0][2]

    def test_detects_alias_pointing_to_wrong_model_type(
        self,
        valid_aliases: dict[str, str],
        valid_waterfalls: dict[str, list[str]],
        known_model_handles: dict[str, ModelType],
    ):
        """Alias pointing to a model with wrong type is detected (e.g., LLM alias -> IMG_GEN model)."""
        # LLM alias pointing to an IMG_GEN model
        bad_aliases = {"llm-alias": "dall-e-3"}

        invalid_refs = find_invalid_alias_targets(
            aliases=bad_aliases,
            all_aliases=valid_aliases,
            all_waterfalls=valid_waterfalls,
            known_model_handles=known_model_handles,
            expected_model_type=ModelType.LLM,
        )

        assert len(invalid_refs) == 1
        assert invalid_refs[0][0] == "llm-alias"
        assert "has type 'img_gen' but expected 'llm'" in invalid_refs[0][2]

    def test_detects_extract_alias_pointing_to_llm_model(
        self,
        valid_aliases: dict[str, str],
        valid_waterfalls: dict[str, list[str]],
        known_model_handles: dict[str, ModelType],
    ):
        """Extract alias pointing to an LLM model is detected."""
        # TEXT_EXTRACTOR alias pointing to an LLM model
        bad_aliases = {"extractor-alias": "gpt-4o"}

        invalid_refs = find_invalid_alias_targets(
            aliases=bad_aliases,
            all_aliases=valid_aliases,
            all_waterfalls=valid_waterfalls,
            known_model_handles=known_model_handles,
            expected_model_type=ModelType.TEXT_EXTRACTOR,
        )

        assert len(invalid_refs) == 1
        assert invalid_refs[0][0] == "extractor-alias"
        assert "has type 'llm' but expected 'text_extractor'" in invalid_refs[0][2]

    # ============================================================
    # Waterfall validation tests
    # ============================================================

    def test_detects_waterfall_containing_another_waterfall(
        self,
        valid_aliases: dict[str, str],
        known_model_handles: dict[str, ModelType],
    ):
        """Waterfall containing another waterfall (~ prefix) is detected."""
        bad_waterfalls = {"broken": ["gpt-4o", "~other_waterfall"]}

        invalid_refs = find_invalid_waterfall_entries(
            waterfalls=bad_waterfalls,
            all_aliases=valid_aliases,
            known_model_handles=known_model_handles,
            expected_model_type=ModelType.LLM,
        )

        assert len(invalid_refs) == 1
        assert invalid_refs[0][1] == 1  # index of bad entry
        assert "cannot contain other waterfalls" in invalid_refs[0][3]

    def test_detects_waterfall_containing_preset(
        self,
        valid_aliases: dict[str, str],
        known_model_handles: dict[str, ModelType],
    ):
        """Waterfall containing a preset ($ prefix) is detected."""
        bad_waterfalls = {"broken": ["$some_preset"]}

        invalid_refs = find_invalid_waterfall_entries(
            waterfalls=bad_waterfalls,
            all_aliases=valid_aliases,
            known_model_handles=known_model_handles,
            expected_model_type=ModelType.LLM,
        )

        assert len(invalid_refs) == 1
        assert "cannot contain presets" in invalid_refs[0][3]

    def test_detects_waterfall_containing_wrong_model_type(
        self,
        valid_aliases: dict[str, str],
        known_model_handles: dict[str, ModelType],
    ):
        """Waterfall containing a model with wrong type is detected."""
        # LLM waterfall containing an IMG_GEN model
        bad_waterfalls = {"broken": ["gpt-4o", "dall-e-3"]}

        invalid_refs = find_invalid_waterfall_entries(
            waterfalls=bad_waterfalls,
            all_aliases=valid_aliases,
            known_model_handles=known_model_handles,
            expected_model_type=ModelType.LLM,
        )

        assert len(invalid_refs) == 1
        assert invalid_refs[0][1] == 1  # index of bad entry (dall-e-3)
        assert "has type 'img_gen' but expected 'llm'" in invalid_refs[0][3]

    def test_detects_empty_waterfall(
        self,
        valid_aliases: dict[str, str],
        known_model_handles: dict[str, ModelType],
    ):
        """Empty waterfall is detected (would cause IndexError at runtime)."""
        bad_waterfalls: dict[str, list[str]] = {"empty-waterfall": []}

        invalid_refs = find_invalid_waterfall_entries(
            waterfalls=bad_waterfalls,
            all_aliases=valid_aliases,
            known_model_handles=known_model_handles,
            expected_model_type=ModelType.LLM,
        )

        assert len(invalid_refs) == 1
        assert invalid_refs[0][0] == "empty-waterfall"
        assert invalid_refs[0][1] == -1  # special index for empty waterfall
        assert "cannot be empty" in invalid_refs[0][3]

    # ============================================================
    # Circular reference tests
    # ============================================================

    def test_detects_simple_circular_alias(self):
        """Direct circular reference (A -> A) is detected."""
        circular_aliases = {"loop": "@loop"}

        cycles = find_circular_aliases(aliases=circular_aliases)

        assert len(cycles) == 1
        assert "loop" in cycles[0][1]

    def test_detects_indirect_circular_alias(self):
        """Indirect circular reference (A -> B -> A) is detected."""
        circular_aliases = {
            "alpha": "@beta",
            "beta": "@alpha",
        }

        cycles = find_circular_aliases(aliases=circular_aliases)

        assert len(cycles) >= 1
        cycle_members = set(cycles[0][1])
        assert "alpha" in cycle_members
        assert "beta" in cycle_members

    def test_detects_unprefixed_circular_alias(self):
        """Unprefixed circular reference (A -> B -> A without @ prefix) is detected.

        This tests the fix for the issue where cycles like {"alpha": "beta", "beta": "alpha"}
        without @ prefixes would not be detected by validation, even though they cause issues
        at runtime. The runtime code follows unprefixed alias references when the target string
        exists as a key in the aliases dict.
        """
        circular_aliases = {
            "alpha": "beta",
            "beta": "alpha",
        }

        cycles = find_circular_aliases(aliases=circular_aliases)

        assert len(cycles) >= 1
        cycle_members = set(cycles[0][1])
        assert "alpha" in cycle_members
        assert "beta" in cycle_members

    def test_detects_mixed_prefix_circular_alias(self):
        """Circular reference with mixed prefixes (A -> @B -> C -> A) is detected."""
        circular_aliases = {
            "alpha": "@beta",
            "beta": "gamma",
            "gamma": "alpha",
        }

        cycles = find_circular_aliases(aliases=circular_aliases)

        assert len(cycles) >= 1
        cycle_members = set(cycles[0][1])
        assert "alpha" in cycle_members
        assert "beta" in cycle_members
        assert "gamma" in cycle_members

    def test_no_cycle_when_unprefixed_target_is_not_alias_key(self):
        """Unprefixed reference to a non-alias key does not create a cycle."""
        aliases = {
            "alpha": "gpt-4o",  # gpt-4o is not an alias key, so no cycle
        }

        cycles = find_circular_aliases(aliases=aliases)

        assert len(cycles) == 0
