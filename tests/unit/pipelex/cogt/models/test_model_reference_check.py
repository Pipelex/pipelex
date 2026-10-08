from typing import Any

import pytest
from mthds.protocol.models import ModelCategory as MthdsModelCategory

from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenSetting
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.img_gen.img_gen_setting import ImgGenSetting
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_reference import ModelReference, ModelReferenceKind
from pipelex.cogt.models.model_reference_check import (
    AliasMatch,
    HandleMatch,
    ModelCheckCategory,
    ModelReferenceResolution,
    ModelReferenceVerdict,
    PresetMatch,
    WaterfallMatch,
    check_model_reference,
)
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.system.runtime import ProblemReaction


def _model_spec(name: str, model_type: ModelType) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="test_backend",
        name=name,
        sdk="test_sdk",
        model_type=model_type,
        model_id=f"test_model_{name}",
        costs={CostCategory.INPUT: 0.001, CostCategory.OUTPUT: 0.002},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=1000,
        max_prompt_images=None,
    )


def _make_deck(*, is_model_fallback_enabled: bool = True) -> ModelDeck:
    """A deck whose bindings cover every resolution: served, unserved, through a reference, cyclic, and names shared across types."""
    return ModelDeck(
        inference_models={
            "gpt-4o-mini": _model_spec("gpt-4o-mini", ModelType.LLM),
            "claude-x": _model_spec("claude-x", ModelType.LLM),
            "img-painter": _model_spec("img-painter", ModelType.IMG_GEN),
            "extract-engine": _model_spec("extract-engine", ModelType.TEXT_EXTRACTOR),
            "reportlab-pdf": _model_spec("reportlab-pdf", ModelType.DOC_GEN),
            # An extraction model whose name is also an LLM alias.
            "shared-name": _model_spec("shared-name", ModelType.TEXT_EXTRACTOR),
        },
        llm_default_temperature=0.7,
        llm_aliases={
            "best-gpt": "gpt-4o-mini",
            "best-claude": "claude-x",
            "spelled-handle": "handle:claude-x",
            "unserved-alias": "gpt-9",
            "cycle-a": "@cycle-b",
            "cycle-b": "@cycle-a",
            "shared-name": "gpt-4o-mini",
        },
        llm_waterfalls={
            "small-llm": ["gpt-9", "gpt-4o-mini"],
            "none-served": ["gpt-9", "gpt-10"],
            "via-alias": ["@best-claude"],
        },
        llm_presets={
            "cheap-llm": LLMSetting(model="gpt-4o-mini", temperature=0.5, description="Cheap and quick"),
            "premium": LLMSetting(model="@best-claude", temperature=0.5),
            "unserved-preset": LLMSetting(model="gpt-9", temperature=0.5),
        },
        llm_choice_defaults=LLMSettingChoicesDefaults(
            default_temperature=0.7,
            for_text=LLMSetting(model="gpt-4o-mini", temperature=0.7),
            for_object=LLMSetting(model="gpt-4o-mini", temperature=0.1),
        ),
        extract_choice_default="extract-engine",
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_aliases={"best-gpt": "img-painter"},
        img_gen_presets={"cheap-img": ImgGenSetting(model="img-painter")},
        img_gen_choice_default="img-painter",
        search_choice_default="@default-search",
        doc_gen_aliases={"default-pdf": "reportlab-pdf"},
        doc_gen_presets={"plain-pdf": DocGenSetting(model="@default-pdf", description="A plain PDF")},
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=is_model_fallback_enabled, missing_presets_reaction=ProblemReaction.NONE),
    )


def _check(reference: str, *, category: ModelCheckCategory | None = None, is_model_fallback_enabled: bool = True) -> ModelReferenceVerdict:
    return check_model_reference(
        model_deck=_make_deck(is_model_fallback_enabled=is_model_fallback_enabled),
        reference=ModelReference.parse(reference),
        category=category,
    )


def _assert_resolved(verdict: ModelReferenceVerdict) -> None:
    assert verdict.resolution == ModelReferenceResolution.RESOLVED, verdict
    assert verdict.suggestions == []
    assert verdict.other_kinds == []
    assert verdict.other_categories == []


def _assert_not_found(verdict: ModelReferenceVerdict) -> None:
    assert verdict.resolution == ModelReferenceResolution.NOT_FOUND, verdict
    assert verdict.matches == []


class TestModelReferenceCheck:
    def test_categories_are_the_protocols_in_its_order_then_doc_gen(self) -> None:
        assert [category.value for category in ModelCheckCategory] == [*(category.value for category in MthdsModelCategory), "doc_gen"]

    @pytest.mark.parametrize(
        ("reference", "expected_match"),
        [
            pytest.param(
                "$cheap-llm",
                PresetMatch(category=ModelCheckCategory.LLM, resolves_to="gpt-4o-mini", target="gpt-4o-mini", description="Cheap and quick"),
                id="preset-on-a-handle",
            ),
            pytest.param(
                "preset:premium",
                PresetMatch(category=ModelCheckCategory.LLM, resolves_to="claude-x", target="@best-claude", description=None),
                id="preset-on-an-alias-spelled-out",
            ),
            pytest.param(
                "$unserved-preset",
                PresetMatch(category=ModelCheckCategory.LLM, resolves_to=None, target="gpt-9", description=None),
                id="preset-on-an-unserved-model",
            ),
            pytest.param("@best-gpt", AliasMatch(category=ModelCheckCategory.LLM, resolves_to="gpt-4o-mini", target="gpt-4o-mini"), id="alias"),
            pytest.param("@unserved-alias", AliasMatch(category=ModelCheckCategory.LLM, resolves_to=None, target="gpt-9"), id="alias-unserved"),
            pytest.param("@cycle-a", AliasMatch(category=ModelCheckCategory.LLM, resolves_to=None, target="@cycle-b"), id="alias-cycle"),
            pytest.param(
                "~small-llm",
                WaterfallMatch(category=ModelCheckCategory.LLM, resolves_to="gpt-4o-mini", fallbacks=["gpt-9", "gpt-4o-mini"]),
                id="waterfall-first-served-step",
            ),
            pytest.param(
                "~none-served",
                WaterfallMatch(category=ModelCheckCategory.LLM, resolves_to=None, fallbacks=["gpt-9", "gpt-10"]),
                id="waterfall-none-served",
            ),
            pytest.param(
                "waterfall:via-alias",
                WaterfallMatch(category=ModelCheckCategory.LLM, resolves_to="claude-x", fallbacks=["@best-claude"]),
                id="waterfall-through-an-alias",
            ),
            pytest.param(
                "gpt-4o-mini",
                HandleMatch(
                    category=ModelCheckCategory.LLM,
                    resolves_to="gpt-4o-mini",
                    via=["$cheap-llm", "@best-gpt", "@shared-name", "~small-llm"],
                ),
                id="handle-with-the-deck-names-binding-it",
            ),
            pytest.param(
                "handle:claude-x",
                HandleMatch(category=ModelCheckCategory.LLM, resolves_to="claude-x", via=["@best-claude", "@spelled-handle"]),
                id="handle-spelled-out-bound-directly-only",
            ),
            pytest.param("best-gpt", HandleMatch(category=ModelCheckCategory.LLM, resolves_to="gpt-4o-mini", via=[]), id="bare-name-of-an-alias"),
            pytest.param("small-llm", HandleMatch(category=ModelCheckCategory.LLM, resolves_to="gpt-4o-mini", via=[]), id="bare-name-of-a-waterfall"),
            pytest.param(
                "shared-name",
                HandleMatch(category=ModelCheckCategory.LLM, resolves_to="gpt-4o-mini", via=[]),
                id="bare-name-of-an-alias-and-of-a-model-of-another-type",
            ),
        ],
    )
    def test_a_reference_resolved_in_its_category_says_what_it_is(self, reference: str, expected_match: Any) -> None:
        verdict = _check(reference, category=ModelCheckCategory.LLM)

        _assert_resolved(verdict)
        parsed = ModelReference.parse(reference)
        assert verdict.reference == reference
        assert verdict.kind == parsed.kind
        assert verdict.name == parsed.name
        assert verdict.category == ModelCheckCategory.LLM
        assert verdict.matches == [expected_match]

    def test_with_model_fallback_off_a_waterfall_resolves_to_its_first_step_alone(self) -> None:
        verdict = _check("~small-llm", category=ModelCheckCategory.LLM, is_model_fallback_enabled=False)

        _assert_resolved(verdict)
        assert verdict.matches == [WaterfallMatch(category=ModelCheckCategory.LLM, resolves_to=None, fallbacks=["gpt-9", "gpt-4o-mini"])]

    def test_with_model_fallback_off_the_bare_name_of_a_waterfall_does_not_resolve(self) -> None:
        verdict = _check("small-llm", category=ModelCheckCategory.LLM, is_model_fallback_enabled=False)

        _assert_not_found(verdict)
        assert verdict.other_kinds == ["~small-llm"]

    def test_a_model_of_another_category_does_not_make_a_bare_handle_resolve(self) -> None:
        verdict = _check("gpt-4o-mini", category=ModelCheckCategory.IMG_GEN)

        _assert_not_found(verdict)
        assert verdict.kind == ModelReferenceKind.HANDLE
        assert verdict.category == ModelCheckCategory.IMG_GEN
        assert verdict.other_categories == [ModelCheckCategory.LLM]

    def test_without_a_type_every_category_where_it_resolves_is_a_match_in_order(self) -> None:
        verdict = _check("shared-name")

        _assert_resolved(verdict)
        assert verdict.category is None
        assert verdict.matches == [
            HandleMatch(category=ModelCheckCategory.LLM, resolves_to="gpt-4o-mini", via=[]),
            HandleMatch(category=ModelCheckCategory.EXTRACT, resolves_to="shared-name", via=[]),
        ]

    def test_doc_gen_is_a_category_the_check_covers(self) -> None:
        verdict = _check("$plain-pdf")

        _assert_resolved(verdict)
        assert verdict.matches == [
            PresetMatch(category=ModelCheckCategory.DOC_GEN, resolves_to="reportlab-pdf", target="@default-pdf", description="A plain PDF")
        ]

    def test_a_misspelt_name_suggests_its_neighbours_once_each(self) -> None:
        """`@best-gp` is near `@best-gpt` in both the LLM and the image-generation categories, which the suggestions name once."""
        verdict = _check("@best-gp")

        _assert_not_found(verdict)
        assert verdict.suggestions.count("@best-gpt") == 1
        assert verdict.other_kinds == []
        assert verdict.other_categories == []

    def test_a_name_under_another_kind_is_in_other_kinds_written_with_its_sigil(self) -> None:
        verdict = _check("$best-gpt")

        _assert_not_found(verdict)
        assert verdict.other_kinds == ["@best-gpt"]

    def test_suggestions_of_another_kind_are_names_without_labels(self) -> None:
        verdict = _check("$best-claud", category=ModelCheckCategory.LLM)

        _assert_not_found(verdict)
        assert "@best-claude" in verdict.suggestions
        assert all("(" not in suggestion for suggestion in verdict.suggestions), verdict.suggestions

    def test_a_reference_asked_in_another_category_names_the_categories_where_it_resolves(self) -> None:
        verdict = _check("@best-gpt", category=ModelCheckCategory.SEARCH)

        _assert_not_found(verdict)
        assert verdict.other_categories == [ModelCheckCategory.LLM, ModelCheckCategory.IMG_GEN]

    def test_a_reference_held_nowhere_is_not_found_with_nothing_to_offer(self) -> None:
        verdict = _check("~held-nowhere-at-all", category=ModelCheckCategory.JUDGMENT)

        _assert_not_found(verdict)
        assert verdict.suggestions == []
        assert verdict.other_kinds == []
        assert verdict.other_categories == []

    def test_the_verdict_echoes_the_trimmed_reference_and_its_parsing(self) -> None:
        verdict = _check("  alias:best-gpt  ", category=ModelCheckCategory.LLM)

        assert verdict.reference == "alias:best-gpt"
        assert verdict.kind == ModelReferenceKind.ALIAS
        assert verdict.name == "best-gpt"

    @pytest.mark.parametrize(
        ("reference", "match_keys"),
        [
            pytest.param("$premium", {"category", "resolves_to", "target", "description"}, id="preset"),
            pytest.param("@unserved-alias", {"category", "resolves_to", "target"}, id="alias"),
            pytest.param("~none-served", {"category", "resolves_to", "fallbacks"}, id="waterfall"),
            pytest.param("claude-x", {"category", "resolves_to", "via"}, id="handle"),
        ],
    )
    def test_a_match_carries_the_fields_of_its_kind_and_nulls_only_where_they_apply(self, reference: str, match_keys: set[str]) -> None:
        dumped = _check(reference, category=ModelCheckCategory.LLM).model_dump(mode="json")

        assert set(dumped) == {"reference", "kind", "name", "category", "resolution", "matches", "suggestions", "other_kinds", "other_categories"}
        (match,) = dumped["matches"]
        assert set(match) == match_keys
