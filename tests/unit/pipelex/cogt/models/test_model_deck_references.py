"""Tests for validating model deck references (aliases, presets, waterfalls).

This test suite systematically validates that model deck references point to valid targets,
preventing configuration errors from being discovered at runtime.
"""

from collections.abc import Mapping

import pytest

from pipelex.cogt.doc_gen.doc_gen_setting import DocGenSetting
from pipelex.cogt.extract.extract_setting import ExtractSetting
from pipelex.cogt.img_gen.img_gen_setting import ImgGenSetting
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.model_backends.model_spec_document import list_declared_model_specs
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import (
    ModelDeckBlueprint,
)
from pipelex.cogt.models.model_deck_loader import load_model_deck_blueprint
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.cogt.models.model_reference import ModelReference, ModelReferenceKind
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.system.configuration.config_loader import config_manager
from pipelex.tools.misc.file_utils import find_files_in_dir
from pipelex.tools.misc.toml_utils import load_toml_from_path_if_exists
from tests.unit.pipelex.cogt.models.model_deck_validation_utils import (
    find_circular_aliases,
    find_invalid_alias_targets,
    find_invalid_waterfall_entries,
)


class TestModelDeckReferences:
    """Validate that model deck references point to valid targets."""

    @pytest.fixture(scope="class")
    def model_deck_blueprint(self) -> ModelDeckBlueprint:
        """Load actual model deck blueprint from TOML files."""
        model_deck_paths = ModelManager.get_model_deck_paths(deck_dir_path=str(config_manager.model_decks_dir_path))
        return load_model_deck_blueprint(model_deck_paths=model_deck_paths)

    @pytest.fixture(scope="class")
    def all_known_model_handles(self) -> dict[str, set[ModelType]]:
        """Collect all valid model handles with their types from the local backend TOML files.

        Returns:
            Mapping of model_handle -> ModelType
        """
        return self._get_local_backend_models()

    # ============================================================
    # Helper methods
    # ============================================================

    def _get_local_backend_models(self) -> dict[str, set[ModelType]]:
        """Parse all local backend TOML files to collect model handles with the model types they are declared as.

        Read as the loader reads a backend file: every root table but `[defaults]` is a model, its handle is its
        `handle` key or else its table name, and its type is its own, else the `[defaults]` one, else the default.
        A handle names one model per model type, so one handle may be declared as several.

        Returns:
            Mapping of model_handle -> the model types the backends declare it as
        """
        known_handles: dict[str, set[ModelType]] = {}
        backends_dir = config_manager.backends_dir_path

        toml_files = find_files_in_dir(backends_dir, pattern="*.toml", is_recursive=False)
        for toml_path in toml_files:
            backend_data = load_toml_from_path_if_exists(str(toml_path))
            if backend_data:
                for declared in list_declared_model_specs(document=backend_data):
                    known_handles.setdefault(declared.handle, set()).add(ModelType(declared.model_type))

        return known_handles

    def _find_invalid_preset_references(
        self,
        presets: Mapping[str, LLMSetting | ExtractSetting | ImgGenSetting | SearchSetting | DocGenSetting | JudgmentSetting],
        all_aliases: dict[str, str],
        all_waterfalls: dict[str, list[str]],
        known_model_handles: dict[str, set[ModelType]],
        expected_model_type: ModelType,
    ) -> list[tuple[str, str, str]]:
        """Find presets that reference invalid model targets.

        Args:
            presets: The presets dict to validate
            all_aliases: All available aliases for this model type
            all_waterfalls: All available waterfalls for this model type
            known_model_handles: Mapping of model handle -> the model types the backends declare it as
            expected_model_type: The expected model type for this deck (LLM, TEXT_EXTRACTOR, IMG_GEN)

        Returns:
            List of (preset_name, model_value, reason) tuples for invalid references
        """
        invalid_refs: list[tuple[str, str, str]] = []

        for preset_name, preset_setting in presets.items():
            model_value = preset_setting.model
            ref = ModelReference.parse(model_value)

            match ref.kind:
                case ModelReferenceKind.ALIAS:
                    if ref.name not in all_aliases:
                        invalid_refs.append((preset_name, model_value, f"alias '{ref.name}' not found"))
                case ModelReferenceKind.WATERFALL:
                    if ref.name not in all_waterfalls:
                        invalid_refs.append((preset_name, model_value, f"waterfall '{ref.name}' not found"))
                case ModelReferenceKind.PRESET:
                    invalid_refs.append((preset_name, model_value, "presets cannot reference other presets ($ prefix)"))
                case ModelReferenceKind.HANDLE:
                    if ref.name not in known_model_handles:
                        invalid_refs.append((preset_name, model_value, f"model handle '{ref.name}' not found in backends"))
                    elif expected_model_type not in known_model_handles[ref.name]:
                        actual_types = ", ".join(f"'{actual_type}'" for actual_type in sorted(known_model_handles[ref.name]))
                        invalid_refs.append(
                            (preset_name, model_value, f"model handle '{ref.name}' has type {actual_types} but expected '{expected_model_type}'")
                        )

        return invalid_refs

    # ============================================================
    # Parameterized validation tests
    # ============================================================

    def _get_deck_for_model_type(
        self,
        model_deck_blueprint: ModelDeckBlueprint,
        model_type: ModelType,
    ):
        """Get the appropriate deck from the blueprint based on model type."""
        match model_type:
            case ModelType.LLM:
                return model_deck_blueprint.llm
            case ModelType.TEXT_EXTRACTOR:
                return model_deck_blueprint.extract
            case ModelType.IMG_GEN:
                return model_deck_blueprint.img_gen
            case ModelType.SEARCH:
                return model_deck_blueprint.search
            case ModelType.DOC_GEN:
                return model_deck_blueprint.doc_gen
            case ModelType.JUDGMENT:
                return model_deck_blueprint.judgment

    @pytest.mark.parametrize(
        ("model_type", "deck_name"),
        [
            (ModelType.LLM, "LLM"),
            (ModelType.TEXT_EXTRACTOR, "Extract"),
            (ModelType.IMG_GEN, "ImgGen"),
            (ModelType.SEARCH, "Search"),
            (ModelType.DOC_GEN, "DocGen"),
            (ModelType.JUDGMENT, "Judgment"),
        ],
    )
    def test_aliases_reference_valid_targets(
        self,
        model_deck_blueprint: ModelDeckBlueprint,
        all_known_model_handles: dict[str, set[ModelType]],
        model_type: ModelType,
        deck_name: str,
    ):
        """Verify aliases point to valid targets (other aliases, waterfalls, or direct handles)."""
        deck = self._get_deck_for_model_type(model_deck_blueprint, model_type)

        invalid_refs = find_invalid_alias_targets(
            aliases=deck.aliases,
            all_aliases=deck.aliases,
            all_waterfalls=deck.waterfalls,
            known_model_handles=all_known_model_handles,
            expected_model_type=model_type,
        )

        if invalid_refs:
            error_lines = [f"Invalid {deck_name} alias references found:"]
            for alias_name, target_value, reason in invalid_refs:
                error_lines.append(f"  - '{alias_name}' -> '{target_value}': {reason}")
            pytest.fail("\n".join(error_lines))

    @pytest.mark.parametrize(
        ("model_type", "deck_name"),
        [
            (ModelType.LLM, "LLM"),
            (ModelType.TEXT_EXTRACTOR, "Extract"),
            (ModelType.IMG_GEN, "ImgGen"),
            (ModelType.SEARCH, "Search"),
            (ModelType.DOC_GEN, "DocGen"),
            (ModelType.JUDGMENT, "Judgment"),
        ],
    )
    def test_presets_reference_valid_models(
        self,
        model_deck_blueprint: ModelDeckBlueprint,
        all_known_model_handles: dict[str, set[ModelType]],
        model_type: ModelType,
        deck_name: str,
    ):
        """Verify preset model fields use valid aliases, waterfalls, or direct handles."""
        deck = self._get_deck_for_model_type(model_deck_blueprint, model_type)

        invalid_refs = self._find_invalid_preset_references(
            presets=deck.presets,
            all_aliases=deck.aliases,
            all_waterfalls=deck.waterfalls,
            known_model_handles=all_known_model_handles,
            expected_model_type=model_type,
        )

        if invalid_refs:
            error_lines = [f"Invalid {deck_name} preset model references found:"]
            for preset_name, model_value, reason in invalid_refs:
                error_lines.append(f"  - preset '{preset_name}' model='{model_value}': {reason}")
            pytest.fail("\n".join(error_lines))

    @pytest.mark.parametrize(
        ("model_type", "deck_name"),
        [
            (ModelType.LLM, "LLM"),
            (ModelType.TEXT_EXTRACTOR, "Extract"),
            (ModelType.IMG_GEN, "ImgGen"),
            (ModelType.SEARCH, "Search"),
            (ModelType.DOC_GEN, "DocGen"),
            (ModelType.JUDGMENT, "Judgment"),
        ],
    )
    def test_waterfalls_contain_valid_models(
        self,
        model_deck_blueprint: ModelDeckBlueprint,
        all_known_model_handles: dict[str, set[ModelType]],
        model_type: ModelType,
        deck_name: str,
    ):
        """Verify waterfall entries are valid aliases or direct model handles."""
        deck = self._get_deck_for_model_type(model_deck_blueprint, model_type)

        invalid_refs = find_invalid_waterfall_entries(
            waterfalls=deck.waterfalls,
            all_aliases=deck.aliases,
            known_model_handles=all_known_model_handles,
            expected_model_type=model_type,
        )

        if invalid_refs:
            error_lines = [f"Invalid {deck_name} waterfall entries found:"]
            for waterfall_name, index, entry_value, reason in invalid_refs:
                error_lines.append(f"  - waterfall '{waterfall_name}'[{index}]='{entry_value}': {reason}")
            pytest.fail("\n".join(error_lines))

    @pytest.mark.parametrize(
        ("model_type", "deck_name"),
        [
            (ModelType.LLM, "LLM"),
            (ModelType.TEXT_EXTRACTOR, "Extract"),
            (ModelType.IMG_GEN, "ImgGen"),
            (ModelType.SEARCH, "Search"),
            (ModelType.DOC_GEN, "DocGen"),
            (ModelType.JUDGMENT, "Judgment"),
        ],
    )
    def test_aliases_no_circular_references(
        self,
        model_deck_blueprint: ModelDeckBlueprint,
        model_type: ModelType,
        deck_name: str,
    ):
        """Detect alias chains that form cycles."""
        deck = self._get_deck_for_model_type(model_deck_blueprint, model_type)

        cycles = find_circular_aliases(aliases=deck.aliases)

        if cycles:
            error_lines = [f"Circular {deck_name} alias references detected:"]
            for _start_alias, cycle_path in cycles:
                cycle_str = " -> ".join(cycle_path)
                error_lines.append(f"  - {cycle_str}")
            pytest.fail("\n".join(error_lines))
