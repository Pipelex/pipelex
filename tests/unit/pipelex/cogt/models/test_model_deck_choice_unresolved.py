"""Whose fault an unresolved model choice is: the method's when its step named the model, the deployment's when the deck did.

The deck's lookups refuse a reference they do not resolve as ``ModelChoiceNotFoundError``, ``model.unknown`` and
caller-facing, which is right for a model the method named. A default or an override the deck names itself reaches the
same lookups when a step names no model, and a miss there is the deck's: ``ModelDeckChoiceUnresolvedError``, which a
caller cannot fix by changing their input, reports ``model.unavailable`` for a bare handle no backend serves and
``pipelex.config.invalid`` for a preset, alias or waterfall the deck does not define, and is never caller-facing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.doc_gen.doc_gen_engine import resolve_doc_gen_setting
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.exceptions import ModelChoiceNotFoundError, ModelDeckChoiceUnresolvedError
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.llm.llm_setting import LLMSettingChoices, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.kernel.extract_ops import resolve_extract_setting
from pipelex.kernel.img_gen_ops import resolve_img_gen_setting
from pipelex.kernel.judgment_ops import judgment_setting_of_choice
from pipelex.kernel.llm_ops import resolve_llm_setting_for_object, resolve_llm_setting_for_text
from pipelex.kernel.search_ops import resolve_search_setting
from pipelex.system.runtime import ProblemReaction

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture

    from pipelex.errors.error_codes import ErrorCode

_DECK_ACCESSORS: tuple[str, ...] = (
    "pipelex.kernel.llm_ops.get_model_deck",
    "pipelex.kernel.extract_ops.get_model_deck",
    "pipelex.kernel.img_gen_ops.get_model_deck",
    "pipelex.kernel.search_ops.get_model_deck",
    "pipelex.kernel.judgment_ops.get_model_deck",
    "pipelex.cogt.doc_gen.doc_gen_engine.get_model_deck",
)


def _served_model(*, name: str, model_type: ModelType) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="test_backend",
        name=name,
        sdk="test_sdk",
        model_type=model_type,
        model_id=f"test_{name}",
        costs={CostCategory.INPUT: 0.001, CostCategory.OUTPUT: 0.002},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=1000,
        max_prompt_images=None,
    )


def _make_deck(*, llm_choice_overrides: LLMSettingChoices | None = None) -> ModelDeck:
    """A deck serving one LLM and one image model, every default of which names a model it does not resolve."""
    return ModelDeck(
        inference_models=ModelSpecIndex.make_from_specs(
            model_specs=[
                _served_model(name="served-llm", model_type=ModelType.LLM),
                _served_model(name="served-img-gen", model_type=ModelType.IMG_GEN),
            ]
        ),
        llm_default_temperature=0.7,
        llm_aliases={},
        llm_waterfalls={},
        llm_presets={},
        llm_choice_defaults=LLMSettingChoicesDefaults(
            default_temperature=0.7,
            # A stale scalar default: a handle the deck once served.
            for_text="stale-text-model",
            for_object="$missing-object-preset",
        ),
        llm_choice_overrides=llm_choice_overrides or LLMSettingChoices(for_text=None, for_object=None),
        extract_aliases={},
        extract_waterfalls={},
        extract_presets={},
        extract_choice_default="$missing-extract-preset",
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_aliases={},
        img_gen_waterfalls={},
        img_gen_presets={},
        img_gen_choice_default="stale-img-gen-model",
        search_aliases={},
        search_waterfalls={},
        search_presets={},
        search_choice_default="~missing-search-waterfall",
        doc_gen_choice_defaults={"pdf.layout": "@missing-doc-gen-alias"},
        judgment_choice_default="@missing-judgment-alias",
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=True, missing_presets_reaction=ProblemReaction.NONE),
    )


def _use_deck(mocker: MockerFixture, *, model_deck: ModelDeck) -> None:
    for accessor in _DECK_ACCESSORS:
        mocker.patch(accessor, return_value=model_deck)


def _resolve_doc_gen_default() -> Any:
    return resolve_doc_gen_setting(doc_gen_choice=None, doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT, pipe_code=None)


def _deck_llm_setting_of_img_gen_model(model_deck: ModelDeck) -> Any:
    return model_deck.get_llm_setting(llm_choice="served-img-gen")


def _deck_check_of_img_gen_model(model_deck: ModelDeck) -> Any:
    return model_deck.check_llm_choice(llm_choice="served-img-gen")


class TestModelDeckChoiceUnresolved:
    @pytest.mark.parametrize(
        ("_topic", "resolve", "expected_deck_setting", "expected_code"),
        [
            ("llm_text_stale_handle", resolve_llm_setting_for_text, "llm.choice_defaults.for_text", CoreCode.MODEL_UNAVAILABLE),
            ("llm_object_preset", resolve_llm_setting_for_object, "llm.choice_defaults.for_object", PipelexErrorCode.CONFIG_INVALID),
            ("extract_preset", resolve_extract_setting, "extract.choice_default", PipelexErrorCode.CONFIG_INVALID),
            ("img_gen_stale_handle", resolve_img_gen_setting, "img_gen.choice_default", CoreCode.MODEL_UNAVAILABLE),
            ("search_waterfall", resolve_search_setting, "search.choice_default", PipelexErrorCode.CONFIG_INVALID),
            ("judgment_alias", judgment_setting_of_choice, "judgment.choice_default", PipelexErrorCode.CONFIG_INVALID),
            ("doc_gen_alias", _resolve_doc_gen_default, 'doc_gen.choice_defaults["pdf.layout"]', PipelexErrorCode.CONFIG_INVALID),
        ],
    )
    def test_a_deck_default_that_does_not_resolve_is_the_deployment_s_fault(
        self,
        mocker: MockerFixture,
        _topic: str,
        resolve: Callable[[], Any],
        expected_deck_setting: str,
        expected_code: ErrorCode,
    ) -> None:
        """A step naming no model runs on the deck's default, so the deck's miss is no input of the caller's."""
        _use_deck(mocker, model_deck=_make_deck())

        with pytest.raises(ModelDeckChoiceUnresolvedError) as exc_info:
            resolve()

        unresolved = exc_info.value
        # Still a choice the deck does not resolve, so a handler that leaves an unresolvable choice to the run skips it.
        assert isinstance(unresolved, ModelChoiceNotFoundError)
        assert unresolved.deck_setting == expected_deck_setting
        assert expected_deck_setting in unresolved.message
        assert unresolved.resolve_error_code() == expected_code
        assert isinstance(unresolved.__cause__, ModelChoiceNotFoundError)
        report = unresolved.to_error_report()
        assert report.caller_facing_message is False
        assert report.error_domain != "input"

    @pytest.mark.parametrize(
        ("_topic", "resolve", "expected_choice"),
        [
            ("llm_text", lambda: resolve_llm_setting_for_text(llm_choice="$unknown-method-preset"), "$unknown-method-preset"),
            ("llm_object", lambda: resolve_llm_setting_for_object(llm_choice="unknown-method-model"), "unknown-method-model"),
            ("extract", lambda: resolve_extract_setting(extract_choice="@unknown-method-alias"), "@unknown-method-alias"),
            ("img_gen", lambda: resolve_img_gen_setting(img_gen_choice="unknown-method-model"), "unknown-method-model"),
            ("judgment", lambda: judgment_setting_of_choice(judgment_choice="~unknown-method-waterfall"), "~unknown-method-waterfall"),
        ],
    )
    def test_a_model_the_step_names_stays_the_caller_s_input(
        self,
        mocker: MockerFixture,
        _topic: str,
        resolve: Callable[[], Any],
        expected_choice: str,
    ) -> None:
        """The method named the model, so the miss is the method's own: `model.unknown`, caller-facing, input domain."""
        _use_deck(mocker, model_deck=_make_deck())

        with pytest.raises(ModelChoiceNotFoundError) as exc_info:
            resolve()

        not_found = exc_info.value
        assert not isinstance(not_found, ModelDeckChoiceUnresolvedError)
        assert not_found.model_choice == expected_choice
        assert not_found.resolve_error_code() == CoreCode.MODEL_UNKNOWN
        report = not_found.to_error_report()
        assert report.caller_facing_message is True
        assert report.error_domain == "input"

    @pytest.mark.parametrize(
        ("_topic", "llm_choice_overrides", "expected_deck_setting", "expected_code"),
        [
            (
                "preset",
                LLMSettingChoices(for_text="$missing-override-preset", for_object=None),
                "llm.choice_overrides.for_text",
                PipelexErrorCode.CONFIG_INVALID,
            ),
            (
                "stale_handle",
                LLMSettingChoices(for_text=None, for_object="stale-override-model"),
                "llm.choice_overrides.for_object",
                CoreCode.MODEL_UNAVAILABLE,
            ),
        ],
    )
    def test_a_deck_override_that_does_not_resolve_refuses_the_deck(
        self,
        _topic: str,
        llm_choice_overrides: LLMSettingChoices,
        expected_deck_setting: str,
        expected_code: ErrorCode,
    ) -> None:
        """The deck checks its overrides when it loads, and a miss there is the deck's, before any caller is involved."""
        with pytest.raises(ModelDeckChoiceUnresolvedError) as exc_info:
            _make_deck(llm_choice_overrides=llm_choice_overrides)

        unresolved = exc_info.value
        assert unresolved.deck_setting == expected_deck_setting
        assert unresolved.resolve_error_code() == expected_code
        assert unresolved.to_error_report().caller_facing_message is False

    @pytest.mark.parametrize(
        ("_topic", "resolve"),
        [
            ("deck_setting", _deck_llm_setting_of_img_gen_model),
            ("deck_check", _deck_check_of_img_gen_model),
        ],
    )
    def test_a_handle_served_only_as_another_type_is_a_capability_the_model_lacks(
        self,
        _topic: str,
        resolve: Callable[[ModelDeck], Any],
    ) -> None:
        """The model exists and is served, only not as the type the step needs: not an unknown model."""
        with pytest.raises(ModelChoiceNotFoundError) as exc_info:
            resolve(_make_deck())

        not_found = exc_info.value
        assert "served by the model deck, but not as an LLM" in not_found.message
        assert not_found.resolve_error_code() == CoreCode.MODEL_CAPABILITY_UNSUPPORTED
        assert not_found.to_error_report().caller_facing_message is True
