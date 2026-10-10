from collections.abc import Sequence
from pathlib import Path
from typing import Any

from typing_extensions import override

from pipelex import log
from pipelex.cogt.doc_gen.doc_gen_format import parse_doc_gen_choice_key
from pipelex.cogt.exceptions import (
    InferenceBackendCredentialsError,
    InferenceBackendCredentialsErrorType,
    ModelManagerError,
    PluginModelDeclarationError,
)
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.cogt.model_backends.backend import InferenceBackend, PipelexBackend
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.cogt.model_backends.credential_resolution import CredentialResolution
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.model_routing.routing_models import BackendMatchForModel, BackendMatchingMethod
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.model_routing.routing_profile_loader import load_active_routing_profile
from pipelex.cogt.models.model_deck import ModelDeck, ModelDeckBlueprint
from pipelex.cogt.models.model_deck_loader import load_model_deck_blueprint
from pipelex.cogt.models.model_manager_abstract import ModelManagerAbstract
from pipelex.config import get_config
from pipelex.migration.exceptions import FormerReleaseConfigError
from pipelex.migration.former_release import describe_former_release_boot_refusal, former_release_boot_blockers
from pipelex.plugins.plugin_model_declarations import PluginModelDeclarations
from pipelex.system.configuration.config_loader import config_manager
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
                dir_path=Path(deck_dir_path),
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
    def setup(
        self,
        *,
        secrets_provider: SecretsProviderAbstract,
        plugin_model_declarations: PluginModelDeclarations,
        needs_inference: bool = True,
        backends_library_paths: Sequence[Path] | None = None,
        backends_dir_path: str | None = None,
        routing_profile_library_paths: Sequence[Path] | None = None,
        deck_dir_path: str | None = None,
    ) -> None:
        # Override paths let the doctor scope --global properly; default None falls
        # back to layered config_manager paths for all other callers. The two documents are
        # sequences — the base file, then the personal override files — see
        # `ConfigLoader.backends_file_paths`.
        resolved_backends_dir_path = backends_dir_path or str(config_manager.backends_dir_path)
        resolved_backends_library_paths = backends_library_paths or config_manager.backends_file_paths()
        resolved_routing_profile_library_paths = routing_profile_library_paths or config_manager.routing_profiles_file_paths()
        # What a former release left for the Pipelex Gateway is refused here, by one error naming the
        # cleanup, ahead of the refusals below: the Gateway's unset key, its backend file declaring no model, or a
        # routing profile sending models to a backend that is not enabled — none of which says why, or what to run.
        if blockers := former_release_boot_blockers(
            backends_library_paths=resolved_backends_library_paths,
            routing_profile_library_paths=resolved_routing_profile_library_paths,
        ):
            msg = describe_former_release_boot_refusal(blockers=blockers)
            raise FormerReleaseConfigError(msg)
        self.inference_backend_library.load(
            secrets_provider=secrets_provider,
            backends_library_paths=resolved_backends_library_paths,
            backends_dir_path=resolved_backends_dir_path,
            # A keyless boot knows every enabled backend's models and resolves no credential; the boot
            # that needs inference resolves every one and refuses to start without it.
            credentials=CredentialResolution.REQUIRE if needs_inference else CredentialResolution.SKIP,
        )
        # The loader parks its stale-configuration warning rather than logging it, so that the
        # doctor's per-backend probe — which loads the whole library once per backend — does not
        # repeat one directory's warning a dozen times. This is the boot that owes the user the
        # single copy, and by here logging is configured.
        if (stale_warning := self.inference_backend_library.take_stale_configuration_warning()) is not None:
            stale_warning.emit()
        # The plugins' internal models join the internal backend before anything reads the library, so routing
        # and the deck see them exactly as they see a model `internal.toml` declares.
        has_internal_backend = self.inference_backend_library.merge_plugin_internal_models(
            plugin_model_declarations=plugin_model_declarations,
            backends_dir_path=resolved_backends_dir_path,
        )
        enabled_backends = self.inference_backend_library.all_enabled_backends()
        self._routing_profile = load_active_routing_profile(
            routing_profile_library_paths=resolved_routing_profile_library_paths,
            enabled_backends=enabled_backends,
        )
        model_deck_paths = ModelManager.get_model_deck_paths(deck_dir_path=deck_dir_path or str(config_manager.model_decks_dir_path))
        deck_blueprint = load_model_deck_blueprint(
            model_deck_paths=model_deck_paths,
            base_deck_dict=self._make_plugin_deck_base(
                plugin_model_declarations=plugin_model_declarations, has_internal_backend=has_internal_backend
            ),
        )
        self.model_deck = self.build_deck(enabled_backends=enabled_backends, model_deck_blueprint=deck_blueprint)

    @classmethod
    def _make_plugin_deck_base(cls, *, plugin_model_declarations: PluginModelDeclarations, has_internal_backend: bool) -> dict[str, Any]:
        """The model deck document the plugins' defaults make, for the deck files to be merged over.

        Left out entirely without an internal backend, as the plugins' models are: a default pointing at a model this
        boot does not serve would fail the deck's validation, and a plugin must not make a
        boot fail that would succeed without it. The kit's own internal models set the precedent: with the backend
        disabled their files' models are not loaded, and nothing a plugin adds changes that.

        Raises:
            PluginModelDeclarationError: a plugin declares a default for a format and source no step composes.
        """
        if not has_internal_backend:
            return {}
        for doc_gen_default in plugin_model_declarations.doc_gen_defaults:
            try:
                parse_doc_gen_choice_key(doc_gen_default.choice_key)
            except ValueError as exc:
                msg = f"Plugin '{doc_gen_default.plugin}' declares a default document engine that no step can use: {exc}"
                raise PluginModelDeclarationError(msg, plugin=doc_gen_default.plugin) from exc
        return plugin_model_declarations.make_deck_base()

    @override
    def validate_model_deck(self):
        self.get_model_deck().validate_registered_models()

    @property
    def routing_profile(self) -> RoutingProfile:
        if self._routing_profile is None:
            msg = "No active routing profile loaded"
            raise RuntimeError(msg)
        return self._routing_profile

    def build_deck(self, model_deck_blueprint: ModelDeckBlueprint, *, enabled_backends: list[str]) -> ModelDeck:
        """Build the deck over every pair of a handle and a model type some backend declares.

        A routing profile matches a handle's name, so the name is matched once, and the matched
        backend is then asked for the spec of each type the name is declared as. Each matching method
        keeps its meaning per pair: a pattern match skips a pair its backend lacks, a default match
        looks for it along the fallback order, and an exact match pins the name to its backend, so a
        type that backend does not serve is not served at all. A name the profile sends to no enabled
        backend is served by the internal backend, for each type that backend declares under it.

        Raises:
            ModelManagerError: A routed backend is not loaded, or a handle routed exactly to a backend
                that declares it under no model type at all.
        """
        inference_models = ModelSpecIndex.make_empty()

        for model_name, declared_model_types in self.inference_backend_library.get_declared_types_by_handle().items():
            backend_match_for_model = self.routing_profile.get_backend_match_for_model(
                enabled_backends=enabled_backends,
                model_name=model_name,
            )
            if backend_match_for_model is None:
                # The profile sends the name nowhere, as a profile routing only to providers does when none of
                # them is enabled. The internal backend's models need no provider, so they are served all the same:
                # only a route sending their name elsewhere, or disabling the internal backend, withholds them.
                for model_type in declared_model_types:
                    if model_spec := self._find_internal_model_spec(model_name=model_name, model_type=model_type, enabled_backends=enabled_backends):
                        inference_models.add(model_spec)
                continue
            matched_backend_name = backend_match_for_model.backend_name
            matched_backend = self.inference_backend_library.get_inference_backend(backend_name=matched_backend_name)
            if matched_backend is None:
                msg = f"Backend '{matched_backend_name}', requested for model '{model_name}', could not be found"
                raise ModelManagerError(msg)
            if backend_match_for_model.matching_method == BackendMatchingMethod.EXACT_MATCH and not matched_backend.model_specs.types_serving(
                handle=model_name
            ):
                msg = (
                    f"Model spec '{model_name}' not found in backend '{matched_backend_name}' "
                    f"which was matched exactly in routing profile '{backend_match_for_model.routing_profile_name}'"
                )
                raise ModelManagerError(msg)
            for model_type in declared_model_types:
                model_spec = self._find_routed_model_spec(
                    model_name=model_name,
                    model_type=model_type,
                    backend_match_for_model=backend_match_for_model,
                    matched_backend=matched_backend,
                    enabled_backends=enabled_backends,
                )
                if model_spec is not None:
                    inference_models.add(model_spec)

        return ModelDeck(
            inference_models=inference_models,
            # LLM
            llm_default_temperature=model_deck_blueprint.llm.choice_defaults.default_temperature,
            llm_aliases=model_deck_blueprint.llm.aliases,
            llm_waterfalls=model_deck_blueprint.llm.waterfalls,
            llm_presets=model_deck_blueprint.llm.presets,
            llm_choice_defaults=model_deck_blueprint.llm.choice_defaults,
            llm_choice_overrides=model_deck_blueprint.llm.choice_overrides,
            # Extract
            extract_aliases=model_deck_blueprint.extract.aliases,
            extract_waterfalls=model_deck_blueprint.extract.waterfalls,
            extract_presets=model_deck_blueprint.extract.presets,
            extract_choice_default=model_deck_blueprint.extract.choice_default,
            # ImgGen
            img_gen_default_quality=model_deck_blueprint.img_gen.default_quality,
            img_gen_aliases=model_deck_blueprint.img_gen.aliases,
            img_gen_waterfalls=model_deck_blueprint.img_gen.waterfalls,
            img_gen_presets=model_deck_blueprint.img_gen.presets,
            img_gen_choice_default=model_deck_blueprint.img_gen.choice_default,
            # Search
            search_aliases=model_deck_blueprint.search.aliases,
            search_waterfalls=model_deck_blueprint.search.waterfalls,
            search_presets=model_deck_blueprint.search.presets,
            search_choice_default=model_deck_blueprint.search.choice_default,
            # DocGen
            doc_gen_aliases=model_deck_blueprint.doc_gen.aliases,
            doc_gen_waterfalls=model_deck_blueprint.doc_gen.waterfalls,
            doc_gen_presets=model_deck_blueprint.doc_gen.presets,
            doc_gen_choice_defaults=model_deck_blueprint.doc_gen.choice_defaults,
            # Judgment
            judgment_aliases=model_deck_blueprint.judgment.aliases,
            judgment_waterfalls=model_deck_blueprint.judgment.waterfalls,
            judgment_presets=model_deck_blueprint.judgment.presets,
            judgment_choice_default=model_deck_blueprint.judgment.choice_default,
            model_deck_config=get_config().inference.model_deck,
        )

    def _find_routed_model_spec(
        self,
        *,
        model_name: str,
        model_type: ModelType,
        backend_match_for_model: BackendMatchForModel,
        matched_backend: InferenceBackend,
        enabled_backends: list[str],
    ) -> InferenceModelSpec | None:
        """The spec serving one pair, found by the routing match of its name, or `None` when the pair is not served.

        Raises:
            ModelManagerError: A backend of the fallback order, or the enabled internal backend, is not loaded.
        """
        if model_spec := matched_backend.get_model_spec(model_type=model_type, handle=model_name):
            return model_spec
        # Not finding the pair in the matched backend can be fine or not according to the matching method
        match backend_match_for_model.matching_method:
            case BackendMatchingMethod.EXACT_MATCH:
                # The route pinned the name to this backend, which declares it as another type only
                # (the caller refused a backend declaring it as no type at all): a call for this pair
                # never goes elsewhere, so the pair is not served.
                log.verbose(
                    f"Model '{model_name}' is routed exactly to backend '{matched_backend.name}' in routing profile "
                    f"'{backend_match_for_model.routing_profile_name}', which does not serve it as "
                    f"{model_type.indefinite_description}, so it is not served as one"
                )
                return None
            case BackendMatchingMethod.PATTERN_MATCH:
                # We can skip it because it was only a pattern match
                return None
            case BackendMatchingMethod.DEFAULT:
                # We could not find the pair, but it was a default match,
                # so we can look for it in the other available backends
                if not backend_match_for_model.fallback_order:
                    # No fallback_order specified - only try the internal backend, whose software-only models
                    # are served whatever the routing profile, unless it is the matched backend we just checked
                    if matched_backend.name == PipelexBackend.INTERNAL:
                        return None
                    return self._find_internal_model_spec(model_name=model_name, model_type=model_type, enabled_backends=enabled_backends)
                # Try fallback_order first, then any enabled backends not in fallback_order
                backends_to_try = backend_match_for_model.fallback_order + [
                    b for b in enabled_backends if b not in backend_match_for_model.fallback_order
                ]
                for available_backend in backends_to_try:
                    if available_backend == matched_backend.name:
                        # we've already checked the matched backend and it didn't have the pair, that's why we're here
                        continue
                    backend = self.inference_backend_library.get_inference_backend(backend_name=available_backend)
                    if backend is None:
                        msg = f"Backend '{available_backend}' not found for model '{model_name}'"
                        raise ModelManagerError(msg)
                    if model_spec := backend.get_model_spec(model_type=model_type, handle=model_name):
                        return model_spec
                # Pair not available in any of the searched backends - skip it
                # Not all models need to be available in the configured backends
                return None

    def _find_internal_model_spec(self, *, model_name: str, model_type: ModelType, enabled_backends: list[str]) -> InferenceModelSpec | None:
        """The internal backend's spec for one pair, or `None` when the internal backend is not enabled or does not declare it.

        The internal backend runs software-only models, with no provider behind them, so whatever the active profile
        it is looked in for a name the profile sends to no enabled backend, and for a default match with no fallback order.

        Raises:
            ModelManagerError: The internal backend is enabled but not loaded.
        """
        if PipelexBackend.INTERNAL not in enabled_backends:
            return None
        internal_backend = self.inference_backend_library.get_inference_backend(backend_name=PipelexBackend.INTERNAL)
        if internal_backend is None:
            msg = f"Backend '{PipelexBackend.INTERNAL}' not found for model '{model_name}'"
            raise ModelManagerError(msg)
        return internal_backend.get_model_spec(model_type=model_type, handle=model_name)

    @override
    def get_inference_model(self, model_handle: str, *, model_type: ModelType) -> InferenceModelSpec:
        if self.model_deck is None:
            msg = "Model deck is not initialized"
            raise RuntimeError(msg)
        return self.model_deck.get_required_inference_model(model_handle=model_handle, model_type=model_type)

    @override
    def get_required_inference_backend(self, backend_name: str) -> InferenceBackend:
        """The backend a worker calls, refused when this process left its credentials unresolved.

        Every reader of a backend's credentials reaches it here, so this one check keeps a keyless
        boot's unset key and endpoint away from every provider client. A keyless boot forces its own
        runs to DRY, so only a keyless process executing live work for another one, as a Temporal
        worker can, gets this far; it is told why rather than sending a provider no key.

        Raises:
            ModelManagerError: No such backend is loaded.
            InferenceBackendCredentialsError: The backend's credentials were not resolved, because the
                process booted without inference.
        """
        backend = self.inference_backend_library.get_inference_backend(backend_name)
        if backend is None:
            msg = f"Inference backend '{backend_name}' not found"
            raise ModelManagerError(msg)
        if backend.unresolved_credentials:
            unresolved_description = ", ".join(
                f"{field_name} ({', '.join(var_names)})" if var_names else field_name
                for field_name, var_names in backend.unresolved_credentials.items()
            )
            unresolved_var_names = backend.unresolved_credential_vars
            msg = (
                f"Inference backend '{backend_name}' cannot be called by this process: it booted without inference "
                f"(needs_inference=False), which loads every backend's models but resolves none of their credentials. "
                f"Left unresolved: {unresolved_description}."
            )
            raise InferenceBackendCredentialsError(
                credentials_error_type=InferenceBackendCredentialsErrorType.NOT_RESOLVED_ON_KEYLESS_BOOT,
                backend_name=backend_name,
                message=msg,
                key_name=unresolved_var_names[0] if unresolved_var_names else next(iter(backend.unresolved_credentials)),
                user_action=UserAction(
                    kind=UserActionKind.CHECK_CREDENTIALS,
                    detail="Boot the process that calls this backend with needs_inference=True, with its credentials set",
                ),
            )
        return backend
