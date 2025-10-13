from typing import Any

from pydantic import ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ModelDeckNotFoundError, ModelDeckValidationError, ModelManagerError
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_routing.routing_models import BackendMatchingMethod
from pipelex.cogt.model_routing.routing_profile_library import RoutingProfileLibrary
from pipelex.cogt.models.model_deck import ModelDeck, ModelDeckBlueprint
from pipelex.cogt.models.model_manager_abstract import ModelManagerAbstract
from pipelex.config import get_config
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import load_toml_from_path


class ModelManager(ModelManagerAbstract):
    def __init__(self) -> None:
        self.routing_profile_library = RoutingProfileLibrary.make_empty()
        self.inference_backend_library = InferenceBackendLibrary.make_empty()
        self.model_deck: ModelDeck | None = None

    @override
    def get_model_deck(self) -> ModelDeck:
        if self.model_deck is None:
            msg = "Model deck is not initialized"
            raise RuntimeError(msg)
        return self.model_deck

    @override
    def teardown(self) -> None:
        self.routing_profile_library.reset()
        self.inference_backend_library.reset()

    @override
    def setup(self) -> None:
        self.routing_profile_library.load()
        self.inference_backend_library.load()
        deck_blueprint = self.load_deck_blueprint()
        self.model_deck = self.build_deck(model_deck_blueprint=deck_blueprint)

    @classmethod
    def load_deck_blueprint(cls) -> ModelDeckBlueprint:
        deck_paths = get_config().cogt.inference_config.get_model_deck_paths()
        full_deck_dict: dict[str, Any] = {}
        if not deck_paths:
            msg = "No Model deck paths found. Please run `pipelex init config` to create the set up the base deck."
            raise ModelDeckNotFoundError(msg)

        for deck_path in deck_paths:
            try:
                deck_dict = load_toml_from_path(path=deck_path)
            except FileNotFoundError as not_found_exc:
                msg = f"Could not find Model Deck file at '{deck_path}': {not_found_exc}"
                raise ModelDeckNotFoundError(msg) from not_found_exc
            deep_update(full_deck_dict, deck_dict)

        try:
            return ModelDeckBlueprint.model_validate(full_deck_dict)
        except ValidationError as exc:
            msg = f"Invalid Model Deck configuration in {deck_paths}: {exc}"
            raise ModelDeckValidationError(msg) from exc

    def build_deck(self, model_deck_blueprint: ModelDeckBlueprint) -> ModelDeck:
        all_models_and_possible_backends = self.inference_backend_library.get_all_models_and_possible_backends()
        inference_models: dict[str, InferenceModelSpec] = {}

        for model_name, available_backends in all_models_and_possible_backends.items():
            backend_match_for_model = self.routing_profile_library.get_backend_match_for_model_from_active_routing_profile(
                model_name=model_name,
            )
            if backend_match_for_model is None:
                log.verbose(f"No backend match found for model '{model_name}'")
                continue
            matched_backend_name = backend_match_for_model.backend_name
            backend = self.inference_backend_library.get_inference_backend(backend_name=matched_backend_name)
            if backend is None:
                msg = f"Backend '{matched_backend_name}', requested for model '{model_name}', could not be found"
                raise ModelManagerError(msg)
            model_spec = backend.get_model_spec(model_name)
            if model_spec is None:
                # Not finding the model spec can be an error or not according to the matching method
                match backend_match_for_model.matching_method:
                    case BackendMatchingMethod.EXACT_MATCH:
                        msg = (
                            f"Model spec '{model_name}' not found in backend '{matched_backend_name}' "
                            f"which was matched exactly in routing profile '{backend_match_for_model.routing_profile_name}'"
                        )
                        raise ModelManagerError(msg)
                    case BackendMatchingMethod.PATTERN_MATCH:
                        log.verbose(
                            f"Model spec '{model_name}' not found in backend '{matched_backend_name}' but it's OK because "
                            f"it was only matched by pattern in routing profile '{backend_match_for_model.routing_profile_name}'",
                        )
                        # We can skip it because it was only a pattern match
                        continue
                    case BackendMatchingMethod.DEFAULT:
                        # We could not find the model spec, but it was a default match,
                        # so we can look for it in the other available backends
                        # TODO: enable to set the order or priority of the available backends
                        for available_backend in available_backends:
                            if available_backend == matched_backend_name:
                                # we've already checked the matched_backend_name and it didn't have the model spec, that's why we're here
                                continue
                            backend = self.inference_backend_library.get_inference_backend(backend_name=available_backend)
                            if backend is None:
                                msg = f"Backend '{available_backend}' not found for model '{model_name}'"
                                raise ModelManagerError(msg)
                            model_spec = backend.get_model_spec(model_name)
                            if model_spec is not None:
                                break
                        if model_spec is None:
                            msg = (
                                f"Model spec '{model_name}' not found in any of the available backends '{available_backends}' "
                                f"which was set as default in routing profile '{backend_match_for_model.routing_profile_name}'"
                            )
                            raise ModelManagerError(msg)
            inference_models[model_name] = model_spec

        return ModelDeck(
            inference_models=inference_models,
            aliases=model_deck_blueprint.aliases,
            llm_presets=model_deck_blueprint.llm.presets,
            llm_choice_defaults=model_deck_blueprint.llm.choice_defaults,
            llm_choice_overrides=model_deck_blueprint.llm.choice_overrides,
            extract_presets=model_deck_blueprint.extract.presets,
            extract_choice_default=model_deck_blueprint.extract.choice_default,
            img_gen_presets=model_deck_blueprint.img_gen.presets,
            img_gen_choice_default=model_deck_blueprint.img_gen.choice_default,
        )

    @override
    def get_inference_model(self, model_handle: str) -> InferenceModelSpec:
        if self.model_deck is None:
            msg = "Model deck is not initialized"
            raise RuntimeError(msg)
        return self.model_deck.get_required_inference_model(model_handle=model_handle)

    @override
    def get_required_inference_backend(self, backend_name: str) -> InferenceBackend:
        backend = self.inference_backend_library.get_inference_backend(backend_name)
        if backend is None:
            msg = f"Inference backend '{backend_name}' not found"
            raise ModelManagerError(msg)
        return backend
