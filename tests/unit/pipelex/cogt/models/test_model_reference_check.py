from typing import Any

import pytest
from mthds.protocol.models import ModelCategory as MthdsModelCategory
from pytest_mock import MockerFixture

from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenSetting
from pipelex.cogt.exceptions import ModelChoiceNotFoundError, ModelNotFoundError, ModelWaterfallError
from pipelex.cogt.extract.extract_setting import ExtractSetting
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.img_gen.img_gen_setting import ImgGenSetting
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_deck_check import check_llm_choice_with_deck
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
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.system.runtime import ProblemReaction

_DECK_LOG_TARGET = "pipelex.cogt.models.model_deck.log"
_DECK_CHECK_GET_MODEL_DECK_TARGET = "pipelex.cogt.models.model_deck_check.get_model_deck"


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


def _deck_with(
    *,
    inference_models: dict[str, InferenceModelSpec],
    is_model_fallback_enabled: bool = True,
    **bindings: Any,
) -> ModelDeck:
    """A deck serving `inference_models` with the aliases, waterfalls and presets `bindings` names, by their deck field."""
    return ModelDeck(
        inference_models=inference_models,
        llm_default_temperature=0.7,
        llm_choice_defaults=LLMSettingChoicesDefaults(
            default_temperature=0.7,
            for_text=LLMSetting(model="gpt-4o-mini", temperature=0.7),
            for_object=LLMSetting(model="gpt-4o-mini", temperature=0.1),
        ),
        extract_choice_default="extract-engine",
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_choice_default="img-painter",
        search_choice_default="@default-search",
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=is_model_fallback_enabled, missing_presets_reaction=ProblemReaction.NONE),
        **bindings,
    )


# The prefix of each model type's binding fields on the deck (`llm_aliases`, `extract_waterfalls`, ...).
_BINDING_PREFIXES: dict[ModelType, str] = {
    ModelType.LLM: "llm",
    ModelType.TEXT_EXTRACTOR: "extract",
    ModelType.IMG_GEN: "img_gen",
    ModelType.SEARCH: "search",
    ModelType.DOC_GEN: "doc_gen",
    ModelType.JUDGMENT: "judgment",
}


def _preset(*, model_type: ModelType, model: str) -> LLMSetting | ExtractSetting | ImgGenSetting | SearchSetting | DocGenSetting | JudgmentSetting:
    match model_type:
        case ModelType.LLM:
            return LLMSetting(model=model, temperature=0.5)
        case ModelType.TEXT_EXTRACTOR:
            return ExtractSetting(model=model)
        case ModelType.IMG_GEN:
            return ImgGenSetting(model=model)
        case ModelType.SEARCH:
            return SearchSetting(model=model)
        case ModelType.DOC_GEN:
            return DocGenSetting(model=model)
        case ModelType.JUDGMENT:
            return JudgmentSetting(model=model)


def _make_collision_deck(*, model_type: ModelType) -> ModelDeck:
    """A deck of one model type where models, aliases and waterfalls share names.

    `shared` is a model, an alias to `other` and a waterfall to `other`; `twin` is no model, an alias to
    `other`, a waterfall to `shared` and a preset bound to the waterfall `~twin`.
    """
    prefix = _BINDING_PREFIXES[model_type]
    bindings: dict[str, Any] = {
        f"{prefix}_aliases": {"shared": "other", "twin": "other"},
        f"{prefix}_waterfalls": {"shared": ["other"], "twin": ["shared"]},
        f"{prefix}_presets": {"twin": _preset(model_type=model_type, model="~twin")},
    }
    return _deck_with(
        inference_models={
            "shared": _model_spec("shared", model_type),
            "other": _model_spec("other", model_type),
        },
        **bindings,
    )


def _model_the_run_calls(*, model_deck: ModelDeck, reference: str, model_type: ModelType) -> str:
    """The model a pipe of this type naming `reference` calls: its setting, as a run builds it, then the deck's lookup of the setting's model."""
    setting_model: str
    match model_type:
        case ModelType.LLM:
            setting_model = model_deck.get_llm_setting(llm_choice=reference).model
        case ModelType.TEXT_EXTRACTOR:
            setting_model = model_deck.get_extract_setting(extract_choice=reference).model
        case ModelType.IMG_GEN:
            setting_model = model_deck.get_img_gen_setting(img_gen_choice=reference).model
        case ModelType.SEARCH:
            setting_model = model_deck.get_search_setting(search_choice=reference).model
        case ModelType.DOC_GEN:
            setting_model = model_deck.get_doc_gen_setting(doc_gen_choice=reference).model
        case ModelType.JUDGMENT:
            setting_model = model_deck.get_judgment_setting(judgment_choice=reference).model
    return model_deck.get_required_inference_model(model_handle=setting_model, model_type=model_type).name


def _category_of(model_type: ModelType) -> ModelCheckCategory:
    return next(category for category in ModelCheckCategory if category.model_type == model_type)


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

    @pytest.mark.parametrize(
        ("reference", "expected_model"),
        [
            pytest.param("~twin", "shared", id="waterfall-named-like-an-alias"),
            pytest.param("waterfall:twin", "shared", id="waterfall-namespace"),
            pytest.param("@twin", "other", id="alias-named-like-a-waterfall"),
            pytest.param("twin", "other", id="bare-name-of-an-alias-and-a-waterfall"),
            pytest.param("~shared", "other", id="waterfall-named-like-a-model"),
            pytest.param("@shared", "other", id="alias-named-like-a-model"),
            pytest.param("shared", "shared", id="bare-name-of-a-model"),
            pytest.param("$twin", "shared", id="preset-bound-to-a-waterfall"),
        ],
    )
    @pytest.mark.parametrize("model_type", list(ModelType))
    def test_the_verdict_names_the_model_a_run_calls_when_names_collide(self, reference: str, expected_model: str, model_type: ModelType) -> None:
        """A sigiled reference resolves by its sigil in the check and in a run alike, whatever shares its name."""
        model_deck = _make_collision_deck(model_type=model_type)

        verdict = check_model_reference(model_deck=model_deck, reference=ModelReference.parse(reference), category=_category_of(model_type))

        _assert_resolved(verdict)
        (match,) = verdict.matches
        assert match.resolves_to == expected_model
        assert _model_the_run_calls(model_deck=model_deck, reference=reference, model_type=model_type) == expected_model

    @pytest.mark.parametrize("reference", ["@cycle-a", "~cycle-waterfall"])
    def test_an_alias_and_a_waterfall_leading_to_each_other_end_as_no_model(self, reference: str) -> None:
        """A cycle through an alias and a waterfall resolves to nothing in the check, and a run refuses it cleanly."""
        model_deck = _deck_with(
            inference_models={"gpt-4o-mini": _model_spec("gpt-4o-mini", ModelType.LLM)},
            llm_aliases={"cycle-a": "~cycle-waterfall"},
            llm_waterfalls={"cycle-waterfall": ["@cycle-a"]},
        )

        verdict = check_model_reference(model_deck=model_deck, reference=ModelReference.parse(reference), category=ModelCheckCategory.LLM)

        _assert_resolved(verdict)
        (match,) = verdict.matches
        assert match.resolves_to is None
        with pytest.raises(ModelNotFoundError):
            _model_the_run_calls(model_deck=model_deck, reference=reference, model_type=ModelType.LLM)

    @pytest.mark.parametrize(
        ("second_step", "expected_model"),
        [
            pytest.param("img-painter", "img-painter", id="next-step-served"),
            pytest.param("img-unserved", None, id="next-step-unserved"),
        ],
    )
    def test_a_waterfall_step_leading_back_to_its_waterfall_is_a_step_no_model_serves(self, second_step: str, expected_model: str | None) -> None:
        """An image-generation waterfall named like an LLM, whose first step is its own name: that step leads back to the waterfall.

        The step ends as no model, as an unserved one does, so the waterfall goes on to its next step.
        """
        model_deck = _deck_with(
            inference_models={
                "gpt-4o-mini": _model_spec("gpt-4o-mini", ModelType.LLM),
                "img-painter": _model_spec("img-painter", ModelType.IMG_GEN),
            },
            img_gen_waterfalls={"gpt-4o-mini": ["gpt-4o-mini", second_step]},
        )

        verdict = check_model_reference(model_deck=model_deck, reference=ModelReference.parse("gpt-4o-mini"), category=ModelCheckCategory.IMG_GEN)

        _assert_resolved(verdict)
        assert verdict.matches == [HandleMatch(category=ModelCheckCategory.IMG_GEN, resolves_to=expected_model, via=["~gpt-4o-mini"])]
        if expected_model is None:
            with pytest.raises(ModelNotFoundError):
                _model_the_run_calls(model_deck=model_deck, reference="gpt-4o-mini", model_type=ModelType.IMG_GEN)
        else:
            assert _model_the_run_calls(model_deck=model_deck, reference="gpt-4o-mini", model_type=ModelType.IMG_GEN) == expected_model

    def test_the_check_logs_nothing_and_leaves_the_fallback_notice_to_the_run(self, mocker: MockerFixture) -> None:
        """A check reads the run's lookup without its side effects; the run that follows still logs what it always logged."""
        model_deck = _make_deck()
        deck_log = mocker.patch(_DECK_LOG_TARGET)

        for reference in ("~small-llm", "small-llm", "@cycle-a", "~none-served", "$premium", "gpt-9", "@unserved-alias"):
            check_model_reference(model_deck=model_deck, reference=ModelReference.parse(reference), category=None)

        assert deck_log.mock_calls == []
        model_deck.get_optional_inference_model(model_handle="~small-llm", model_type=ModelType.LLM)
        deck_log.info.assert_called_once()
        model_deck.get_optional_inference_model(model_handle="@cycle-a", model_type=ModelType.LLM)
        deck_log.warning.assert_called_once()

    def test_with_model_fallback_off_a_bare_waterfall_name_is_refused_by_the_check_the_validation_and_the_run(self, mocker: MockerFixture) -> None:
        """A pipe's bare name reaches the deck's lookup only through its setting, which refuses a waterfall name while fallback is off.

        The deck's lookup alone would serve the waterfall's first step, but a pipe never reaches it with this name.
        """
        model_deck = _make_deck(is_model_fallback_enabled=False)
        mocker.patch(_DECK_CHECK_GET_MODEL_DECK_TARGET, return_value=model_deck)

        verdict = check_model_reference(model_deck=model_deck, reference=ModelReference.parse("small-llm"), category=ModelCheckCategory.LLM)

        _assert_not_found(verdict)
        with pytest.raises(ModelChoiceNotFoundError):
            check_llm_choice_with_deck("small-llm")
        with pytest.raises(ModelChoiceNotFoundError):
            model_deck.get_llm_setting(llm_choice="small-llm")

    @pytest.mark.parametrize(
        ("waterfalls", "aliases"),
        [
            pytest.param({"outer": ["~inner", "gpt-4o-mini"], "inner": ["~outer"]}, {}, id="nested-waterfall-leading-back"),
            pytest.param({"outer": ["~inner", "gpt-4o-mini"], "inner": ["unserved-model"]}, {}, id="nested-waterfall-unserved"),
            pytest.param(
                {"outer": ["@to-inner", "gpt-4o-mini"], "inner": ["unserved-model"]}, {"to-inner": "~inner"}, id="alias-to-an-unserved-waterfall"
            ),
        ],
    )
    def test_a_step_whose_waterfall_runs_out_lets_its_waterfall_go_on(self, waterfalls: dict[str, list[str]], aliases: dict[str, str]) -> None:
        """A step reaching a waterfall none of whose steps is served serves no model, so the outer waterfall tries its next step."""
        model_deck = _deck_with(
            inference_models={"gpt-4o-mini": _model_spec("gpt-4o-mini", ModelType.LLM)},
            llm_waterfalls=waterfalls,
            llm_aliases=aliases,
        )

        verdict = check_model_reference(model_deck=model_deck, reference=ModelReference.parse("~outer"), category=ModelCheckCategory.LLM)

        _assert_resolved(verdict)
        assert verdict.matches == [WaterfallMatch(category=ModelCheckCategory.LLM, resolves_to="gpt-4o-mini", fallbacks=waterfalls["outer"])]
        assert _model_the_run_calls(model_deck=model_deck, reference="~outer", model_type=ModelType.LLM) == "gpt-4o-mini"

    def test_with_model_fallback_off_a_nested_waterfall_refusing_its_fallback_refuses_the_outer_one(self) -> None:
        """The refusal of a fallback while fallbacks are disabled is not a waterfall running out: it holds through the outer waterfall."""
        model_deck = _deck_with(
            inference_models={
                "gpt-4o-mini": _model_spec("gpt-4o-mini", ModelType.LLM),
                "claude-x": _model_spec("claude-x", ModelType.LLM),
            },
            is_model_fallback_enabled=False,
            llm_waterfalls={"outer": ["~inner", "claude-x"], "inner": ["unserved-model", "gpt-4o-mini"]},
        )

        verdict = check_model_reference(model_deck=model_deck, reference=ModelReference.parse("~outer"), category=ModelCheckCategory.LLM)

        assert verdict.matches == [WaterfallMatch(category=ModelCheckCategory.LLM, resolves_to=None, fallbacks=["~inner", "claude-x"])]
        with pytest.raises(ModelNotFoundError) as exc_info:
            _model_the_run_calls(model_deck=model_deck, reference="~outer", model_type=ModelType.LLM)
        assert not isinstance(exc_info.value, ModelWaterfallError)
        assert "model fallbacks are disabled" in exc_info.value.message

    def test_a_handle_reference_names_a_literal_handle(self, mocker: MockerFixture) -> None:
        """`handle:@best-gpt` names a model handle spelled `@best-gpt`, not the alias: the check, the validation and the run refuse it alike."""
        model_deck = _make_deck()
        mocker.patch(_DECK_CHECK_GET_MODEL_DECK_TARGET, return_value=model_deck)

        verdict = check_model_reference(model_deck=model_deck, reference=ModelReference.parse("handle:@best-gpt"), category=ModelCheckCategory.LLM)

        _assert_not_found(verdict)
        assert model_deck.is_reference_defined(reference=ModelReference.parse("handle:@best-gpt"), model_type=ModelType.LLM) is False
        with pytest.raises(ModelChoiceNotFoundError):
            check_llm_choice_with_deck("handle:@best-gpt")
        with pytest.raises(ModelChoiceNotFoundError):
            model_deck.get_llm_setting(llm_choice="handle:@best-gpt")
        with pytest.raises(ModelChoiceNotFoundError):
            model_deck.check_llm_choice(llm_choice="handle:@best-gpt")

    @pytest.mark.parametrize("literal_name", ["@named", "~named", "$named", "alias:named"])
    @pytest.mark.parametrize(
        "bindings",
        [
            pytest.param({}, id="no-colliding-binding"),
            pytest.param({"llm_aliases": {"named": "other"}, "llm_waterfalls": {"named": ["other"]}}, id="colliding-alias-and-waterfall"),
        ],
    )
    def test_a_served_handle_spelled_like_a_reference_is_called_literally(
        self, mocker: MockerFixture, literal_name: str, bindings: dict[str, Any]
    ) -> None:
        """`handle:@named` names the model served as `@named`: the validation, the run and the check all select it, not the alias."""
        model_deck = _deck_with(
            inference_models={
                literal_name: _model_spec(literal_name, ModelType.LLM),
                "other": _model_spec("other", ModelType.LLM),
            },
            **bindings,
        )
        mocker.patch(_DECK_CHECK_GET_MODEL_DECK_TARGET, return_value=model_deck)
        reference = f"handle:{literal_name}"

        check_llm_choice_with_deck(reference)
        model_deck.validate_inference_models()
        assert _model_the_run_calls(model_deck=model_deck, reference=reference, model_type=ModelType.LLM) == literal_name
        verdict = check_model_reference(model_deck=model_deck, reference=ModelReference.parse(reference), category=ModelCheckCategory.LLM)
        _assert_resolved(verdict)
        (match,) = verdict.matches
        assert match.resolves_to == literal_name

    def test_a_suggested_handle_spelled_like_a_reference_is_written_with_its_namespace(self) -> None:
        """A suggestion is a reference a caller may write back, so a handle spelled like an alias is offered as `handle:@named`."""
        model_deck = _deck_with(inference_models={"@named": _model_spec("@named", ModelType.LLM)})

        verdict = check_model_reference(model_deck=model_deck, reference=ModelReference.parse("handle:@namedd"), category=ModelCheckCategory.LLM)

        _assert_not_found(verdict)
        assert "handle:@named" in verdict.suggestions
