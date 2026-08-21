"""Unit coverage for ``ModelManager._collect_deck_referenced_handles`` and ``_extract_choice_handle``.

These two classmethods feed the gateway-membership check in ``ModelManager.setup``:
``_collect_deck_referenced_handles`` gathers every ``(handle, model_type)`` the deck advertises
as usable (presets + choice defaults), and ``_extract_choice_handle`` normalises a ``*ModelChoice``
union to a raw handle string. Aliases and waterfalls are intentionally NOT enumerated directly —
they are reachable through preset/choice references and the resolver walks them.
"""

from __future__ import annotations

import pytest

from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.extract.extract_setting import ExtractModelChoice, ExtractSetting
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice, ImgGenSetting
from pipelex.cogt.llm.llm_setting import LLMModelChoice, LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.cogt.models.model_reference import ModelReference
from pipelex.cogt.search.search_setting import SearchModelChoice, SearchSetting
from pipelex.system.runtime import ProblemReaction

# Both methods are private leaves of the membership resolver; aliasing them keeps the call
# sites in the tests free of repeated noqa/ignore pragmas.
_collect_deck_referenced_handles = ModelManager._collect_deck_referenced_handles  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
_extract_choice_handle = ModelManager._extract_choice_handle  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]


def _make_deck(
    *,
    llm_presets: dict[str, LLMSetting] | None = None,
    llm_for_text: LLMModelChoice = "llm-text-handle",
    llm_for_object: LLMModelChoice = "llm-object-handle",
    extract_presets: dict[str, ExtractSetting] | None = None,
    extract_choice_default: ExtractModelChoice = "extract-default-handle",
    img_gen_presets: dict[str, ImgGenSetting] | None = None,
    img_gen_choice_default: ImgGenModelChoice = "img-gen-default-handle",
    search_presets: dict[str, SearchSetting] | None = None,
    search_choice_default: SearchModelChoice = "search-default-handle",
    llm_aliases: dict[str, str] | None = None,
    llm_waterfalls: dict[str, list[str]] | None = None,
) -> ModelDeck:
    """Build a minimal real ModelDeck with all required fields, mirroring test_model_deck.py."""
    return ModelDeck(
        inference_models={},
        # LLM
        llm_default_temperature=0.7,
        llm_aliases=llm_aliases or {},
        llm_waterfalls=llm_waterfalls or {},
        llm_presets=llm_presets or {},
        llm_choice_defaults=LLMSettingChoicesDefaults(
            default_temperature=0.7,
            for_text=llm_for_text,
            for_object=llm_for_object,
        ),
        # Extract
        extract_aliases={},
        extract_waterfalls={},
        extract_presets=extract_presets or {},
        extract_choice_default=extract_choice_default,
        # ImgGen
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_aliases={},
        img_gen_waterfalls={},
        img_gen_presets=img_gen_presets or {},
        img_gen_choice_default=img_gen_choice_default,
        # Search
        search_aliases={},
        search_waterfalls={},
        search_presets=search_presets or {},
        search_choice_default=search_choice_default,
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=True, missing_presets_reaction=ProblemReaction.NONE),
    )


class TestCollectDeckReferencedHandles:
    @pytest.mark.parametrize(
        ("choice", "expected"),
        [
            (None, None),
            ("raw-handle", "raw-handle"),
            (ModelReference.parse("ref-handle"), "ref-handle"),
            (LLMSetting(model="llm-model", temperature=0.5), "llm-model"),
            (ExtractSetting(model="extract-model"), "extract-model"),
            (ImgGenSetting(model="img-gen-model"), "img-gen-model"),
            (SearchSetting(model="search-model"), "search-model"),
        ],
    )
    def test_extract_choice_handle(
        self,
        choice: LLMSetting | ExtractSetting | ImgGenSetting | SearchSetting | ModelReference | str | None,
        expected: str | None,
    ) -> None:
        """_extract_choice_handle normalises every choice shape: None, raw str, ModelReference, typed setting."""
        assert _extract_choice_handle(choice) == expected

    def test_collects_presets_and_choice_defaults_for_all_types(self) -> None:
        """_collect_deck_referenced_handles yields a (handle, ModelType) pair for every preset and choice default."""
        deck = _make_deck(
            llm_presets={
                "fast": LLMSetting(model="llm-preset-fast", temperature=0.3),
                "smart": LLMSetting(model="llm-preset-smart", temperature=0.7),
            },
            llm_for_text="llm-text-handle",
            llm_for_object="llm-object-handle",
            extract_presets={"doc": ExtractSetting(model="extract-preset-doc")},
            extract_choice_default="extract-default-handle",
            img_gen_presets={"basic": ImgGenSetting(model="img-gen-preset-basic")},
            img_gen_choice_default="img-gen-default-handle",
            search_presets={"web": SearchSetting(model="search-preset-web")},
            search_choice_default="search-default-handle",
        )

        collected = _collect_deck_referenced_handles(deck)

        assert set(collected) == {
            ("llm-preset-fast", ModelType.LLM),
            ("llm-preset-smart", ModelType.LLM),
            ("llm-text-handle", ModelType.LLM),
            ("llm-object-handle", ModelType.LLM),
            ("extract-preset-doc", ModelType.TEXT_EXTRACTOR),
            ("extract-default-handle", ModelType.TEXT_EXTRACTOR),
            ("img-gen-preset-basic", ModelType.IMG_GEN),
            ("img-gen-default-handle", ModelType.IMG_GEN),
            ("search-preset-web", ModelType.SEARCH),
            ("search-default-handle", ModelType.SEARCH),
        }

    def test_aliases_and_waterfalls_are_not_enumerated_directly(self) -> None:
        """Alias/waterfall keys and their targets are not surfaced unless referenced by a preset/choice."""
        deck = _make_deck(
            llm_aliases={"my-alias": "alias-target-handle"},
            llm_waterfalls={"my-waterfall": ["waterfall-target-handle"]},
        )

        handles = {handle for handle, _ in _collect_deck_referenced_handles(deck)}

        assert "my-alias" not in handles
        assert "alias-target-handle" not in handles
        assert "my-waterfall" not in handles
        assert "waterfall-target-handle" not in handles
