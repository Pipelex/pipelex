from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, Self, cast

from pydantic import Field, PrivateAttr, RootModel, ValidationError

from pipelex import log
from pipelex.cogt.exceptions import (
    InferenceBackendCredentialsError,
    InferenceBackendCredentialsErrorType,
    InferenceBackendLibraryError,
    InferenceBackendLibraryNotFoundError,
    InferenceBackendLibraryValidationError,
    InferenceModelSpecError,
)
from pipelex.cogt.model_backends.backend import InferenceBackend, PipelexBackend
from pipelex.cogt.model_backends.backend_factory import (
    InferenceBackendBlueprint,
    InferenceBackendFactory,
)
from pipelex.cogt.model_backends.gateway_config import GatewayConfig, drop_unknown_gateway_defaults
from pipelex.cogt.model_backends.model_spec_document import MODEL_SPEC_DEFAULTS_TABLE
from pipelex.cogt.model_backends.model_spec_factory import (
    BackendModelSpecs,
    InferenceModelSpecBlueprint,
    InferenceModelSpecFactory,
)
from pipelex.cogt.model_backends.model_spec_keys import ModelSpecSource, describe_rejected_keys, split_model_spec_keys
from pipelex.migration.plan import MigrationPlan
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.config_surface import (
    INFERENCE_BACKEND_CONFIG_SURFACE_ID,
    replay_surface_files_in_memory,
    stale_configuration_warning,
)
from pipelex.system.pipelex_service.gateway_config_merger import GatewayConfigMerger
from pipelex.system.runtime import runtime_manager
from pipelex.tools.misc.dict_utils import (
    apply_to_strings_recursive,
)
from pipelex.tools.misc.toml_utils import (
    describe_toml_base_and_overrides,
    load_toml_from_base_and_overrides,
    load_toml_from_path,
    load_toml_from_path_if_exists,
)
from pipelex.tools.secrets.exceptions import UnknownVarPrefixError, VarFallbackPatternError, VarNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.secrets.secrets_utils import substitute_vars
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec

InferenceBackendLibraryRoot = dict[str, InferenceBackend]


class RecoveredModelSpecs(NamedTuple):
    """One backend's model specs rebuilt from a migrated file, and what the ledger did to get there."""

    model_specs: "dict[str, InferenceModelSpec]"
    plans: list[MigrationPlan]


def backend_toml_path(*, backends_dir_path: str, backend_name: str) -> Path:
    """Where a backend's per-model file lives, spelled once.

    Boot tolerance replays a stale file in memory and rebuilds the specs from the result, so the
    retry must read *the file the load read*. Two independent constructions of that path is a
    divergence waiting to happen, and it already was one: a backend name is a raw top-level table
    key of the user's own `inference/backends.toml` and nothing validates it, TOML permits a quoted
    `["/abs/path"]` key, and `Path(directory) / "/abs/path.toml"` drops the directory — so the retry
    would leave the backends directory the load had stayed inside.
    """
    return Path(f"{backends_dir_path}/{backend_name}.toml")


class InferenceBackendLibrary(RootModel[InferenceBackendLibraryRoot]):
    root: InferenceBackendLibraryRoot = Field(default_factory=dict)

    _stale_warning: str | None = PrivateAttr(default=None)

    def reset(self):
        self.root = {}
        self._stale_warning = None

    @classmethod
    def make_empty(cls) -> Self:
        return cls(root={})

    def take_stale_configuration_warning(self) -> str | None:
        """The warning a tolerated load owes the user, once — or `None` when every file was current.

        Parked rather than logged, and the reason is a caller rather than boot order: `pipelex
        doctor` probes the backend files by loading the whole library once per backend, so a loader
        that logged for itself would repeat the same warning a dozen times over one stale directory.
        Handing it over instead lets each caller decide — `ModelManager.setup` emits it (one boot,
        one warning), and the doctor's per-backend probe simply never asks.
        """
        warning, self._stale_warning = self._stale_warning, None
        return warning

    def load(
        self,
        *,
        secrets_provider: SecretsProviderAbstract,
        backends_library_paths: Sequence[Path],
        backends_dir_path: str,
        include_disabled: bool = False,
        gateway_config: GatewayConfig | None = None,
        lenient: bool = False,
    ):
        """Load backend configurations from TOML files.

        For pipelex_gateway, uses the provided remote config and merges with local overrides.

        **A file left behind by a schema change is carried forward rather than fatal.** When a local
        per-backend TOML is refused, the `inference-backend` ledger is replayed over that one file
        **in memory** and the loader's own steps re-run over what comes back; a load that then
        succeeds parks a warning (`take_stale_configuration_warning`) naming the files and the
        `pipelex migrate` remedy. Nothing is written — only the explicit command writes, which is
        why the warning keeps coming back until it is run. A file the ledger cannot explain raises
        exactly what it raised before: the retry either recovers or gets out of the way.

        The warning names the files *this* load merged, which is not always every file the command
        would repair: `backends_dir_path` picks one directory (a project's `.pipelex/` wins the whole
        directory over the global one), while `pipelex migrate` walks every configuration root.

        The index itself is one document read from several files: the base `backends.toml` first,
        then each `backends_override.toml` that exists, deep-merged in order so a personal file
        carrying only `[<backend>] enabled = true` flips that one flag and leaves the table's other
        keys to the base. `config_manager.backends_file_paths()` is the sequence every reader passes.

        Args:
            secrets_provider: Provider for secrets/credentials.
            backends_library_paths: The base `backends.toml` first, then the override files in merge order.
            backends_dir_path: Path to directory containing per-backend TOML files.
            include_disabled: Whether to include disabled backends.
            gateway_config: Gateway configuration for Pipelex Gateway backend.
            lenient: When True, skip a backend whose *credentials* cannot be resolved, or the
                gateway backend when no `gateway_config` was handed in, instead of raising — that
                is the whole of the tolerance. A malformed configuration (an unknown
                or invalid key, a model spec that is not a table, a missing per-backend TOML) stays
                fatal in both modes: a config typo must never silently delete a backend, because the
                commands that boot leniently (validate, show, dry runs) would then report the far
                more confusing "model not found" for every handle that backend served. A *stale* key
                — one the ledger explains — is not a typo and is not covered by this flag at all: it
                is carried forward in both modes, or fatal in both, according to the ledger alone.
        """
        stale_plans: list[MigrationPlan] = []
        library_paths_description = describe_toml_base_and_overrides(paths=backends_library_paths)
        try:
            backends_dict = load_toml_from_base_and_overrides(paths=backends_library_paths)
        except FileNotFoundError as file_not_found_exc:
            msg = f"Could not find inference backend library at {library_paths_description}: {file_not_found_exc}"
            raise InferenceBackendLibraryNotFoundError(msg) from file_not_found_exc

        # Create a partial function with the secrets provider bound
        substitute_vars_with_provider = partial(substitute_vars, secrets_provider=secrets_provider)

        # We'll split the read settings into standard fields and extra config
        backend_blueprint_standard_fields = InferenceBackendBlueprint.model_fields.keys()
        for backend_name, backend_dict in backends_dict.items():
            extra_config: dict[str, Any] = {}
            inference_backend_blueprint_dict_raw = backend_dict.copy()
            enabled = inference_backend_blueprint_dict_raw.get("enabled", True)
            if not enabled and not include_disabled:
                continue
            if runtime_manager.is_ci_testing and backend_name == "vertexai":
                continue
            try:
                inference_backend_blueprint_dict = apply_to_strings_recursive(
                    inference_backend_blueprint_dict_raw, transform_func=substitute_vars_with_provider
                )
            except VarFallbackPatternError as var_fallback_pattern_exc:
                if lenient:
                    log.verbose(f"Skipping backend '{backend_name}': variable fallback pattern error")
                    continue
                msg = f"Variable substitution failed due to a pattern error in {library_paths_description}:\n{var_fallback_pattern_exc}"
                key_name = "unknown"
                raise InferenceBackendCredentialsError(
                    credentials_error_type=InferenceBackendCredentialsErrorType.VAR_FALLBACK_PATTERN,
                    backend_name=backend_name,
                    message=msg,
                    key_name=key_name,
                ) from var_fallback_pattern_exc
            except VarNotFoundError as var_not_found_exc:
                if lenient:
                    log.verbose(f"Skipping backend '{backend_name}': missing credential variable '{var_not_found_exc.var_name}'")
                    continue
                msg = (
                    f"Variable substitution failed due to a 'variable not found' error in {library_paths_description}:\n"
                    f"Backend name: '{backend_name}', Variable name: '{var_not_found_exc.var_name}'\n"
                    f"{var_not_found_exc}\nRun mode: '{runtime_manager.run_mode}'"
                )
                raise InferenceBackendCredentialsError(
                    credentials_error_type=InferenceBackendCredentialsErrorType.VAR_NOT_FOUND,
                    backend_name=backend_name,
                    message=msg,
                    key_name=var_not_found_exc.var_name,
                ) from var_not_found_exc
            except UnknownVarPrefixError as unknown_var_prefix_exc:
                if lenient:
                    log.verbose(f"Skipping backend '{backend_name}': unknown variable prefix for '{unknown_var_prefix_exc.var_name}'")
                    continue
                raise InferenceBackendCredentialsError(
                    credentials_error_type=InferenceBackendCredentialsErrorType.UNKNOWN_VAR_PREFIX,
                    backend_name=backend_name,
                    message=(
                        f"Variable substitution failed due to an unknown variable prefix error "
                        f"in {library_paths_description}:\n{unknown_var_prefix_exc}"
                    ),
                    key_name=unknown_var_prefix_exc.var_name,
                ) from unknown_var_prefix_exc

            try:
                for backend_blueprint_key in backend_dict:
                    if backend_blueprint_key not in backend_blueprint_standard_fields:
                        extra_config[backend_blueprint_key] = inference_backend_blueprint_dict.pop(backend_blueprint_key)
                try:
                    backend_blueprint = InferenceBackendBlueprint.model_validate(inference_backend_blueprint_dict)
                except ValidationError as validation_error:
                    # The index file's own refusal, said with the backend and the file in front of the
                    # analysis: pydantic's error alone names a field, and every table of this file has
                    # that field.
                    validation_error_msg = format_pydantic_validation_error(validation_error)
                    msg = f"Invalid inference backend '{backend_name}' in {library_paths_description}: {validation_error_msg}"
                    raise InferenceBackendLibraryValidationError(msg, backend_name=backend_name) from validation_error

                # Handle pipelex_gateway specially - use remote config
                backend_config_source: str
                model_spec_source: ModelSpecSource
                if PipelexBackend.is_gateway_backend(backend_name):
                    if gateway_config is None:
                        if lenient:
                            log.verbose(f"Skipping backend '{backend_name}': gateway model specs not available")
                            continue
                        # A caller's omission rather than a user's: the boot fetches the gateway's
                        # specs whenever `is_pipelex_gateway_enabled` reads this same file as enabled,
                        # and that reader and this loop agree on what "enabled" means. Reachable only
                        # by loading the library directly without a gateway config.
                        msg = (
                            f"Backend '{backend_name}' is enabled in {library_paths_description} but no Pipelex Gateway model specs "
                            "were given to the loader: pass `gateway_config`, or disable the backend"
                        )
                        raise InferenceBackendLibraryError(msg, backend_name=backend_name)
                    extra_config["aws_region"] = gateway_config.aws_region
                    model_spec_source = ModelSpecSource.REMOTE_GATEWAY
                    model_specs_dict, backend_config_source = self._load_gateway_model_specs(
                        gateway_config=gateway_config,
                        backend_name=backend_name,
                        backends_dir_path=backends_dir_path,
                        substitute_vars_with_provider=substitute_vars_with_provider,
                    )
                else:
                    model_spec_source = ModelSpecSource.LOCAL_FILE
                    model_specs_dict, backend_config_source = self._load_local_model_specs(
                        backend_name=backend_name,
                        backends_dir_path=backends_dir_path,
                        substitute_vars_with_provider=substitute_vars_with_provider,
                    )

                try:
                    backend_model_specs = self._build_backend_model_specs(
                        model_specs_dict=model_specs_dict,
                        backend_name=backend_name,
                        backend_config_source=backend_config_source,
                        model_spec_source=model_spec_source,
                        backend_blueprint=backend_blueprint,
                    )
                except InferenceBackendLibraryError:
                    recovered = self._local_model_specs_the_ledger_can_explain(
                        backend_name=backend_name,
                        backends_dir_path=backends_dir_path,
                        model_spec_source=model_spec_source,
                        backend_blueprint=backend_blueprint,
                        substitute_vars_with_provider=substitute_vars_with_provider,
                    )
                    if recovered is None:
                        raise
                    backend_model_specs = recovered.model_specs
                    stale_plans.extend(recovered.plans)
                backend = InferenceBackendFactory.make_inference_backend(
                    name=backend_name,
                    blueprint=backend_blueprint,
                    extra_config=extra_config,
                    model_specs=backend_model_specs,
                )
                self.root[backend_name] = backend
            except InferenceBackendCredentialsError as credentials_exc:
                if lenient:
                    log.verbose(f"Skipping backend '{backend_name}': {credentials_exc}")
                    continue
                raise

        # One warning for the whole load rather than one per backend: a schema change lands on every
        # file of the directory at once, and a user reading a dozen warnings would learn nothing the
        # first did not already say.
        self._stale_warning = stale_configuration_warning(plans=stale_plans, walked_dirs=config_manager.existing_config_dirs) if stale_plans else None

    @classmethod
    def _build_backend_model_specs(
        cls,
        *,
        model_specs_dict: BackendModelSpecs,
        backend_name: str,
        backend_config_source: str,
        model_spec_source: ModelSpecSource,
        backend_blueprint: InferenceBackendBlueprint,
    ) -> "dict[str, InferenceModelSpec]":
        """Turn one backend's raw tables into model specs: pop `[defaults]`, split, merge, validate.

        Its own method so the boot-tolerance retry can run it a second time over a migrated document
        without duplicating a line of it. The read is non-destructive — `[defaults]` is popped from a
        copy — because the caller may still need the original tables when this raises.
        """
        remaining_tables = dict(model_specs_dict)
        defaults_dict: dict[str, Any] = remaining_tables.pop(MODEL_SPEC_DEFAULTS_TABLE, {})
        backend_model_specs: dict[str, InferenceModelSpec] = {}
        for model_spec_name, value in remaining_tables.items():
            if not isinstance(value, dict):
                msg = f"Model spec '{model_spec_name}' for backend '{backend_name}' from {backend_config_source} is not a dictionary"
                raise InferenceModelSpecError(msg, backend_name=backend_name)
            model_spec_dict: dict[str, Any] = cast("dict[str, Any]", value)
            try:
                # A per-model key the blueprint does not know is a request header only if it is shaped
                # like one; anything else is a typo or a dead field, and what happens to it depends on
                # where the table came from.
                key_split = split_model_spec_keys(model_spec_dict=model_spec_dict)
                if key_split.rejected:
                    match model_spec_source:
                        case ModelSpecSource.LOCAL_FILE:
                            # Fatal in lenient mode too: leniency covers credentials only (see the docstring),
                            # and this is not a credentials error, so the lenient `except` in `load` lets it
                            # through. What may still catch it is the ledger, one level up.
                            plural = "s" if len(key_split.rejected) > 1 else ""
                            msg = (
                                f"Unknown key{plural} on model '{model_spec_name}' for backend '{backend_name}' "
                                f"from {backend_config_source}: {describe_rejected_keys(rejected=key_split.rejected)}"
                            )
                            raise InferenceBackendLibraryError(msg, backend_name=backend_name)
                        case ModelSpecSource.REMOTE_GATEWAY:
                            # Version skew, the same judgement `drop_unknown_gateway_defaults` makes for the
                            # `defaults` block: pruned, and silently — this can run before the log hub is set.
                            pass
                # Start from the defaults, then override with the model's own fields
                model_spec_blueprint_dict = defaults_dict.copy()
                model_spec_blueprint_dict.update(key_split.fields)
                model_spec_blueprint = InferenceModelSpecBlueprint.model_validate(model_spec_blueprint_dict)
                model_spec = InferenceModelSpecFactory.make_inference_model_spec(
                    backend_name=backend_name,
                    name=model_spec_name,
                    blueprint=model_spec_blueprint,
                    backend_listed_constraints=backend_blueprint.listed_constraints,
                    backend_valued_constraints=backend_blueprint.valued_constraints,
                    extra_headers=key_split.headers,
                )
                backend_model_specs[model_spec_name] = model_spec
            except ValidationError as validation_error:
                validation_error_msg = format_pydantic_validation_error(validation_error)
                msg = (
                    f"Invalid inference model spec '{model_spec_name}' for backend '{backend_name}' "
                    f"from {backend_config_source}: {validation_error_msg}"
                )
                raise InferenceBackendLibraryError(msg, backend_name=backend_name) from validation_error
            except InferenceModelSpecError as exc:
                msg = f"Failed to load inference model spec '{model_spec_name}' for backend '{backend_name}' from {backend_config_source}"
                raise InferenceBackendLibraryError(msg, backend_name=backend_name) from exc
        return backend_model_specs

    def _local_model_specs_the_ledger_can_explain(
        self,
        *,
        backend_name: str,
        backends_dir_path: str,
        model_spec_source: ModelSpecSource,
        backend_blueprint: InferenceBackendBlueprint,
        substitute_vars_with_provider: Any,
    ) -> RecoveredModelSpecs | None:
        """This backend's specs rebuilt from its file as the ledger would leave it, or `None`.

        `None` covers both ways this declines — the ledger had nothing to say about the file, or it
        did and the result still does not load. Neither is this method's to report: the caller
        re-raises the error the file actually produced, which names the key the user can act on,
        where "migration did not help" would name nothing.

        **One file, and only a local one.** The helper deep-merges the paths it is given, which is
        right for a tier stack and wrong here — backend files are independent documents that share no
        keys, so they are replayed one at a time. And the gateway backend is left out on purpose:
        `GatewayConfigMerger` ignores a local `[defaults]` outright and keeps only `sdk` and
        `structure_method` from a per-model override, so a stale key in `pipelex_gateway.toml` is
        filtered out before any spec is built and can never be what refused the load. `pipelex
        migrate` still repairs that file on disk — the surface claims every `*.toml` in the directory
        — but at boot there is nothing there to carry forward.
        """
        match model_spec_source:
            case ModelSpecSource.REMOTE_GATEWAY:
                return None
            case ModelSpecSource.LOCAL_FILE:
                pass
        path_to_model_specs_toml = backend_toml_path(backends_dir_path=backends_dir_path, backend_name=backend_name)
        replayed = replay_surface_files_in_memory(surface_id=INFERENCE_BACKEND_CONFIG_SURFACE_ID, paths=[path_to_model_specs_toml])
        if replayed is None:
            return None
        backend_config_source = f"file '{path_to_model_specs_toml}'"
        try:
            migrated_specs_dict = self._substitute_model_spec_vars(
                model_specs_dict=replayed.config_dict,
                backend_name=backend_name,
                source=backend_config_source,
                substitute_vars_with_provider=substitute_vars_with_provider,
            )
            model_specs = self._build_backend_model_specs(
                model_specs_dict=migrated_specs_dict,
                backend_name=backend_name,
                backend_config_source=backend_config_source,
                model_spec_source=model_spec_source,
                backend_blueprint=backend_blueprint,
            )
        except (InferenceBackendLibraryError, InferenceModelSpecError, InferenceBackendCredentialsError):
            return None
        return RecoveredModelSpecs(model_specs=model_specs, plans=replayed.plans)

    def _load_gateway_model_specs(
        self,
        gateway_config: GatewayConfig,
        *,
        backend_name: str,
        backends_dir_path: str,
        substitute_vars_with_provider: Any,
    ) -> tuple[BackendModelSpecs, str]:
        """Load model specs for pipelex_gateway from remote config.

        Args:
            gateway_config: Gateway configuration for Pipelex Gateway backend.
            backend_name: Name the backend library gives this gateway backend.
            backends_dir_path: Path to directory containing local override file.
            substitute_vars_with_provider: Function to substitute variables.

        Returns:
            Model specs dictionary merged from remote and local overrides.

        Raises:
            InferenceBackendCredentialsError: If variable substitution fails.
        """
        # Load local overrides if they exist
        path_to_local_overrides = f"{backends_dir_path}/{PipelexBackend.GATEWAY}.toml"
        local_overrides = load_toml_from_path_if_exists(path=path_to_local_overrides) or {}

        # Merge remote config with local overrides
        model_specs_dict = GatewayConfigMerger.merge(
            gateway_model_specs=drop_unknown_gateway_defaults(gateway_model_specs=gateway_config.model_specs),
            local_overrides=local_overrides,
        )

        backend_config_source = f"remote config with local overrides from '{path_to_local_overrides}'"
        # Apply variable substitution (in case remote config has any variables)
        model_specs_dict = self._substitute_model_spec_vars(
            model_specs_dict=model_specs_dict,
            backend_name=backend_name,
            source=backend_config_source,
            substitute_vars_with_provider=substitute_vars_with_provider,
        )

        return model_specs_dict, backend_config_source

    def _load_local_model_specs(
        self,
        backend_name: str,
        *,
        backends_dir_path: str,
        substitute_vars_with_provider: Any,
    ) -> tuple[BackendModelSpecs, str]:
        """Load model specs from local TOML file.

        Args:
            backend_name: Name of the backend.
            backends_dir_path: Path to directory containing TOML files.
            substitute_vars_with_provider: Function to substitute variables.

        Returns:
            Model specs dictionary from local TOML.

        Raises:
            InferenceBackendLibraryError: If the file is missing.
            InferenceBackendCredentialsError: If variable substitution fails.
        """
        path_to_model_specs_toml = backend_toml_path(backends_dir_path=backends_dir_path, backend_name=backend_name)
        try:
            model_specs_dict_raw = load_toml_from_path(path=path_to_model_specs_toml)
        except FileNotFoundError as file_not_found_exc:
            msg = f"Failed to load inference model specs from file '{path_to_model_specs_toml}': {file_not_found_exc}"
            raise InferenceBackendLibraryError(msg, backend_name=backend_name) from file_not_found_exc

        backend_config_source = f"file '{path_to_model_specs_toml}'"
        model_specs_dict = self._substitute_model_spec_vars(
            model_specs_dict=model_specs_dict_raw,
            backend_name=backend_name,
            source=backend_config_source,
            substitute_vars_with_provider=substitute_vars_with_provider,
        )
        return model_specs_dict, backend_config_source

    @classmethod
    def _substitute_model_spec_vars(
        cls,
        *,
        model_specs_dict: BackendModelSpecs,
        backend_name: str,
        source: str,
        substitute_vars_with_provider: Any,
    ) -> BackendModelSpecs:
        """Resolve variable placeholders in model specs, as a *credentials* failure when one cannot be.

        The error class carries the leniency decision: `load(lenient=True)` skips a backend whose
        credentials are missing, and nothing else. Raising anything broader here would put a
        malformed-config failure on the same silent path.

        Raises:
            InferenceBackendCredentialsError: If a variable cannot be resolved.
        """
        try:
            return apply_to_strings_recursive(model_specs_dict, transform_func=substitute_vars_with_provider)
        except VarFallbackPatternError as var_fallback_pattern_exc:
            msg = f"Variable substitution failed in {source}: {var_fallback_pattern_exc}"
            raise InferenceBackendCredentialsError(
                credentials_error_type=InferenceBackendCredentialsErrorType.VAR_FALLBACK_PATTERN,
                backend_name=backend_name,
                # The pattern names several candidates, so no single one of them is the missing key.
                key_name="unknown",
                message=msg,
            ) from var_fallback_pattern_exc
        except VarNotFoundError as var_not_found_exc:
            msg = f"Variable substitution failed in {source}: {var_not_found_exc}"
            raise InferenceBackendCredentialsError(
                credentials_error_type=InferenceBackendCredentialsErrorType.VAR_NOT_FOUND,
                backend_name=backend_name,
                message=msg,
                key_name=var_not_found_exc.var_name,
            ) from var_not_found_exc
        except UnknownVarPrefixError as unknown_var_prefix_exc:
            msg = f"Variable substitution failed in {source}: {unknown_var_prefix_exc}"
            raise InferenceBackendCredentialsError(
                credentials_error_type=InferenceBackendCredentialsErrorType.UNKNOWN_VAR_PREFIX,
                backend_name=backend_name,
                message=msg,
                key_name=unknown_var_prefix_exc.var_name,
            ) from unknown_var_prefix_exc

    def list_backend_names(self) -> list[str]:
        return list(self.root.keys())

    def list_all_model_names(self) -> list[str]:
        """List the names of all models in all backends."""
        all_model_names: set[str] = set()
        for backend in self.root.values():
            all_model_names.update(backend.list_model_names())
        return sorted(all_model_names)

    def get_all_models_and_possible_backends(self) -> dict[str, list[str]]:
        """Get a dictionary of all models and their possible backends."""
        all_models_and_possible_backends: dict[str, list[str]] = {}
        for backend in self.root.values():
            for model_name in backend.list_model_names():
                if model_name not in all_models_and_possible_backends:
                    all_models_and_possible_backends[model_name] = []
                all_models_and_possible_backends[model_name].append(backend.name)
        return all_models_and_possible_backends

    def get_inference_backend(self, backend_name: str) -> InferenceBackend | None:
        return self.root.get(backend_name)

    def all_enabled_backends(self) -> list[str]:
        return [backend_name for backend_name, backend in self.root.items() if backend.enabled]
