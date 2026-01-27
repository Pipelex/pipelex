"""Tests for model deck validation helper methods with intentionally bad data.

These tests verify that the validation logic correctly detects invalid references.
"""

import pytest

from pipelex.cogt.models.model_reference import ModelReference, ModelReferenceKind


class TestModelDeckValidationHelpers:
    """Test validation helper methods with synthetic bad data."""

    # ============================================================
    # Test data fixtures
    # ============================================================

    @pytest.fixture
    def known_model_handles(self) -> set[str]:
        """A small set of valid model handles for testing."""
        return {"gpt-4o", "claude-3-opus", "gemini-pro"}

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
    # Helper method implementations (copied from main test for isolation)
    # ============================================================

    def _find_invalid_alias_targets(
        self,
        aliases: dict[str, str],
        all_aliases: dict[str, str],
        all_waterfalls: dict[str, list[str]],
        known_model_handles: set[str],
    ) -> list[tuple[str, str, str]]:
        """Find aliases that reference invalid targets."""
        invalid_refs: list[tuple[str, str, str]] = []

        for alias_name, target_value in aliases.items():
            ref = ModelReference.parse(target_value)

            match ref.kind:
                case ModelReferenceKind.ALIAS:
                    if ref.name not in all_aliases:
                        invalid_refs.append((alias_name, target_value, f"alias '{ref.name}' not found"))
                case ModelReferenceKind.WATERFALL:
                    if ref.name not in all_waterfalls:
                        invalid_refs.append((alias_name, target_value, f"waterfall '{ref.name}' not found"))
                case ModelReferenceKind.PRESET:
                    invalid_refs.append((alias_name, target_value, "aliases cannot reference presets ($ prefix)"))
                case ModelReferenceKind.HANDLE:
                    if ref.name not in known_model_handles:
                        invalid_refs.append((alias_name, target_value, f"model handle '{ref.name}' not found in backends"))

        return invalid_refs

    def _find_invalid_waterfall_entries(
        self,
        waterfalls: dict[str, list[str]],
        all_aliases: dict[str, str],
        known_model_handles: set[str],
    ) -> list[tuple[str, int, str, str]]:
        """Find waterfall entries that reference invalid targets."""
        invalid_refs: list[tuple[str, int, str, str]] = []

        for waterfall_name, entries in waterfalls.items():
            for index, entry_value in enumerate(entries):
                ref = ModelReference.parse(entry_value)

                match ref.kind:
                    case ModelReferenceKind.ALIAS:
                        if ref.name not in all_aliases:
                            invalid_refs.append((waterfall_name, index, entry_value, f"alias '{ref.name}' not found"))
                    case ModelReferenceKind.WATERFALL:
                        invalid_refs.append((waterfall_name, index, entry_value, "waterfalls cannot contain other waterfalls (~ prefix)"))
                    case ModelReferenceKind.PRESET:
                        invalid_refs.append((waterfall_name, index, entry_value, "waterfalls cannot contain presets ($ prefix)"))
                    case ModelReferenceKind.HANDLE:
                        if ref.name not in known_model_handles:
                            invalid_refs.append((waterfall_name, index, entry_value, f"model handle '{ref.name}' not found in backends"))

        return invalid_refs

    def _find_circular_aliases(
        self,
        aliases: dict[str, str],
    ) -> list[tuple[str, list[str]]]:
        """Find circular alias chains."""
        cycles: list[tuple[str, list[str]]] = []

        for start_alias in aliases:
            visited: list[str] = []
            current = start_alias

            while current in aliases:
                if current in visited:
                    cycle_start_idx = visited.index(current)
                    cycle_path = [*visited[cycle_start_idx:], current]
                    if start_alias in cycle_path:
                        cycles.append((start_alias, cycle_path))
                    break

                visited.append(current)
                target = aliases[current]
                ref = ModelReference.parse(target)

                if ref.kind == ModelReferenceKind.ALIAS:
                    current = ref.name
                else:
                    break

        unique_cycles: list[tuple[str, list[str]]] = []
        seen_cycles: set[frozenset[str]] = set()

        for start_alias, cycle_path in cycles:
            cycle_set = frozenset(cycle_path)
            if cycle_set not in seen_cycles:
                seen_cycles.add(cycle_set)
                unique_cycles.append((start_alias, cycle_path))

        return unique_cycles

    # ============================================================
    # Alias validation tests
    # ============================================================

    def test_detects_alias_pointing_to_unknown_handle(
        self,
        valid_aliases: dict[str, str],
        valid_waterfalls: dict[str, list[str]],
        known_model_handles: set[str],
    ):
        """Alias pointing to non-existent model handle is detected."""
        bad_aliases = {"broken": "nonexistent-model"}

        invalid_refs = self._find_invalid_alias_targets(
            aliases=bad_aliases,
            all_aliases=valid_aliases,
            all_waterfalls=valid_waterfalls,
            known_model_handles=known_model_handles,
        )

        assert len(invalid_refs) == 1
        assert invalid_refs[0][0] == "broken"
        assert "not found in backends" in invalid_refs[0][2]

    def test_detects_alias_pointing_to_preset(
        self,
        valid_aliases: dict[str, str],
        valid_waterfalls: dict[str, list[str]],
        known_model_handles: set[str],
    ):
        """Alias pointing to a preset ($ prefix) is detected as invalid."""
        bad_aliases = {"broken": "$some_preset"}

        invalid_refs = self._find_invalid_alias_targets(
            aliases=bad_aliases,
            all_aliases=valid_aliases,
            all_waterfalls=valid_waterfalls,
            known_model_handles=known_model_handles,
        )

        assert len(invalid_refs) == 1
        assert "cannot reference presets" in invalid_refs[0][2]

    # ============================================================
    # Waterfall validation tests
    # ============================================================

    def test_detects_waterfall_containing_another_waterfall(
        self,
        valid_aliases: dict[str, str],
        known_model_handles: set[str],
    ):
        """Waterfall containing another waterfall (~ prefix) is detected."""
        bad_waterfalls = {"broken": ["gpt-4o", "~other_waterfall"]}

        invalid_refs = self._find_invalid_waterfall_entries(
            waterfalls=bad_waterfalls,
            all_aliases=valid_aliases,
            known_model_handles=known_model_handles,
        )

        assert len(invalid_refs) == 1
        assert invalid_refs[0][1] == 1  # index of bad entry
        assert "cannot contain other waterfalls" in invalid_refs[0][3]

    def test_detects_waterfall_containing_preset(
        self,
        valid_aliases: dict[str, str],
        known_model_handles: set[str],
    ):
        """Waterfall containing a preset ($ prefix) is detected."""
        bad_waterfalls = {"broken": ["$some_preset"]}

        invalid_refs = self._find_invalid_waterfall_entries(
            waterfalls=bad_waterfalls,
            all_aliases=valid_aliases,
            known_model_handles=known_model_handles,
        )

        assert len(invalid_refs) == 1
        assert "cannot contain presets" in invalid_refs[0][3]

    # ============================================================
    # Circular reference tests
    # ============================================================

    def test_detects_simple_circular_alias(self):
        """Direct circular reference (A -> A) is detected."""
        circular_aliases = {"loop": "@loop"}

        cycles = self._find_circular_aliases(aliases=circular_aliases)

        assert len(cycles) == 1
        assert "loop" in cycles[0][1]

    def test_detects_indirect_circular_alias(self):
        """Indirect circular reference (A -> B -> A) is detected."""
        circular_aliases = {
            "alpha": "@beta",
            "beta": "@alpha",
        }

        cycles = self._find_circular_aliases(aliases=circular_aliases)

        assert len(cycles) >= 1
        cycle_members = set(cycles[0][1])
        assert "alpha" in cycle_members
        assert "beta" in cycle_members
