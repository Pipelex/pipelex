import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain, StepKind

from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.exceptions import InferenceErrorCategory, ModelNotFoundError, find_inference_error_category_in_chain
from pipelex.cogt.extract.extract_setting import ExtractSetting
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoices, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import PipelexProblem, ProblemView
from pipelex.system.runtime import ProblemReaction


def _make_deck() -> ModelDeck:
    """A deck serving one model, whose own entries name several models it does not serve."""
    served_model = InferenceModelSpec(
        backend_name="test_backend",
        name="served-model",
        sdk="test_sdk",
        model_type=ModelType.LLM,
        model_id="test_model_served",
        costs={CostCategory.INPUT: 0.001, CostCategory.OUTPUT: 0.002},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=1000,
        max_prompt_images=None,
    )
    return ModelDeck(
        inference_models=ModelSpecIndex.make_from_specs(model_specs=[served_model]),
        llm_default_temperature=0.7,
        llm_aliases={"deck-alias": "deck-alias-target", "served-alias": "served-model"},
        llm_waterfalls={"deck-waterfall": ["deck-waterfall-member", "served-model"]},
        llm_presets={"deck-preset": LLMSetting(model="deck-preset-model", temperature=0.3)},
        llm_choice_defaults=LLMSettingChoicesDefaults(
            default_temperature=0.7,
            for_text=LLMSetting(model="deck-default-text", temperature=0.7),
            for_object="$deck-preset",
        ),
        # A setting table is not parsed when the deck loads, so it can hold a value no reference parses from.
        llm_choice_overrides=LLMSettingChoices(
            for_text=LLMSetting(model="@", temperature=0.1),
            for_object=LLMSetting(model="deck-override-object", temperature=0.1),
        ),
        extract_aliases={},
        extract_waterfalls={},
        extract_presets={"deck-extract-preset": ExtractSetting(model="deck-extract-preset-model")},
        extract_choice_default="$deck-extract-preset",
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_aliases={},
        img_gen_waterfalls={},
        img_gen_presets={},
        # A handle spelled with its prefix reaches the lookup by its bare name.
        img_gen_choice_default="handle:deck-img-gen-default",
        search_aliases={},
        search_waterfalls={},
        search_presets={},
        # A plain reference to a model the deck serves as another type.
        search_choice_default="served-model",
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=True, missing_presets_reaction=ProblemReaction.NONE),
    )


def _raise_not_found(*, model_handle: str, model_type: ModelType) -> ModelNotFoundError:
    with pytest.raises(ModelNotFoundError) as exc_info:
        _make_deck().get_required_inference_model(model_handle, model_type=model_type)
    return exc_info.value


class TestModelDeckUnknownReference:
    @pytest.mark.parametrize(
        ("_topic", "model_handle", "model_type", "expected_suggestions"),
        [
            # A handle near one the deck serves as that type is offered it.
            ("handle", "method-only-model", ModelType.LLM, ["served-model"]),
            ("alias", "@method-only-alias", ModelType.LLM, []),
            ("waterfall", "~method-only-waterfall", ModelType.LLM, []),
            ("preset_used_as_a_model", "$deck-preset", ModelType.LLM, []),
            ("extract_handle", "method-only-extractor", ModelType.TEXT_EXTRACTOR, []),
            ("search_handle", "method-only-search", ModelType.SEARCH, []),
            # An LLM preset names it, but no image-generation entry does.
            ("img_gen_handle", "deck-preset-model", ModelType.IMG_GEN, []),
            # The deck serves it, but as an LLM, which an image-generation lookup refuses.
            ("served_handle_of_another_type", "served-model", ModelType.IMG_GEN, []),
        ],
    )
    def test_a_reference_only_the_method_names_is_the_callers_fault(
        self,
        _topic: str,
        model_handle: str,
        model_type: ModelType,
        expected_suggestions: list[str],
    ) -> None:
        """A reference the deck neither defines nor names came from the method: `model.unknown`, in the method's domain."""
        error = _raise_not_found(model_handle=model_handle, model_type=model_type)
        caller = error.to_problem(view=ProblemView.CALLER)

        assert caller.code == CoreCode.MODEL_UNKNOWN
        assert caller.domain == ProblemDomain.METHOD
        assert error_code_spec(CoreCode.MODEL_UNKNOWN).status == 422
        # The category still says the setup is wrong for the call; the domain says whose it is.
        assert find_inference_error_category_in_chain(error) == InferenceErrorCategory.CONFIGURATION
        # The caller reads the reference as the method wrote it and the type its lookup asked for, and nothing of the
        # deck: not even the type the deck serves a model of another type as.
        assert caller.params is not None
        assert caller.params.as_wire() == {"model": model_handle, "model_type": model_type, "suggestions": expected_suggestions}
        assert caller.detail == f"The method names the {model_type} model '{model_handle}', which no catalog knows."
        assert caller.next_step.kind == StepKind.CHANGE_MODEL
        assert caller.diagnostics is None
        operator = error.to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "ModelNotFoundError"
        assert operator.diagnostics.message == f"Model handle '{model_handle}' was not found in the model deck."

    @pytest.mark.parametrize(
        ("_topic", "model_handle", "model_type"),
        [
            ("preset_model", "deck-preset-model", ModelType.LLM),
            ("alias_target", "deck-alias-target", ModelType.LLM),
            ("defined_alias", "@deck-alias", ModelType.LLM),
            ("waterfall_member", "deck-waterfall-member", ModelType.LLM),
            ("default_setting", "deck-default-text", ModelType.LLM),
            ("override_setting", "deck-override-object", ModelType.LLM),
            ("unparsable_setting_model", "@", ModelType.LLM),
            ("plain_reference_default", "deck-img-gen-default", ModelType.IMG_GEN),
            ("plain_reference_default_of_another_type", "served-model", ModelType.SEARCH),
            ("extract_preset_model", "deck-extract-preset-model", ModelType.TEXT_EXTRACTOR),
        ],
    )
    def test_a_reference_the_deck_names_is_the_deployments_fault(self, _topic: str, model_handle: str, model_type: ModelType) -> None:
        """A reference the deck itself defines or names but does not serve is the operator's, its message the operator's alone."""
        error = _raise_not_found(model_handle=model_handle, model_type=model_type)
        caller = error.to_problem(view=ProblemView.CALLER)
        operator = error.to_problem(view=ProblemView.OPERATOR)

        assert caller.code == CoreCode.MODEL_UNAVAILABLE
        assert caller.domain == ProblemDomain.OPERATOR
        assert error_code_spec(CoreCode.MODEL_UNAVAILABLE).status == 501
        # The caller can only choose another model; serving this one is the operator's to configure.
        assert caller.next_step.kind == StepKind.CHANGE_MODEL
        assert operator.next_step.kind == StepKind.FIX_CONFIGURATION
        assert caller.diagnostics is None
        assert "was not found in the model deck" not in str(caller.to_wire())
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "ModelNotFoundError"
        assert operator.diagnostics.message == f"Model handle '{model_handle}' was not found in the model deck."
        assert error.advised_action() is None

    def test_the_classification_rides_the_worker_to_runner_hop(self) -> None:
        """On a hosted run the lookup fails on a worker: the problem is built there and read back on the runner."""
        packed = _raise_not_found(model_handle="method-only-model", model_type=ModelType.LLM).to_problem(view=ProblemView.CALLER).to_wire()
        recovered = PipelexProblem.model_validate(packed)

        assert recovered.code == CoreCode.MODEL_UNKNOWN
        assert error_code_spec(CoreCode.MODEL_UNKNOWN).status == 422
        assert recovered.detail == "The method names the llm model 'method-only-model', which no catalog knows."
        assert recovered.next_step.kind == StepKind.CHANGE_MODEL
        assert recovered.to_wire() == packed
