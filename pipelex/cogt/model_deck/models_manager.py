from typing import Dict, List, Optional

from typing_extensions import override

from pipelex import pretty_print
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_deck.deck_manager import DeckManager
from pipelex.cogt.model_deck.llm_deck import LLMDeck, LLMDeckBlueprint
from pipelex.cogt.model_deck.models_manager_abstract import ModelsManagerAbstract
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.model_routing.routing_profile_library import RoutingProfileLibrary


class ModelsManager(ModelsManagerAbstract):
    def __init__(self) -> None:
        self.routing_profile_library = RoutingProfileLibrary.make_empty()
        self.inference_backend_library = InferenceBackendLibrary.make_empty()
        self.llm_deck: Optional[LLMDeck] = None

    @override
    def get_llm_deck(self) -> LLMDeck:
        if self.llm_deck is None:
            raise RuntimeError("LLM deck is not initialized")
        return self.llm_deck

    @property
    def routing_profile(self) -> RoutingProfile:
        return self.routing_profile_library.get_required_active_routing_profile()

    @override
    def teardown(self) -> None:
        self.routing_profile_library.reset()
        self.inference_backend_library.reset()

    @override
    def setup(self) -> None:
        self.routing_profile_library.load()
        self.inference_backend_library.load()
        llm_deck_blueprint = DeckManager.load_deck_blueprint()
        self.llm_deck = self.build_deck(llm_deck_blueprint=llm_deck_blueprint)

    def list_all_model_names(self) -> List[str]:
        return self.inference_backend_library.list_all_model_names()

    def build_deck(self, llm_deck_blueprint: LLMDeckBlueprint) -> LLMDeck:
        all_model_names = self.list_all_model_names()
        llm_handles: Dict[str, InferenceModelSpec] = {}

        pretty_print(all_model_names, title="all_model_names")

        backend_names = self.inference_backend_library.list_backend_names()
        pretty_print(backend_names, title="Enabled backends")

        for model_name in all_model_names:
            backend_name = self.routing_profile.get_backend_for_model(model_name)
            backend = self.inference_backend_library.get_required_backend(backend_name)
            llm_handles[model_name] = backend.get_required_model_spec(model_name)

        llm_deck = LLMDeck(
            llm_handles=llm_handles,
            llm_presets=llm_deck_blueprint.llm_presets,
            llm_choice_defaults=llm_deck_blueprint.llm_choice_defaults,
            llm_choice_overrides=llm_deck_blueprint.llm_choice_overrides,
        )
        return llm_deck

    @override
    def get_all_inference_models(self) -> Dict[str, InferenceModelSpec]:
        if self.llm_deck is None:
            raise RuntimeError("LLM deck is not initialized")
        return self.llm_deck.llm_handles

    @override
    def get_inference_model(self, llm_handle: str) -> InferenceModelSpec:
        if self.llm_deck is None:
            raise RuntimeError("LLM deck is not initialized")
        return self.llm_deck.get_inference_model(llm_handle=llm_handle)

    @override
    def get_inference_backend(self, backend_name: str) -> InferenceBackend:
        return self.inference_backend_library.get_required_backend(backend_name)
