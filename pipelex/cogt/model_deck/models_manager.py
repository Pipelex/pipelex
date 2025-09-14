from typing import Dict, List, Optional

from typing_extensions import override

from pipelex import log, pretty_print
from pipelex.cogt.exceptions import ModelsManagerError
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_deck.deck_manager import DeckManager
from pipelex.cogt.model_deck.llm_deck import LLMDeck, LLMDeckBlueprint
from pipelex.cogt.model_deck.models_manager_abstract import ModelsManagerAbstract
from pipelex.cogt.model_routing.routing_models import BackendMatchingMethod
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
        pretty_print(self.llm_deck, title="LLM Deck")

    def build_deck(self, llm_deck_blueprint: LLMDeckBlueprint) -> LLMDeck:
        all_models_and_possible_backends = self.inference_backend_library.get_all_models_and_possible_backends()
        llm_handles: Dict[str, InferenceModelSpec] = {}

        pretty_print(all_models_and_possible_backends, title="all_models_and_possible_backends")

        backend_names = self.inference_backend_library.list_backend_names()
        pretty_print(backend_names, title="Enabled backends")

        for model_name, available_backends in all_models_and_possible_backends.items():
            backend_match_for_model = self.routing_profile_library.get_backend_match_for_model_from_active_routing_profile(
                model_name=model_name,
            )
            if backend_match_for_model is None:
                raise ModelsManagerError(f"No backend match found for model '{model_name}'")
            matched_backend_name = backend_match_for_model.backend_name
            backend = self.inference_backend_library.get_inference_backend(backend_name=matched_backend_name)
            if backend is None:
                raise ModelsManagerError(f"Backend '{matched_backend_name}', requested for model '{model_name}', could not be found")
            model_spec = backend.get_model_spec(model_name)
            if model_spec is None:
                # Not finding the model spec can be an error or not according to the matching method
                match backend_match_for_model.matching_method:
                    case BackendMatchingMethod.EXACT_MATCH:
                        raise ModelsManagerError(
                            f"Model spec '{model_name}' not found in backend '{matched_backend_name}' "
                            f"which was matched exactly in routing profile '{backend_match_for_model.routing_profile_name}'"
                        )
                    case BackendMatchingMethod.PATTERN_MATCH:
                        log.verbose(
                            f"Model spec '{model_name}' not found in backend '{matched_backend_name}' but it's OK because "
                            f"it was only matched by pattern in routing profile '{backend_match_for_model.routing_profile_name}'"
                        )
                        # We can skip it because it was only a pattern match
                        continue
                    case BackendMatchingMethod.DEFAULT:
                        # We could not find the model spec, but it was a default match,
                        # so we can look for it in the other available backends
                        # TODO: enable to set the order or priority of the available backends
                        for available_backend in available_backends:
                            if available_backend == matched_backend_name:
                                continue
                            backend = self.inference_backend_library.get_inference_backend(backend_name=available_backend)
                            if backend is None:
                                raise ModelsManagerError(f"Backend '{available_backend}' not found for model '{model_name}'")
                            model_spec = backend.get_model_spec(model_name)
                            if model_spec is not None:
                                break
                        if model_spec is None:
                            raise ModelsManagerError(
                                f"Model spec '{model_name}' not found in any of the available backends '{available_backends}' "
                                f"which was set as default in routing profile '{backend_match_for_model.routing_profile_name}'"
                            )
            llm_handles[model_name] = model_spec

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
    def get_required_inference_backend(self, backend_name: str) -> InferenceBackend:
        backend = self.inference_backend_library.get_inference_backend(backend_name)
        if backend is None:
            raise ModelsManagerError(f"Inference backend '{backend_name}' not found")
        return backend
