"""Shared builders for the per-pair deck tests: in-memory backends, a deck blueprint naming the twin, and a deck built from them."""

from pipelex.cogt.extract.extract_setting import ExtractModelChoice
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.models.model_deck import (
    ExtractDeckBlueprint,
    ImgGenDeckBlueprint,
    JudgmentDeckBlueprint,
    LLMDeckBlueprint,
    ModelDeckBlueprint,
    SearchDeckBlueprint,
)
from pipelex.cogt.models.model_manager import ModelManager

TWIN_HANDLE = "gpt-6-luna"
GET_MODEL_DECK_TARGET = "pipelex.cogt.models.model_deck_check.get_model_deck"


def make_spec(*, name: str, model_type: ModelType, backend_name: str) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name=backend_name,
        name=name,
        sdk=f"{backend_name}_sdk",
        model_type=model_type,
        model_id=name,
        costs={},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )


def make_backend(name: str, *served: tuple[str, ModelType]) -> InferenceBackend:
    return InferenceBackend(
        name=name,
        model_specs=ModelSpecIndex.make_from_specs(
            model_specs=[make_spec(name=handle, model_type=model_type, backend_name=name) for handle, model_type in served]
        ),
    )


def make_deck_blueprint(*, extract_choice_default: ExtractModelChoice = "extractor") -> ModelDeckBlueprint:
    return ModelDeckBlueprint(
        llm=LLMDeckBlueprint(
            choice_defaults=LLMSettingChoicesDefaults(
                default_temperature=0.7,
                for_text=LLMSetting(model=TWIN_HANDLE, temperature=0.7),
                for_object=LLMSetting(model=TWIN_HANDLE, temperature=0.1),
            ),
        ),
        extract=ExtractDeckBlueprint(choice_default=extract_choice_default),
        img_gen=ImgGenDeckBlueprint(default_quality=Quality.MEDIUM, choice_default="painter"),
        search=SearchDeckBlueprint(choice_default="searcher"),
        judgment=JudgmentDeckBlueprint(aliases={"fast": "verdict"}),
    )


def build_deck_manager(*backends: InferenceBackend, routing_profile: RoutingProfile, enabled_backends: list[str] | None = None) -> ModelManager:
    """A manager whose deck is built over these backends, every one of them enabled unless `enabled_backends` names a subset."""
    manager = ModelManager()
    manager.inference_backend_library.root = {backend.name: backend for backend in backends}
    manager._routing_profile = routing_profile  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
    manager.model_deck = manager.build_deck(
        model_deck_blueprint=make_deck_blueprint(),
        enabled_backends=enabled_backends if enabled_backends is not None else [backend.name for backend in backends],
    )
    return manager
