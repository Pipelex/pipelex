from typing_extensions import override

from pipelex.cogt.exceptions import GatewayUnknownModelError, ModelManagerError
from pipelex.cogt.extract.extract_setting import ExtractSetting
from pipelex.cogt.img_gen.img_gen_setting import ImgGenSetting
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.model_backends.backend import InferenceBackend, PipelexBackend
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.cogt.model_backends.gateway_config import GatewayConfig
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.model_routing.routing_models import BackendMatchingMethod
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.model_routing.routing_profile_loader import load_active_routing_profile
from pipelex.cogt.models.model_deck import ModelDeck, ModelDeckBlueprint
from pipelex.cogt.models.model_deck_loader import load_model_deck_blueprint
from pipelex.cogt.models.model_manager_abstract import ModelManagerAbstract
from pipelex.cogt.models.model_reference import ModelReference, ModelReferenceKind, ModelReferenceParseError
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.config import get_config
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.pipelex_service.types import RemoteConfigSource
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
    def setup(
        self,
        secrets_provider: SecretsProviderAbstract,
        gateway_config: GatewayConfig | None,
        gateway_config_source: RemoteConfigSource | None,
        needs_inference: bool = True,
    ) -> None:
        self.inference_backend_library.load(
            secrets_provider=secrets_provider,
            backends_library_path=str(config_manager.backends_file_path),
            backends_dir_path=str(config_manager.backends_dir_path),
            gateway_config=gateway_config,
            lenient=not needs_inference,
        )
        enabled_backends = self.inference_backend_library.all_enabled_backends()
        self._routing_profile = load_active_routing_profile(
            routing_profile_library_path=str(config_manager.routing_profiles_file_path),
            enabled_backends=enabled_backends,
            lenient=not needs_inference,
        )
        model_deck_paths = ModelManager.get_model_deck_paths(deck_dir_path=str(config_manager.model_decks_dir_path))
        deck_blueprint = load_model_deck_blueprint(model_deck_paths=model_deck_paths)
        self.model_deck = self.build_deck(enabled_backends=enabled_backends, model_deck_blueprint=deck_blueprint)

        self._enforce_gateway_model_membership(
            gateway_config=gateway_config,
            gateway_config_source=gateway_config_source,
        )

    def _enforce_gateway_model_membership(
        self,
        gateway_config: GatewayConfig | None,
        gateway_config_source: RemoteConfigSource | None,
    ) -> None:
        """Fail loudly when the deck references a handle the gateway should provide but cannot.

        Runs even when ``missing_presets_reaction = "log"`` (the default), because a missing
        gateway model is a distinct failure mode from a generic preset mismatch: it means the
        active gateway specs (fresh or cached) are out of sync with what the deck author
        declared. Surfacing this as ``GatewayUnknownModelError`` lets the agent CLI hint at
        cache-refresh remediation when the config was sourced from the on-disk fallback.

        We only fire the check when both ``gateway_config`` and ``gateway_config_source`` are
        set — that is, when the gateway is actually live in this setup pass.

        Waterfall semantics: a waterfall reference is "known" if AT LEAST ONE of its
        fallbacks resolves to a known handle. At runtime the deck walks the list and uses
        the first available model (when ``is_model_fallback_enabled`` is true, the default),
        so a deck like ``["future-model", "current-model"]`` is perfectly valid as long as
        ``current-model`` is in the gateway specs.
        """
        if gateway_config is None or gateway_config_source is None:
            return
        deck = self.get_model_deck()
        gateway_spec_names = {name for name in gateway_config.model_specs if name != "defaults"}

        for handle, model_type in self._collect_deck_referenced_handles(deck):
            try:
                ref = ModelReference.parse(handle)
            except ModelReferenceParseError:
                continue
            candidates = self._resolve_terminal_candidates(deck=deck, ref=ref, model_type=model_type)
            if not candidates:
                continue
            if any(candidate in deck.inference_models or candidate in gateway_spec_names for candidate in candidates):
                continue
            # No candidate resolves to a known handle. Report the first one — it's the
            # primary the user is asking for; subsequent entries are fallbacks.
            raise GatewayUnknownModelError(model_name=candidates[0], source=gateway_config_source)

    @classmethod
    def _collect_deck_referenced_handles(cls, deck: ModelDeck) -> list[tuple[str, ModelType]]:
        """Gather the (handle, model_type) pairs that the deck advertises as usable.

        Covers presets and choice defaults across every model type. Aliases and waterfalls
        are intentionally NOT enumerated directly — they are reachable via preset/choice
        references, and the resolver walks through them. Including them here would force the
        check on dangling helpers the user has not actively wired into a preset.
        """
        references: list[tuple[str, ModelType]] = []
        for llm_setting in deck.llm_presets.values():
            references.append((llm_setting.model, ModelType.LLM))
        llm_text_handle = cls._extract_choice_handle(deck.llm_choice_defaults.for_text)
        if llm_text_handle is not None:
            references.append((llm_text_handle, ModelType.LLM))
        llm_object_handle = cls._extract_choice_handle(deck.llm_choice_defaults.for_object)
        if llm_object_handle is not None:
            references.append((llm_object_handle, ModelType.LLM))
        for extract_setting in deck.extract_presets.values():
            references.append((extract_setting.model, ModelType.TEXT_EXTRACTOR))
        extract_default_handle = cls._extract_choice_handle(deck.extract_choice_default)
        if extract_default_handle is not None:
            references.append((extract_default_handle, ModelType.TEXT_EXTRACTOR))
        for img_gen_setting in deck.img_gen_presets.values():
            references.append((img_gen_setting.model, ModelType.IMG_GEN))
        img_gen_default_handle = cls._extract_choice_handle(deck.img_gen_choice_default)
        if img_gen_default_handle is not None:
            references.append((img_gen_default_handle, ModelType.IMG_GEN))
        for search_setting in deck.search_presets.values():
            references.append((search_setting.model, ModelType.SEARCH))
        search_default_handle = cls._extract_choice_handle(deck.search_choice_default)
        if search_default_handle is not None:
            references.append((search_default_handle, ModelType.SEARCH))
        return references

    @classmethod
    def _extract_choice_handle(cls, choice: LLMSetting | ExtractSetting | ImgGenSetting | SearchSetting | ModelReference | str | None) -> str | None:
        """Normalise a ``*ModelChoice`` union (LLMModelChoice etc.) to a raw handle string.

        Choice defaults can be a typed setting object, a parsed ``ModelReference``, or a raw
        string — all three paths point at a handle we need to validate.
        """
        if choice is None:
            return None
        if isinstance(choice, str):
            return choice
        if isinstance(choice, ModelReference):
            return choice.raw
        return choice.model

    @classmethod
    def _resolve_terminal_candidates(
        cls,
        deck: ModelDeck,
        ref: ModelReference,
        model_type: ModelType,
    ) -> list[str]:
        """Return every terminal handle reachable from ``ref`` via aliases/waterfalls.

        For ``HANDLE`` references: returns ``[name]`` (bare strings are HANDLEs by design —
        see ``ModelReference.parse`` for the BREAKING CHANGE note).

        For ``ALIAS`` references: follows the alias target. Cycles return ``[]``.

        For ``WATERFALL`` references: follows EVERY fallback in order (or only the first
        when ``model_deck_config.is_model_fallback_enabled`` is false, matching runtime
        behaviour at ``model_deck._get_optional_inference_model_with_fallback``). Cycles
        across either alias or waterfall keys return ``[]`` for the cycling branch but do
        not poison the rest of the candidate list.

        For ``PRESET`` references: returns ``[]`` (presets are not handles).
        """
        aliases, waterfalls = deck.get_aliases_and_waterfalls_for_type(model_type)
        is_fallback_enabled = deck.model_deck_config.is_model_fallback_enabled
        return cls._collect_candidates(
            ref=ref,
            aliases=aliases,
            waterfalls=waterfalls,
            is_fallback_enabled=is_fallback_enabled,
            visited=set(),
        )

    @classmethod
    def _collect_candidates(
        cls,
        ref: ModelReference,
        aliases: dict[str, str],
        waterfalls: dict[str, list[str]],
        is_fallback_enabled: bool,
        visited: set[tuple[ModelReferenceKind, str]],
    ) -> list[str]:
        # Cycle key is (kind, name): an alias and a waterfall can share a name yet be distinct nodes.
        visit_key: tuple[ModelReferenceKind, str]
        match ref.kind:
            case ModelReferenceKind.HANDLE:
                return [ref.name]
            case ModelReferenceKind.ALIAS:
                visit_key = (ref.kind, ref.name)
                if visit_key in visited:
                    return []
                visited.add(visit_key)
                target = aliases.get(ref.name)
                if target is None:
                    return [ref.name]
                try:
                    next_ref = ModelReference.parse(target)
                except ModelReferenceParseError:
                    return []
                return cls._collect_candidates(
                    ref=next_ref,
                    aliases=aliases,
                    waterfalls=waterfalls,
                    is_fallback_enabled=is_fallback_enabled,
                    visited=visited,
                )
            case ModelReferenceKind.WATERFALL:
                visit_key = (ref.kind, ref.name)
                if visit_key in visited:
                    return []
                visited.add(visit_key)
                fallback_list = waterfalls.get(ref.name)
                if not fallback_list:
                    return [ref.name]
                # Runtime only tries the first fallback when fallback is disabled; mirror
                # that here so the membership check stays consistent with what actually runs.
                entries = fallback_list if is_fallback_enabled else fallback_list[:1]
                candidates: list[str] = []
                for entry in entries:
                    try:
                        next_ref = ModelReference.parse(entry)
                    except ModelReferenceParseError:
                        continue
                    # Fresh visited set per branch so two waterfall entries that legitimately
                    # share an alias don't kill the second one.
                    candidates.extend(
                        cls._collect_candidates(
                            ref=next_ref,
                            aliases=aliases,
                            waterfalls=waterfalls,
                            is_fallback_enabled=is_fallback_enabled,
                            visited=set(visited),
                        )
                    )
                return candidates
            case ModelReferenceKind.PRESET:
                return []

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

        for model_name in all_models_and_possible_backends:
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
                        # Use fallback_order if specified, otherwise only try internal backend
                        if backend_match_for_model.fallback_order:
                            # Try fallback_order first, then any enabled backends not in fallback_order
                            backends_to_try = backend_match_for_model.fallback_order + [
                                b for b in enabled_backends if b not in backend_match_for_model.fallback_order
                            ]
                        else:
                            # No fallback_order specified - only try the internal backend as a special case
                            # Internal backend contains software-only models that should always be available
                            # regardless of which AI provider routing profile is selected
                            backends_to_try = [PipelexBackend.INTERNAL] if PipelexBackend.INTERNAL in enabled_backends else []

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
            model_deck_config=get_config().cogt.model_deck_config,
        )

    @override
    def get_inference_model(self, model_handle: str, model_type: ModelType) -> InferenceModelSpec:
        if self.model_deck is None:
            msg = "Model deck is not initialized"
            raise RuntimeError(msg)
        return self.model_deck.get_required_inference_model(model_handle=model_handle, model_type=model_type)

    @override
    def get_required_inference_backend(self, backend_name: str) -> InferenceBackend:
        backend = self.inference_backend_library.get_inference_backend(backend_name)
        if backend is None:
            msg = f"Inference backend '{backend_name}' not found"
            raise ModelManagerError(msg)
        return backend
