import pytest
from mthds.protocol.problem.registry import CoreCode, ModelUnavailableReason, ProblemDomain

from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.exceptions import ModelNotFoundError
from pipelex.cogt.extract.extract_setting import ExtractSetting
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.errors.problem import ProblemView
from pipelex.system.runtime import ProblemReaction
from tests.unit.pipelex.cogt.models.test_data import UnservedReferenceTestData as Data


def _make_deck() -> ModelDeck:
    """A deck serving one model, whose catalogs also declare a model on a backend this deployment does not enable."""
    served_model = InferenceModelSpec(
        backend_name="test_backend",
        name=Data.SERVED_HANDLE,
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
        cataloged_handles={Data.SERVED_HANDLE: [ModelType.LLM], Data.CATALOGED_HANDLE: [ModelType.LLM]},
        llm_default_temperature=0.7,
        llm_aliases={},
        llm_waterfalls={},
        llm_presets={},
        llm_choice_defaults=LLMSettingChoicesDefaults(
            default_temperature=0.7,
            for_text=LLMSetting(model=Data.SERVED_HANDLE, temperature=0.7),
            for_object=LLMSetting(model=Data.SERVED_HANDLE, temperature=0.7),
        ),
        extract_aliases={},
        extract_waterfalls={},
        extract_presets={"deck-extract-preset": ExtractSetting(model=Data.SERVED_HANDLE)},
        extract_choice_default="$deck-extract-preset",
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_aliases={},
        img_gen_waterfalls={},
        img_gen_presets={},
        img_gen_choice_default=Data.SERVED_HANDLE,
        search_aliases={},
        search_waterfalls={},
        search_presets={},
        search_choice_default=Data.SERVED_HANDLE,
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=True, missing_presets_reaction=ProblemReaction.NONE),
    )


def _raise_not_found(*, model_handle: str, model_type: ModelType) -> ModelNotFoundError:
    with pytest.raises(ModelNotFoundError) as exc_info:
        _make_deck().get_required_inference_model(model_handle, model_type=model_type)
    return exc_info.value


class TestModelDeckUnservedReference:
    def test_a_model_a_catalog_knows_but_no_enabled_backend_serves_is_unavailable(self) -> None:
        """The model exists on a backend this deployment switched off: the deployment's `model.unavailable`, never `model.unknown`."""
        deck = _make_deck()
        assert deck.is_cataloged_but_unserved(name=Data.CATALOGED_HANDLE, model_type=ModelType.LLM)
        assert not deck.is_cataloged_but_unserved(name=Data.SERVED_HANDLE, model_type=ModelType.LLM)
        assert not deck.is_cataloged_but_unserved(name=Data.CATALOGED_HANDLE, model_type=ModelType.IMG_GEN)

        caller = _raise_not_found(model_handle=Data.CATALOGED_HANDLE, model_type=ModelType.LLM).to_problem(view=ProblemView.CALLER)

        assert caller.code == CoreCode.MODEL_UNAVAILABLE
        assert caller.domain == ProblemDomain.OPERATOR
        assert caller.params is not None
        assert caller.params.as_wire() == {"model": Data.CATALOGED_HANDLE, "model_type": "llm", "reason": ModelUnavailableReason.NOT_SERVED}

    @pytest.mark.parametrize(
        ("_topic", "model_handle", "expected_suggestions"),
        [
            ("near_a_served_handle", Data.NEAR_HANDLE, [Data.SERVED_HANDLE]),
            ("near_no_served_handle", Data.FAR_HANDLE, []),
        ],
    )
    def test_a_model_no_catalog_knows_offers_the_nearest_served_handles(
        self, _topic: str, model_handle: str, expected_suggestions: list[str]
    ) -> None:
        """A name no catalog knows is the method's `model.unknown`, which always offers the nearest handles, an empty list when none is near."""
        caller = _raise_not_found(model_handle=model_handle, model_type=ModelType.LLM).to_problem(view=ProblemView.CALLER)

        assert caller.code == CoreCode.MODEL_UNKNOWN
        assert caller.params is not None
        assert caller.params.as_wire() == {"model": model_handle, "model_type": "llm", "suggestions": expected_suggestions}
