import pytest

from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode, ErrorReport
from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.exceptions import ModelNotFoundError
from pipelex.cogt.extract.extract_setting import ExtractSetting
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoices, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.usage.cost_category import CostCategory
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
        inference_models={"served-model": served_model},
        llm_default_temperature=0.7,
        llm_aliases={"deck-alias": "deck-alias-target", "served-alias": "served-model"},
        llm_waterfalls={"deck-waterfall": ["deck-waterfall-member", "served-model"]},
        llm_presets={"deck-preset": LLMSetting(model="deck-preset-model", temperature=0.3)},
        llm_choice_defaults=LLMSettingChoicesDefaults(
            default_temperature=0.7,
            for_text=LLMSetting(model="deck-default-text", temperature=0.7),
            for_object="$deck-preset",
        ),
        llm_choice_overrides=LLMSettingChoices(for_text=None, for_object=LLMSetting(model="deck-override-object", temperature=0.1)),
        extract_aliases={},
        extract_waterfalls={},
        extract_presets={"deck-extract-preset": ExtractSetting(model="deck-extract-preset-model")},
        extract_choice_default="$deck-extract-preset",
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_aliases={},
        img_gen_waterfalls={},
        img_gen_presets={},
        img_gen_choice_default="deck-img-gen-default",
        search_aliases={},
        search_waterfalls={},
        search_presets={},
        search_choice_default="deck-search-default",
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=True, missing_presets_reaction=ProblemReaction.NONE),
    )


def _raise_not_found(*, model_handle: str, model_type: ModelType) -> ModelNotFoundError:
    with pytest.raises(ModelNotFoundError) as exc_info:
        _make_deck().get_required_inference_model(model_handle, model_type=model_type)
    return exc_info.value


class TestModelDeckUnknownReference:
    @pytest.mark.parametrize(
        ("_topic", "model_handle", "model_type"),
        [
            ("handle", "method-only-model", ModelType.LLM),
            ("alias", "@method-only-alias", ModelType.LLM),
            ("waterfall", "~method-only-waterfall", ModelType.LLM),
            ("preset_used_as_a_model", "$deck-preset", ModelType.LLM),
            ("extract_handle", "method-only-extractor", ModelType.TEXT_EXTRACTOR),
            # An LLM preset names it, but no image-generation entry does.
            ("img_gen_handle", "deck-preset-model", ModelType.IMG_GEN),
        ],
    )
    def test_a_reference_only_the_method_names_is_the_callers_fault(self, _topic: str, model_handle: str, model_type: ModelType) -> None:
        """A reference the deck neither defines nor names came from the method: input domain, and caller-facing."""
        report = _raise_not_found(model_handle=model_handle, model_type=model_type).to_error_report()

        assert report.error_type == "ModelNotFoundError"
        assert report.message == f"Model handle '{model_handle}' was not found in the model deck."
        assert report.error_domain == "input"
        assert report.caller_facing_message is True
        assert report.http_status == 422
        # The category still says the setup is wrong for the call; the domain says whose it is.
        assert report.error_category == "configuration"
        assert report.to_dict(disclosure_mode=DisclosureMode.STRICT)["message"] == report.message

    @pytest.mark.parametrize(
        ("_topic", "model_handle", "model_type"),
        [
            ("preset_model", "deck-preset-model", ModelType.LLM),
            ("alias_target", "deck-alias-target", ModelType.LLM),
            ("defined_alias", "@deck-alias", ModelType.LLM),
            ("waterfall_member", "deck-waterfall-member", ModelType.LLM),
            ("default_setting", "deck-default-text", ModelType.LLM),
            ("override_setting", "deck-override-object", ModelType.LLM),
            ("extract_preset_model", "deck-extract-preset-model", ModelType.TEXT_EXTRACTOR),
        ],
    )
    def test_a_reference_the_deck_names_is_the_deployments_fault(self, _topic: str, model_handle: str, model_type: ModelType) -> None:
        """A reference the deck itself defines or names but does not serve stays config-domain and redacted."""
        report = _raise_not_found(model_handle=model_handle, model_type=model_type).to_error_report()

        assert report.error_type == "ModelNotFoundError"
        assert report.error_domain == "config"
        assert report.caller_facing_message is False
        assert report.http_status == 500
        assert report.to_dict(disclosure_mode=DisclosureMode.STRICT)["message"] == INTERNAL_ERROR_PLACEHOLDER

    def test_the_classification_rides_the_worker_to_runner_hop(self) -> None:
        """On a hosted run the lookup fails on a worker: the report is packed VERBOSE there and projected STRICT on the runner."""
        packed = _raise_not_found(model_handle="method-only-model", model_type=ModelType.LLM).to_error_report().to_dict()
        recovered = ErrorReport.from_dict(packed)

        assert recovered.caller_facing_message is True
        payload = recovered.to_problem_document(disclosure_mode=DisclosureMode.STRICT)
        assert payload["status"] == 422
        assert payload["detail"] == "Model handle 'method-only-model' was not found in the model deck."
