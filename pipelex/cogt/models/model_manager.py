from typing import Any

from pydantic import ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ModelDeckNotFoundError, ModelDeckValidationError, ModelManagerError
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_routing.routing_models import BackendMatchingMethod
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.model_routing.routing_profile_factory import RoutingProfileFactory, RoutingProfileLibraryBlueprint
from pipelex.cogt.models.model_deck import ModelDeck, ModelDeckBlueprint
from pipelex.cogt.models.model_manager_abstract import ModelManagerAbstract
from pipelex.config import get_config
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class ModelManager(ModelManagerAbstract):
    def __init__(self) -> None:
        self._routing_profile: RoutingProfile | None = None
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
        self._routing_profile = None
        self.inference_backend_library.reset()

    @override
    def setup(self) -> None:
        self.inference_backend_library.load()
        enabled_backends = self.inference_backend_library.all_enabled_backends()
        self.load_routing_profile(enabled_backends=enabled_backends)
        deck_blueprint = self.load_deck_blueprint()
        self.model_deck = self.build_deck(enabled_backends=enabled_backends, model_deck_blueprint=deck_blueprint)

    @property
    def routing_profile(self) -> RoutingProfile:
        if self._routing_profile is None:
            msg = "No active routing profile loaded"
            raise RuntimeError(msg)
        return self._routing_profile

    def load_routing_profile(self, enabled_backends: list[str]) -> None:
        """Load the active routing profile from the routing profile library from TOML file."""
        routing_profile_library_path = get_config().cogt.inference_config.routing_profile_library_path

        # Load the routing profile library from TOML file
        try:
            catalog_dict = load_toml_from_path(path=routing_profile_library_path)
        except FileNotFoundError as not_found_exc:
            msg = f"Could not find routing profile library at '{routing_profile_library_path}': {not_found_exc}"
            raise ModelManagerError(msg) from not_found_exc

        # Validate the routing profile library configuration
        try:
            routing_profile_library_blueprint = RoutingProfileLibraryBlueprint.model_validate(catalog_dict)
        except ValidationError as exc:
            valiation_error_msg = format_pydantic_validation_error(exc)
            msg = f"Invalid routing profile library configuration in '{routing_profile_library_path}': {valiation_error_msg}"
            raise ModelManagerError(msg) from exc

        # Validate that the active profile exists
        profile_names = ", ".join(list(routing_profile_library_blueprint.profiles.keys()))
        active_profile_name = routing_profile_library_blueprint.active
        if active_profile_name not in profile_names:
            msg = f"Active profile '{active_profile_name}' not found in profile routing library. Available profiles: {profile_names}"
            raise ModelManagerError(msg)

        # Load all profiles
        active_profile_blueprint = routing_profile_library_blueprint.profiles[active_profile_name]
        active_profile = RoutingProfileFactory.make_routing_profile(
            name=active_profile_name,
            blueprint=active_profile_blueprint,
        )
        if active_profile.default and active_profile.default not in enabled_backends:
            msg = f"Default backend '{active_profile.default}' for routing profile '{active_profile_name}' is not enabled"
            # raise RoutingProfileLibraryError(msg)
            log.error(msg)
        seen_disabled_backends: set[str] = set()
        for backend_name in active_profile.routes.values():
            if backend_name not in enabled_backends and backend_name not in seen_disabled_backends:
                msg = f"Backend '{backend_name}' for profile '{active_profile_name}' is not enabled"
                # raise RoutingProfileLibraryError(msg)
                log.warning(msg)
                seen_disabled_backends.add(backend_name)
        self._routing_profile = active_profile

        log.debug(f"Loaded active routing profile: '{self._routing_profile}'")

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
            valiation_error_msg = format_pydantic_validation_error(exc)
            msg = f"Invalid Model Deck configuration in {deck_paths}: {valiation_error_msg}"
            raise ModelDeckValidationError(msg) from exc

    def build_deck(self, enabled_backends: list[str], model_deck_blueprint: ModelDeckBlueprint) -> ModelDeck:
        all_models_and_possible_backends = self.inference_backend_library.get_all_models_and_possible_backends()
        inference_models: dict[str, InferenceModelSpec] = {}

        for model_name, available_backends in all_models_and_possible_backends.items():
            backend_match_for_model = self.routing_profile.get_backend_match_for_model(
                enabled_backends=enabled_backends,
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
