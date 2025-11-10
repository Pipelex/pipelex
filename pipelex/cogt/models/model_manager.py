from typing_extensions import override

from pipelex.cogt.exceptions import ModelManagerError
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_routing.routing_models import BackendMatchingMethod
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.model_routing.routing_profile_loader import load_active_routing_profile
from pipelex.cogt.models.model_deck import ModelDeck, ModelDeckBlueprint
from pipelex.cogt.models.model_deck_loader import load_model_deck_blueprint
from pipelex.cogt.models.model_manager_abstract import ModelManagerAbstract
from pipelex.config import ConfigPaths, get_config
from pipelex.tools.misc.file_utils import find_files_in_dir
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


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

    @classmethod
    def get_model_deck_paths(cls, deck_dir_path: str) -> list[str]:
        """Get all Model deck TOML file paths sorted alphabetically."""
        model_deck_paths = [
            str(path)
            for path in find_files_in_dir(
                dir_path=deck_dir_path,
                pattern="*.toml",
                is_recursive=True,
            )
        ]
        model_deck_paths.sort()
        return model_deck_paths

    @override
    def teardown(self) -> None:
        self.model_deck = None
        self.inference_backend_library.reset()
        self._routing_profile = None

    @override
    def setup(self, secrets_provider: SecretsProviderAbstract) -> None:
        self.inference_backend_library.load(
            secrets_provider=secrets_provider,
            backends_library_path=ConfigPaths.BACKENDS_FILE_PATH,
            backends_dir_path=ConfigPaths.BACKENDS_DIR_PATH,
        )
        enabled_backends = self.inference_backend_library.all_enabled_backends()
        self._routing_profile = load_active_routing_profile(
            routing_profile_library_path=ConfigPaths.ROUTING_PROFILES_FILE_PATH,
            enabled_backends=enabled_backends,
        )
        model_deck_paths = ModelManager.get_model_deck_paths(deck_dir_path=ConfigPaths.MODEL_DECKS_DIR_PATH)
        deck_blueprint = load_model_deck_blueprint(model_deck_paths=model_deck_paths)
        self.model_deck = self.build_deck(enabled_backends=enabled_backends, model_deck_blueprint=deck_blueprint)

    @override
    def validate_model_deck(self):
        self.get_model_deck().validate_registered_models()

    @property
    def routing_profile(self) -> RoutingProfile:
        if self._routing_profile is None:
            msg = "No active routing profile loaded"
            raise RuntimeError(msg)
        return self._routing_profile

    def build_deck(self, enabled_backends: list[str], model_deck_blueprint: ModelDeckBlueprint) -> ModelDeck:
        all_models_and_possible_backends = self.inference_backend_library.get_all_models_and_possible_backends()
        inference_models: dict[str, InferenceModelSpec] = {}

        for model_name, available_backends in all_models_and_possible_backends.items():
            backend_match_for_model = self.routing_profile.get_backend_match_for_model(
                enabled_backends=enabled_backends,
                model_name=model_name,
            )
            if backend_match_for_model is None:
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
                        # We can skip it because it was only a pattern match
                        continue
                    case BackendMatchingMethod.DEFAULT:
                        # We could not find the model spec, but it was a default match,
                        # so we can look for it in the other available backends
                        # Use fallback_order if specified, then try remaining enabled backends
                        if backend_match_for_model.fallback_order:
                            # Try fallback_order first, then any enabled backends not in fallback_order
                            backends_to_try = backend_match_for_model.fallback_order + [
                                b for b in enabled_backends if b not in backend_match_for_model.fallback_order
                            ]
                        else:
                            # No fallback_order specified, use all available_backends
                            backends_to_try = available_backends

                        for available_backend in backends_to_try:
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
                            # Model not available in any of the searched backends - skip it
                            # Not all models need to be available in the configured backends
                            continue
            inference_models[model_name] = model_spec

        return ModelDeck(
            inference_models=inference_models,
            aliases=model_deck_blueprint.aliases,
            waterfalls=model_deck_blueprint.waterfalls,
            llm_presets=model_deck_blueprint.llm.presets,
            llm_choice_defaults=model_deck_blueprint.llm.choice_defaults,
            llm_choice_overrides=model_deck_blueprint.llm.choice_overrides,
            extract_presets=model_deck_blueprint.extract.presets,
            extract_choice_default=model_deck_blueprint.extract.choice_default,
            img_gen_presets=model_deck_blueprint.img_gen.presets,
            img_gen_choice_default=model_deck_blueprint.img_gen.choice_default,
            model_deck_config=get_config().cogt.model_deck_config,
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
