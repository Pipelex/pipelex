import os
from typing import Any, Dict, Optional

from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ModelDeckNotFoundError, ModelsManagerError
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_routing.routing_models import BackendMatchingMethod
from pipelex.cogt.model_routing.routing_profile_library import RoutingProfileLibrary
from pipelex.cogt.models.model_deck import ModelDeck, ModelDeckBlueprint
from pipelex.cogt.models.model_manager_abstract import ModelManagerAbstract
from pipelex.config import get_config
from pipelex.exceptions import LibraryError
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import TOMLValidationError, load_toml_from_path, validate_toml_file


class ModelManager(ModelManagerAbstract):
    def __init__(self) -> None:
        self.routing_profile_library = RoutingProfileLibrary.make_empty()
        self.inference_backend_library = InferenceBackendLibrary.make_empty()
        self.llm_deck: Optional[ModelDeck] = None

    @override
    def get_llm_deck(self) -> ModelDeck:
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
        llm_deck_blueprint = self.load_deck_blueprint()
        self.llm_deck = self.build_deck(llm_deck_blueprint=llm_deck_blueprint)

    @classmethod
    def _validate_toml_files(cls) -> None:
        log.debug("LibraryManager deck TOML file formatting")

        # Validation of LLM deck paths
        llm_deck_paths = get_config().cogt.inference_config.get_llm_deck_paths()
        for llm_deck_path in llm_deck_paths:
            if os.path.exists(llm_deck_path):
                try:
                    validate_toml_file(llm_deck_path)
                except TOMLValidationError as exc:
                    log.error(f"TOML formatting issues in LLM deck file '{llm_deck_path}': {exc}")
                    raise LibraryError(f"TOML validation failed for LLM deck file '{llm_deck_path}': {exc}") from exc

    @classmethod
    def load_deck_blueprint(cls) -> ModelDeckBlueprint:
        llm_deck_paths = get_config().cogt.inference_config.get_llm_deck_paths()
        full_llm_deck_dict: Dict[str, Any] = {}
        if not llm_deck_paths:
            raise ModelDeckNotFoundError("No LLM deck paths found. Please run `pipelex init-libraries` to create it.")

        for llm_deck_path in llm_deck_paths:
            if not os.path.exists(llm_deck_path):
                raise ModelDeckNotFoundError(f"LLM deck path `{llm_deck_path}` not found. Please run `pipelex init-libraries` to create it.")
            try:
                llm_deck_dict = load_toml_from_path(path=llm_deck_path)
                log.debug(f"Loaded LLM deck from {llm_deck_path}")
                deep_update(full_llm_deck_dict, llm_deck_dict)
            except Exception as exc:
                log.error(f"Failed to load LLM deck file '{llm_deck_path}': {exc}")
                raise

        llm_deck_blueprint = ModelDeckBlueprint.model_validate(full_llm_deck_dict)
        return llm_deck_blueprint

    def build_deck(self, llm_deck_blueprint: ModelDeckBlueprint) -> ModelDeck:
        all_models_and_possible_backends = self.inference_backend_library.get_all_models_and_possible_backends()
        llm_handles: Dict[str, InferenceModelSpec] = {}

        for model_name, available_backends in all_models_and_possible_backends.items():
            backend_match_for_model = self.routing_profile_library.get_backend_match_for_model_from_active_routing_profile(
                model_name=model_name,
            )
            if backend_match_for_model is None:
                # raise ModelsManagerError(f"No backend match found for model '{model_name}'")
                log.verbose(f"No backend match found for model '{model_name}'")
                continue
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

        llm_deck = ModelDeck(
            inference_models=llm_handles,
            aliases=llm_deck_blueprint.aliases,
            llm_presets=llm_deck_blueprint.llm_presets,
            llm_choice_defaults=llm_deck_blueprint.llm_choice_defaults,
            llm_choice_overrides=llm_deck_blueprint.llm_choice_overrides,
        )
        return llm_deck

    @override
    def get_inference_model(self, llm_handle: str) -> InferenceModelSpec:
        if self.llm_deck is None:
            raise RuntimeError("LLM deck is not initialized")
        return self.llm_deck.get_required_inference_model(llm_handle=llm_handle)

    @override
    def get_required_inference_backend(self, backend_name: str) -> InferenceBackend:
        backend = self.inference_backend_library.get_inference_backend(backend_name)
        if backend is None:
            raise ModelsManagerError(f"Inference backend '{backend_name}' not found")
        return backend
