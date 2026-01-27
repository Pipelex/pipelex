"""Tests for validating model deck references (aliases, presets, waterfalls).

This test suite systematically validates that model deck references point to valid targets,
preventing configuration errors from being discovered at runtime.
"""

import pytest

from pipelex.cogt.extract.extract_setting import ExtractSetting
from pipelex.cogt.img_gen.img_gen_setting import ImgGenSetting
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.models.model_deck import (
    ModelDeckBlueprint,
)
from pipelex.cogt.models.model_deck_loader import load_model_deck_blueprint
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.cogt.models.model_reference import ModelReference, ModelReferenceKind
from pipelex.system.configuration.configs import ConfigPaths
from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher
from pipelex.tools.misc.file_utils import find_files_in_dir
from pipelex.tools.misc.toml_utils import load_toml_from_path_if_exists


class TestModelDeckReferences:
    """Validate that model deck references point to valid targets."""

    @pytest.fixture(scope="class")
    def model_deck_blueprint(self) -> ModelDeckBlueprint:
        """Load actual model deck blueprint from TOML files."""
        model_deck_paths = ModelManager.get_model_deck_paths(deck_dir_path=ConfigPaths.MODEL_DECKS_DIR_PATH)
        return load_model_deck_blueprint(model_deck_paths=model_deck_paths)

    @pytest.fixture(scope="class")
    def all_known_model_handles(self) -> set[str]:
        """Collect all valid model handles from local backends + Pipelex Gateway.

        Sources:
        1. Local backend TOML files (.pipelex/inference/backends/*.toml)
        2. Pipelex Gateway remote config (uses session-level cache from conftest.py)
        """
        known_handles: set[str] = set()

        # 1. Parse local backend TOML files
        known_handles.update(self._get_local_backend_models())

        # 2. Get gateway models from cached remote config
        remote_config = RemoteConfigFetcher.fetch_remote_config()  # Uses cached version
        gateway_specs = remote_config.backend_model_specs
        known_handles.update(gateway_specs.keys())

        return known_handles

    # ============================================================
    # Helper methods
    # ============================================================

    def _get_local_backend_models(self) -> set[str]:
        """Parse all local backend TOML files to collect model handles.

        Model names are the top-level keys in each backend TOML file,
        excluding the 'defaults' section which contains shared config.
        """
        known_handles: set[str] = set()
        backends_dir = ConfigPaths.BACKENDS_DIR_PATH

        toml_files = find_files_in_dir(backends_dir, pattern="*.toml", is_recursive=False)
        for toml_path in toml_files:
            backend_data = load_toml_from_path_if_exists(str(toml_path))
            if backend_data:
                # Model names are top-level keys except "defaults"
                for key in backend_data:
                    if key != "defaults":
                        known_handles.add(key)

        return known_handles

    def _find_invalid_alias_targets(
        self,
        aliases: dict[str, str],
        all_aliases: dict[str, str],
        all_waterfalls: dict[str, list[str]],
        known_model_handles: set[str],
    ) -> list[tuple[str, str, str]]:
        """Find aliases that reference invalid targets.

        Args:
            aliases: The aliases dict to validate
            all_aliases: All available aliases for this model type
            all_waterfalls: All available waterfalls for this model type
            known_model_handles: Set of valid direct model handles

        Returns:
            List of (alias_name, target_value, reason) tuples for invalid references
        """
        invalid_refs: list[tuple[str, str, str]] = []

        for alias_name, target_value in aliases.items():
            ref = ModelReference.parse(target_value)

            match ref.kind:
                case ModelReferenceKind.ALIAS:
                    # Alias can point to another alias
                    if ref.name not in all_aliases:
                        invalid_refs.append((alias_name, target_value, f"alias '{ref.name}' not found"))
                case ModelReferenceKind.WATERFALL:
                    # Alias can point to a waterfall
                    if ref.name not in all_waterfalls:
                        invalid_refs.append((alias_name, target_value, f"waterfall '{ref.name}' not found"))
                case ModelReferenceKind.PRESET:
                    # Alias should NOT point to a preset
                    invalid_refs.append((alias_name, target_value, "aliases cannot reference presets ($ prefix)"))
                case ModelReferenceKind.HANDLE:
                    # Validate direct handle exists in known models
                    if ref.name not in known_model_handles:
                        invalid_refs.append((alias_name, target_value, f"model handle '{ref.name}' not found in backends"))

        return invalid_refs

    def _find_invalid_preset_references(
        self,
        presets: dict[str, LLMSetting] | dict[str, ExtractSetting] | dict[str, ImgGenSetting],
        all_aliases: dict[str, str],
        all_waterfalls: dict[str, list[str]],
        known_model_handles: set[str],
    ) -> list[tuple[str, str, str]]:
        """Find presets that reference invalid model targets.

        Args:
            presets: The presets dict to validate
            all_aliases: All available aliases for this model type
            all_waterfalls: All available waterfalls for this model type
            known_model_handles: Set of valid direct model handles

        Returns:
            List of (preset_name, model_value, reason) tuples for invalid references
        """
        invalid_refs: list[tuple[str, str, str]] = []

        for preset_name, preset_setting in presets.items():
            model_value = preset_setting.model
            ref = ModelReference.parse(model_value)

            match ref.kind:
                case ModelReferenceKind.ALIAS:
                    # Preset can use an alias
                    if ref.name not in all_aliases:
                        invalid_refs.append((preset_name, model_value, f"alias '{ref.name}' not found"))
                case ModelReferenceKind.WATERFALL:
                    # Preset can use a waterfall
                    if ref.name not in all_waterfalls:
                        invalid_refs.append((preset_name, model_value, f"waterfall '{ref.name}' not found"))
                case ModelReferenceKind.PRESET:
                    # Preset should NOT reference another preset
                    invalid_refs.append((preset_name, model_value, "presets cannot reference other presets ($ prefix)"))
                case ModelReferenceKind.HANDLE:
                    # Validate direct handle exists in known models
                    if ref.name not in known_model_handles:
                        invalid_refs.append((preset_name, model_value, f"model handle '{ref.name}' not found in backends"))

        return invalid_refs

    def _find_invalid_waterfall_entries(
        self,
        waterfalls: dict[str, list[str]],
        all_aliases: dict[str, str],
        known_model_handles: set[str],
    ) -> list[tuple[str, int, str, str]]:
        """Find waterfall entries that reference invalid targets.

        Args:
            waterfalls: The waterfalls dict to validate
            all_aliases: All available aliases for this model type
            known_model_handles: Set of valid direct model handles

        Returns:
            List of (waterfall_name, index, entry_value, reason) tuples for invalid entries
        """
        invalid_refs: list[tuple[str, int, str, str]] = []

        for waterfall_name, entries in waterfalls.items():
            for index, entry_value in enumerate(entries):
                ref = ModelReference.parse(entry_value)

                match ref.kind:
                    case ModelReferenceKind.ALIAS:
                        # Waterfall can contain aliases
                        if ref.name not in all_aliases:
                            invalid_refs.append((waterfall_name, index, entry_value, f"alias '{ref.name}' not found"))
                    case ModelReferenceKind.WATERFALL:
                        # Waterfall should NOT contain other waterfalls
                        invalid_refs.append((waterfall_name, index, entry_value, "waterfalls cannot contain other waterfalls (~ prefix)"))
                    case ModelReferenceKind.PRESET:
                        # Waterfall should NOT contain presets
                        invalid_refs.append((waterfall_name, index, entry_value, "waterfalls cannot contain presets ($ prefix)"))
                    case ModelReferenceKind.HANDLE:
                        # Validate direct handle exists in known models
                        if ref.name not in known_model_handles:
                            invalid_refs.append((waterfall_name, index, entry_value, f"model handle '{ref.name}' not found in backends"))

        return invalid_refs

    def _find_circular_aliases(
        self,
        aliases: dict[str, str],
    ) -> list[tuple[str, list[str]]]:
        """Find circular alias chains.

        Args:
            aliases: The aliases dict to check for cycles

        Returns:
            List of (starting_alias, cycle_path) tuples for detected cycles
        """
        cycles: list[tuple[str, list[str]]] = []

        for start_alias in aliases:
            visited: list[str] = []
            current = start_alias

            while current in aliases:
                if current in visited:
                    # Found a cycle
                    cycle_start_idx = visited.index(current)
                    cycle_path = [*visited[cycle_start_idx:], current]
                    # Only report if this cycle starts with our starting alias
                    if start_alias in cycle_path:
                        cycles.append((start_alias, cycle_path))
                    break

                visited.append(current)
                target = aliases[current]
                ref = ModelReference.parse(target)

                # Only follow alias references
                if ref.kind == ModelReferenceKind.ALIAS:
                    current = ref.name
                else:
                    # Not an alias reference, chain ends
                    break

        # Deduplicate cycles (same cycle can be found from different starting points)
        unique_cycles: list[tuple[str, list[str]]] = []
        seen_cycles: set[frozenset[str]] = set()

        for start_alias, cycle_path in cycles:
            cycle_set = frozenset(cycle_path)
            if cycle_set not in seen_cycles:
                seen_cycles.add(cycle_set)
                unique_cycles.append((start_alias, cycle_path))

        return unique_cycles

    # ============================================================
    # LLM Tests
    # ============================================================

    def test_llm_aliases_reference_valid_targets(
        self,
        model_deck_blueprint: ModelDeckBlueprint,
        all_known_model_handles: set[str],
    ):
        """Verify LLM aliases point to valid targets (other aliases, waterfalls, or direct handles)."""
        llm_deck = model_deck_blueprint.llm

        invalid_refs = self._find_invalid_alias_targets(
            aliases=llm_deck.aliases,
            all_aliases=llm_deck.aliases,
            all_waterfalls=llm_deck.waterfalls,
            known_model_handles=all_known_model_handles,
        )

        if invalid_refs:
            error_lines = ["Invalid LLM alias references found:"]
            for alias_name, target_value, reason in invalid_refs:
                error_lines.append(f"  - '{alias_name}' -> '{target_value}': {reason}")
            pytest.fail("\n".join(error_lines))

    def test_llm_presets_reference_valid_models(
        self,
        model_deck_blueprint: ModelDeckBlueprint,
        all_known_model_handles: set[str],
    ):
        """Verify LLM preset model fields use valid aliases, waterfalls, or direct handles."""
        llm_deck = model_deck_blueprint.llm

        invalid_refs = self._find_invalid_preset_references(
            presets=llm_deck.presets,
            all_aliases=llm_deck.aliases,
            all_waterfalls=llm_deck.waterfalls,
            known_model_handles=all_known_model_handles,
        )

        if invalid_refs:
            error_lines = ["Invalid LLM preset model references found:"]
            for preset_name, model_value, reason in invalid_refs:
                error_lines.append(f"  - preset '{preset_name}' model='{model_value}': {reason}")
            pytest.fail("\n".join(error_lines))

    def test_llm_waterfalls_contain_valid_models(
        self,
        model_deck_blueprint: ModelDeckBlueprint,
        all_known_model_handles: set[str],
    ):
        """Verify LLM waterfall entries are valid aliases or direct model handles."""
        llm_deck = model_deck_blueprint.llm

        invalid_refs = self._find_invalid_waterfall_entries(
            waterfalls=llm_deck.waterfalls,
            all_aliases=llm_deck.aliases,
            known_model_handles=all_known_model_handles,
        )

        if invalid_refs:
            error_lines = ["Invalid LLM waterfall entries found:"]
            for waterfall_name, index, entry_value, reason in invalid_refs:
                error_lines.append(f"  - waterfall '{waterfall_name}'[{index}]='{entry_value}': {reason}")
            pytest.fail("\n".join(error_lines))

    def test_llm_aliases_no_circular_references(self, model_deck_blueprint: ModelDeckBlueprint):
        """Detect LLM alias chains that form cycles."""
        llm_deck = model_deck_blueprint.llm

        cycles = self._find_circular_aliases(aliases=llm_deck.aliases)

        if cycles:
            error_lines = ["Circular LLM alias references detected:"]
            for _start_alias, cycle_path in cycles:
                cycle_str = " -> ".join(cycle_path)
                error_lines.append(f"  - {cycle_str}")
            pytest.fail("\n".join(error_lines))

    # ============================================================
    # Extract Tests
    # ============================================================

    def test_extract_aliases_reference_valid_targets(
        self,
        model_deck_blueprint: ModelDeckBlueprint,
        all_known_model_handles: set[str],
    ):
        """Verify Extract aliases point to valid targets (other aliases, waterfalls, or direct handles)."""
        extract_deck = model_deck_blueprint.extract

        invalid_refs = self._find_invalid_alias_targets(
            aliases=extract_deck.aliases,
            all_aliases=extract_deck.aliases,
            all_waterfalls=extract_deck.waterfalls,
            known_model_handles=all_known_model_handles,
        )

        if invalid_refs:
            error_lines = ["Invalid Extract alias references found:"]
            for alias_name, target_value, reason in invalid_refs:
                error_lines.append(f"  - '{alias_name}' -> '{target_value}': {reason}")
            pytest.fail("\n".join(error_lines))

    def test_extract_presets_reference_valid_models(
        self,
        model_deck_blueprint: ModelDeckBlueprint,
        all_known_model_handles: set[str],
    ):
        """Verify Extract preset model fields use valid aliases, waterfalls, or direct handles."""
        extract_deck = model_deck_blueprint.extract

        invalid_refs = self._find_invalid_preset_references(
            presets=extract_deck.presets,
            all_aliases=extract_deck.aliases,
            all_waterfalls=extract_deck.waterfalls,
            known_model_handles=all_known_model_handles,
        )

        if invalid_refs:
            error_lines = ["Invalid Extract preset model references found:"]
            for preset_name, model_value, reason in invalid_refs:
                error_lines.append(f"  - preset '{preset_name}' model='{model_value}': {reason}")
            pytest.fail("\n".join(error_lines))

    def test_extract_waterfalls_contain_valid_models(
        self,
        model_deck_blueprint: ModelDeckBlueprint,
        all_known_model_handles: set[str],
    ):
        """Verify Extract waterfall entries are valid aliases or direct model handles."""
        extract_deck = model_deck_blueprint.extract

        invalid_refs = self._find_invalid_waterfall_entries(
            waterfalls=extract_deck.waterfalls,
            all_aliases=extract_deck.aliases,
            known_model_handles=all_known_model_handles,
        )

        if invalid_refs:
            error_lines = ["Invalid Extract waterfall entries found:"]
            for waterfall_name, index, entry_value, reason in invalid_refs:
                error_lines.append(f"  - waterfall '{waterfall_name}'[{index}]='{entry_value}': {reason}")
            pytest.fail("\n".join(error_lines))

    def test_extract_aliases_no_circular_references(self, model_deck_blueprint: ModelDeckBlueprint):
        """Detect Extract alias chains that form cycles."""
        extract_deck = model_deck_blueprint.extract

        cycles = self._find_circular_aliases(aliases=extract_deck.aliases)

        if cycles:
            error_lines = ["Circular Extract alias references detected:"]
            for _start_alias, cycle_path in cycles:
                cycle_str = " -> ".join(cycle_path)
                error_lines.append(f"  - {cycle_str}")
            pytest.fail("\n".join(error_lines))

    # ============================================================
    # ImgGen Tests
    # ============================================================

    def test_img_gen_aliases_reference_valid_targets(
        self,
        model_deck_blueprint: ModelDeckBlueprint,
        all_known_model_handles: set[str],
    ):
        """Verify ImgGen aliases point to valid targets (other aliases, waterfalls, or direct handles)."""
        img_gen_deck = model_deck_blueprint.img_gen

        invalid_refs = self._find_invalid_alias_targets(
            aliases=img_gen_deck.aliases,
            all_aliases=img_gen_deck.aliases,
            all_waterfalls=img_gen_deck.waterfalls,
            known_model_handles=all_known_model_handles,
        )

        if invalid_refs:
            error_lines = ["Invalid ImgGen alias references found:"]
            for alias_name, target_value, reason in invalid_refs:
                error_lines.append(f"  - '{alias_name}' -> '{target_value}': {reason}")
            pytest.fail("\n".join(error_lines))

    def test_img_gen_presets_reference_valid_models(
        self,
        model_deck_blueprint: ModelDeckBlueprint,
        all_known_model_handles: set[str],
    ):
        """Verify ImgGen preset model fields use valid aliases, waterfalls, or direct handles."""
        img_gen_deck = model_deck_blueprint.img_gen

        invalid_refs = self._find_invalid_preset_references(
            presets=img_gen_deck.presets,
            all_aliases=img_gen_deck.aliases,
            all_waterfalls=img_gen_deck.waterfalls,
            known_model_handles=all_known_model_handles,
        )

        if invalid_refs:
            error_lines = ["Invalid ImgGen preset model references found:"]
            for preset_name, model_value, reason in invalid_refs:
                error_lines.append(f"  - preset '{preset_name}' model='{model_value}': {reason}")
            pytest.fail("\n".join(error_lines))

    def test_img_gen_waterfalls_contain_valid_models(
        self,
        model_deck_blueprint: ModelDeckBlueprint,
        all_known_model_handles: set[str],
    ):
        """Verify ImgGen waterfall entries are valid aliases or direct model handles."""
        img_gen_deck = model_deck_blueprint.img_gen

        invalid_refs = self._find_invalid_waterfall_entries(
            waterfalls=img_gen_deck.waterfalls,
            all_aliases=img_gen_deck.aliases,
            known_model_handles=all_known_model_handles,
        )

        if invalid_refs:
            error_lines = ["Invalid ImgGen waterfall entries found:"]
            for waterfall_name, index, entry_value, reason in invalid_refs:
                error_lines.append(f"  - waterfall '{waterfall_name}'[{index}]='{entry_value}': {reason}")
            pytest.fail("\n".join(error_lines))

    def test_img_gen_aliases_no_circular_references(self, model_deck_blueprint: ModelDeckBlueprint):
        """Detect ImgGen alias chains that form cycles."""
        img_gen_deck = model_deck_blueprint.img_gen

        cycles = self._find_circular_aliases(aliases=img_gen_deck.aliases)

        if cycles:
            error_lines = ["Circular ImgGen alias references detected:"]
            for _start_alias, cycle_path in cycles:
                cycle_str = " -> ".join(cycle_path)
                error_lines.append(f"  - {cycle_str}")
            pytest.fail("\n".join(error_lines))
