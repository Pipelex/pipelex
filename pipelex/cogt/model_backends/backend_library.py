from collections.abc import Callable, Iterable, Sequence
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
    PluginModelDeclarationError,
)
from pipelex.cogt.model_backends.backend import InferenceBackend, PipelexBackend
from pipelex.cogt.model_backends.backend_factory import (
    InferenceBackendBlueprint,
    InferenceBackendFactory,
)
from pipelex.cogt.model_backends.constraints import ListedConstraint, ValuedConstraint
from pipelex.cogt.model_backends.credential_resolution import CredentialResolution
from pipelex.cogt.model_backends.model_spec_document import MODEL_SPEC_DEFAULTS_TABLE
from pipelex.cogt.model_backends.model_spec_factory import (
    BackendModelSpecs,
    InferenceModelSpecBlueprint,
    InferenceModelSpecFactory,
)
from pipelex.cogt.model_backends.model_spec_keys import describe_rejected_keys, split_model_spec_keys
from pipelex.migration.plan import MigrationPlan
from pipelex.plugins.plugin_model_declarations import PluginModelDeclarations
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.config_surface import (
    INFERENCE_BACKEND_CONFIG_SURFACE_ID,
    replay_surface_files_in_memory,
    stale_configuration_warning,
)
from pipelex.system.runtime import runtime_manager
from pipelex.tools.misc.dict_utils import (
    apply_to_strings_recursive,
)
from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.toml_utils import (
    describe_toml_base_and_overrides,
    load_toml_from_base_and_overrides,
    load_toml_from_path,
    present_toml_override_paths,
)
from pipelex.tools.secrets.exceptions import UnknownVarPrefixError, VarFallbackPatternError, VarNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.secrets.secrets_utils import placeholder_var_names, substitute_vars
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec

InferenceBackendLibraryRoot = dict[str, InferenceBackend]

# A `backends.toml` key that named the remote-config section holding a backend's model specs.
RETIRED_MODEL_SPECS_SECTION_KEY = "model_specs_section"

# Where a keyless load records the variables a backend's own file references, beside the fields of
# its `backends.toml` table (see `InferenceBackend.unresolved_credentials`).
UNRESOLVED_MODEL_SPECS_KEY = "model_specs"

# What the loader runs over every string of a backend's files: substitution on a load that resolves
# credentials, a recorder that keeps the text on one that does not.
StringTransform = Callable[[str], str]

# The declared fields a `${…}` placeholder may stand in: the values a call sends. Every other declared
# field describes the model (its type, its constraints, the SDK that serves it), which a keyless load
# must know without resolving anything, so both loads refuse a placeholder there. A key the blueprint
# does not declare is extra config on a backend and a request header on a model, both sent with a
# call, so both stay templatable.
TEMPLATABLE_BACKEND_FIELDS = frozenset({"endpoint", "api_key", "extra_config"})
TEMPLATABLE_MODEL_SPEC_FIELDS = frozenset({"model_id", "endpoint_path"})


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
        credentials: CredentialResolution = CredentialResolution.REQUIRE,
    ):
        """Load backend configurations from TOML files.

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
            credentials: `REQUIRE` substitutes every `${…}` placeholder and raises
                `InferenceBackendCredentialsError` naming the variable it cannot resolve. `SKIP`, the
                keyless boot's mode (validate, show, dry runs), substitutes nothing and asks the
                secrets provider nothing: every enabled backend is kept with its models and
                constraints, a field of its table that references a variable is left unset, a
                templated model-spec string keeps its text, and the backend records the variables in
                `unresolved_credentials`, which refuses a call to it. Vertex AI mints no token.
                A malformed configuration (an unknown or invalid key, a model spec that is not a
                table, a missing per-backend TOML, a placeholder in a field that describes the model
                rather than a value a call sends) is fatal in both modes: a config typo must never
                silently delete a backend, because the commands that boot keyless would then report
                the far more confusing "model not found" for every handle that backend served. A
                *stale* key — one the ledger explains — is not a typo: it is carried forward in both
                modes, or fatal in both, according to the ledger alone.
        """
        stale_plans: list[MigrationPlan] = []
        library_paths_description = describe_toml_base_and_overrides(paths=backends_library_paths)
        try:
            backends_dict = load_toml_from_base_and_overrides(paths=backends_library_paths)
        except FileNotFoundError as file_not_found_exc:
            msg = f"Could not find inference backend library at '{backends_library_paths[0]}': {file_not_found_exc}"
            raise InferenceBackendLibraryNotFoundError(msg) from file_not_found_exc
        except TomlError as toml_exc:
            # A hand-edited override with a stray quote is a document the library cannot load, and
            # the boot's own clause for that names the file; a raw parse error would not reach it.
            msg = f"Invalid inference backend library {library_paths_description}: {toml_exc}"
            raise InferenceBackendLibraryValidationError(msg) from toml_exc
        if present_toml_override_paths(paths=backends_library_paths):
            # The one trace a machine-wide override leaves: which files this boot actually merged.
            log.info(f"Inference backends read from {library_paths_description}")

        # Create a partial function with the secrets provider bound
        substitute_vars_with_provider = partial(substitute_vars, secrets_provider=secrets_provider)

        # We'll split the read settings into standard fields and extra config
        backend_blueprint_standard_fields = InferenceBackendBlueprint.model_fields.keys()
        for backend_name, backend_dict in backends_dict.items():
            if not isinstance(backend_dict, dict):
                # The likeliest half-written override: `acme = false` where `[acme] enabled = false`
                # was meant. `deep_update` replaces a table by a scalar whole, so this is the first
                # place that can name the file rather than crash on `.copy()`. Fatal in both modes:
                # a keyless boot skips credentials, not a document that is wrong.
                msg = (
                    f"Invalid inference backend '{backend_name}' in {library_paths_description}: "
                    f"expected a table, got {type(backend_dict).__name__} ({backend_dict!r})"
                )
                raise InferenceBackendLibraryValidationError(msg, backend_name=backend_name)
            backend_table = cast("dict[str, Any]", backend_dict)
            extra_config: dict[str, Any] = {}
            inference_backend_blueprint_dict_raw = backend_table.copy()
            enabled = inference_backend_blueprint_dict_raw.get("enabled", True)
            if not enabled and not include_disabled:
                continue
            if enabled and RETIRED_MODEL_SPECS_SECTION_KEY in backend_table:
                # The key once pointed at specs the remote config served. Read as an extra key, it would
                # boot the backend with whatever its own file lists — for a backend whose file was a
                # comment-only template, nothing — and every model routed to it would go missing with no
                # word on why. Fatal in both modes, like any document that is wrong.
                msg = (
                    f"Invalid inference backend '{backend_name}' in {library_paths_description}: "
                    f"'{RETIRED_MODEL_SPECS_SECTION_KEY}' is no longer supported, because model specs are no longer "
                    f"downloaded. List the backend's models in 'backends/{backend_name}.toml' and remove the key, "
                    f"or disable the backend."
                )
                raise InferenceBackendLibraryValidationError(msg, backend_name=backend_name)
            self._refuse_placeholders_in_literal_fields(
                table=backend_table,
                declared_fields=backend_blueprint_standard_fields,
                templatable_fields=TEMPLATABLE_BACKEND_FIELDS,
                where=f"inference backend '{backend_name}' in {library_paths_description}",
                backend_name=backend_name,
            )
            unresolved_credentials: dict[str, list[str]] = {}
            model_spec_var_names: list[str] = []
            match credentials:
                case CredentialResolution.REQUIRE:
                    if runtime_manager.is_ci_testing and backend_name == "vertexai":
                        # Its token is minted over the network at load, which a CI sandbox cannot do.
                        continue
                    inference_backend_blueprint_dict = self._substitute_backend_table_vars(
                        backend_table=inference_backend_blueprint_dict_raw,
                        backend_name=backend_name,
                        library_paths_description=library_paths_description,
                        substitute_vars_with_provider=substitute_vars_with_provider,
                    )
                    model_specs_transform: StringTransform = substitute_vars_with_provider
                case CredentialResolution.SKIP:
                    inference_backend_blueprint_dict = self._backend_table_without_templated_fields(
                        backend_table=inference_backend_blueprint_dict_raw,
                        unresolved_credentials=unresolved_credentials,
                    )
                    model_specs_transform = partial(self._record_placeholder_var_names, var_names=model_spec_var_names)

            for backend_blueprint_key in list(inference_backend_blueprint_dict):
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

            model_specs_dict, backend_config_source = self._load_local_model_specs(
                backend_name=backend_name,
                backends_dir_path=backends_dir_path,
                substitute_vars_with_provider=model_specs_transform,
            )

            try:
                backend_model_specs = self._build_backend_model_specs(
                    model_specs_dict=model_specs_dict,
                    backend_name=backend_name,
                    backend_config_source=backend_config_source,
                    backend_listed_constraints=backend_blueprint.listed_constraints,
                    backend_valued_constraints=backend_blueprint.valued_constraints,
                )
            except InferenceBackendLibraryError:
                recovered = self._local_model_specs_the_ledger_can_explain(
                    backend_name=backend_name,
                    backends_dir_path=backends_dir_path,
                    backend_blueprint=backend_blueprint,
                    substitute_vars_with_provider=model_specs_transform,
                )
                if recovered is None:
                    raise
                backend_model_specs = recovered.model_specs
                stale_plans.extend(recovered.plans)
            if enabled and not backend_model_specs and backend_name != PipelexBackend.INTERNAL:
                # An enabled backend serving nothing is never what a user meant: it is a table an
                # earlier release left enabled over a comment-only file, the Pipelex Gateway's above all.
                # Booting it would only drop every model routed to it from the deck, which says
                # "handle not found" and nothing about why. The internal backend is exempt: plugins
                # add its models after this load.
                msg = (
                    f"Inference backend '{backend_name}' is enabled in {library_paths_description} but "
                    f"{backend_config_source} declares no model. Disable it, or list the models it serves; "
                    f"if a routing profile sends models to it, point that profile at a backend that serves them."
                )
                raise InferenceBackendLibraryValidationError(msg, backend_name=backend_name)
            if model_spec_var_names:
                unresolved_credentials[UNRESOLVED_MODEL_SPECS_KEY] = model_spec_var_names
            backend = InferenceBackendFactory.make_inference_backend(
                name=backend_name,
                blueprint=backend_blueprint,
                extra_config=extra_config,
                model_specs=backend_model_specs,
                credentials=credentials,
                unresolved_credentials=unresolved_credentials,
            )
            self.root[backend_name] = backend

        # One warning for the whole load rather than one per backend: a schema change lands on every
        # file of the directory at once, and a user reading a dozen warnings would learn nothing the
        # first did not already say.
        self._stale_warning = stale_configuration_warning(plans=stale_plans, walked_dirs=config_manager.existing_config_dirs) if stale_plans else None

    @classmethod
    def _substitute_backend_table_vars(
        cls,
        *,
        backend_table: dict[str, Any],
        backend_name: str,
        library_paths_description: str,
        substitute_vars_with_provider: StringTransform,
    ) -> dict[str, Any]:
        """Resolve every placeholder of a backend's `backends.toml` table, as a *credentials* failure when one cannot be.

        Raises:
            InferenceBackendCredentialsError: If a variable cannot be resolved.
        """
        try:
            return apply_to_strings_recursive(backend_table, transform_func=substitute_vars_with_provider)
        except VarFallbackPatternError as var_fallback_pattern_exc:
            msg = f"Variable substitution failed due to a pattern error in {library_paths_description}:\n{var_fallback_pattern_exc}"
            raise InferenceBackendCredentialsError(
                credentials_error_type=InferenceBackendCredentialsErrorType.VAR_FALLBACK_PATTERN,
                backend_name=backend_name,
                message=msg,
                # The pattern names several candidates, so no single one of them is the missing key.
                key_name="unknown",
            ) from var_fallback_pattern_exc
        except VarNotFoundError as var_not_found_exc:
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
            raise InferenceBackendCredentialsError(
                credentials_error_type=InferenceBackendCredentialsErrorType.UNKNOWN_VAR_PREFIX,
                backend_name=backend_name,
                message=(
                    f"Variable substitution failed due to an unknown variable prefix error in {library_paths_description}:\n{unknown_var_prefix_exc}"
                ),
                key_name=unknown_var_prefix_exc.var_name,
            ) from unknown_var_prefix_exc

    @classmethod
    def _backend_table_without_templated_fields(
        cls,
        *,
        backend_table: dict[str, Any],
        unresolved_credentials: dict[str, list[str]],
    ) -> dict[str, Any]:
        """A backend's `backends.toml` table less every field that references a variable, which it records instead.

        A keyless load leaves such a field unset rather than keep its `${…}` text, so that nothing
        can mistake the text for an endpoint or a key: `endpoint` and `api_key` fall back to `None`,
        an extra-config key is absent. A literal field, such as a fixed endpoint, is kept as written.
        """
        kept_fields: dict[str, Any] = {}
        for field_name, value in backend_table.items():
            field_var_names: list[str] = []
            apply_to_strings_recursive({field_name: value}, transform_func=partial(cls._record_placeholder_var_names, var_names=field_var_names))
            if field_var_names:
                unresolved_credentials[field_name] = field_var_names
            else:
                kept_fields[field_name] = value
        return kept_fields

    @classmethod
    def _refuse_placeholders_in_literal_fields(
        cls,
        *,
        table: dict[str, Any],
        declared_fields: Iterable[str],
        templatable_fields: frozenset[str],
        where: str,
        backend_name: str,
    ) -> None:
        """Refuse a `${…}` placeholder in a declared field that describes the model, on every load.

        Checked on the raw text, before any substitution, so a load that resolves credentials and one
        that does not refuse the same files: a keyless load cannot resolve such a field, and a verdict
        that held only where the variable is set is what the keyless boot exists to rule out.

        Raises:
            InferenceBackendLibraryValidationError: Naming the field and the variables it references.
        """
        literal_fields = set(declared_fields) - templatable_fields
        for field_name, value in table.items():
            if field_name not in literal_fields:
                continue
            var_names: list[str] = []
            apply_to_strings_recursive({field_name: value}, transform_func=partial(cls._record_placeholder_var_names, var_names=var_names))
            if var_names:
                msg = (
                    f"Invalid {where}: '{field_name}' references {', '.join(var_names)}, but a placeholder may only "
                    f"stand in a value a call sends (an API key, an endpoint, a model id, a request header or an extra "
                    f"config key). '{field_name}' describes the model, which a boot without inference must know "
                    f"without resolving anything: write it literally."
                )
                raise InferenceBackendLibraryValidationError(msg, backend_name=backend_name)

    @classmethod
    def _record_placeholder_var_names(cls, content: str, *, var_names: list[str]) -> str:
        """Add the variables `content` references to `var_names`, and return `content` as it is."""
        for var_name in placeholder_var_names(content=content):
            if var_name not in var_names:
                var_names.append(var_name)
        return content

    @classmethod
    def _build_backend_model_specs(
        cls,
        *,
        model_specs_dict: BackendModelSpecs,
        backend_name: str,
        backend_config_source: str,
        backend_listed_constraints: list[ListedConstraint],
        backend_valued_constraints: dict[ValuedConstraint, Any],
    ) -> "dict[str, InferenceModelSpec]":
        """Turn one backend's raw tables into model specs: pop `[defaults]`, split, merge, validate.

        Its own method so the boot-tolerance retry can run it a second time over a migrated document
        without duplicating a line of it, and so a plugin's internal models are built by the very path
        a backend file's are. The read is non-destructive — `[defaults]` is popped from a copy —
        because the caller may still need the original tables when this raises.
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
                # like one; anything else is a typo or a dead field, and is refused.
                key_split = split_model_spec_keys(model_spec_dict=model_spec_dict)
                if key_split.rejected:
                    # Fatal on a keyless load too: that load skips credentials, and this is a document
                    # that is wrong. What may still catch it is the ledger, one level up.
                    plural = "s" if len(key_split.rejected) > 1 else ""
                    msg = (
                        f"Unknown key{plural} on model '{model_spec_name}' for backend '{backend_name}' "
                        f"from {backend_config_source}: {describe_rejected_keys(rejected=key_split.rejected)}"
                    )
                    raise InferenceBackendLibraryError(msg, backend_name=backend_name)
                # Start from the defaults, then override with the model's own fields
                model_spec_blueprint_dict = defaults_dict.copy()
                model_spec_blueprint_dict.update(key_split.fields)
                model_spec_blueprint = InferenceModelSpecBlueprint.model_validate(model_spec_blueprint_dict)
                model_spec = InferenceModelSpecFactory.make_inference_model_spec(
                    backend_name=backend_name,
                    name=model_spec_name,
                    blueprint=model_spec_blueprint,
                    backend_listed_constraints=backend_listed_constraints,
                    backend_valued_constraints=backend_valued_constraints,
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
        backend_blueprint: InferenceBackendBlueprint,
        substitute_vars_with_provider: StringTransform,
    ) -> RecoveredModelSpecs | None:
        """This backend's specs rebuilt from its file as the ledger would leave it, or `None`.

        `None` covers both ways this declines — the ledger had nothing to say about the file, or it
        did and the result still does not load. Neither is this method's to report: the caller
        re-raises the error the file actually produced, which names the key the user can act on,
        where "migration did not help" would name nothing.

        **One file at a time.** The helper deep-merges the paths it is given, which is
        right for a tier stack and wrong here — backend files are independent documents that share no
        keys, so they are replayed one at a time.
        """
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
                backend_listed_constraints=backend_blueprint.listed_constraints,
                backend_valued_constraints=backend_blueprint.valued_constraints,
            )
        except (InferenceBackendLibraryError, InferenceModelSpecError, InferenceBackendCredentialsError):
            return None
        return RecoveredModelSpecs(model_specs=model_specs, plans=replayed.plans)

    def _load_local_model_specs(
        self,
        backend_name: str,
        *,
        backends_dir_path: str,
        substitute_vars_with_provider: StringTransform,
    ) -> tuple[BackendModelSpecs, str]:
        """Load model specs from local TOML file.

        Args:
            backend_name: Name of the backend.
            backends_dir_path: Path to directory containing TOML files.
            substitute_vars_with_provider: What runs over every string of the file: substitution, or on a
                keyless load a recorder that keeps the text.

        Returns:
            Model specs dictionary from local TOML.

        Raises:
            InferenceBackendLibraryError: If the file is missing.
            InferenceBackendLibraryValidationError: If a field describing a model references a variable.
            InferenceBackendCredentialsError: If variable substitution fails.
        """
        path_to_model_specs_toml = backend_toml_path(backends_dir_path=backends_dir_path, backend_name=backend_name)
        try:
            model_specs_dict_raw = load_toml_from_path(path=path_to_model_specs_toml)
        except FileNotFoundError as file_not_found_exc:
            msg = f"Failed to load inference model specs from file '{path_to_model_specs_toml}': {file_not_found_exc}"
            raise InferenceBackendLibraryError(msg, backend_name=backend_name) from file_not_found_exc

        backend_config_source = f"file '{path_to_model_specs_toml}'"
        for model_spec_name, model_spec_table in model_specs_dict_raw.items():
            if isinstance(model_spec_table, dict):
                self._refuse_placeholders_in_literal_fields(
                    table=cast("dict[str, Any]", model_spec_table),
                    declared_fields=InferenceModelSpecBlueprint.model_fields.keys(),
                    templatable_fields=TEMPLATABLE_MODEL_SPEC_FIELDS,
                    where=f"model '{model_spec_name}' for backend '{backend_name}' in {backend_config_source}",
                    backend_name=backend_name,
                )
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
        substitute_vars_with_provider: StringTransform,
    ) -> BackendModelSpecs:
        """Resolve variable placeholders in model specs, as a *credentials* failure when one cannot be.

        Only a load that resolves credentials can raise here: a keyless load's transform keeps the
        text and records the variables, and never raises.

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

    def merge_plugin_internal_models(self, *, plugin_model_declarations: PluginModelDeclarations, backends_dir_path: str) -> bool:
        """Merge the internal models the plugins declared into the internal backend, or report there is none to merge into.

        Each table is built by the path a backend file's tables take: a key the model spec
        does not know is the plugin author's mistake and fatal, as it is in a local file. The table is complete on
        its own, so the `[defaults]` of `internal.toml` is not applied to it.

        **A name the installation's `internal.toml` already declares is refused rather than overridden**, naming
        the plugin and the file: which of the two declarations a boot would run would otherwise depend on nothing
        the user can see. Model names are not global across backends — the same name in several backend files is
        the ordinary case, and the routing profile picks one — so a name another backend declares is left to the
        routing, exactly as it is for a model the file declares.

        Returns:
            Whether this load has an internal backend. `False` when the installation disables it, or declares none:
            the plugins' models are then not merged, as a disabled backend's own models are not loaded, and the
            caller leaves the plugins' model deck defaults out for the same reason.

        Raises:
            PluginModelDeclarationError: a plugin declares a model `internal.toml` declares too, or one whose table
                is not a valid model spec.
        """
        internal_backend = self.root.get(PipelexBackend.INTERNAL)
        if internal_backend is None:
            return False
        internal_file_path = backend_toml_path(backends_dir_path=backends_dir_path, backend_name=PipelexBackend.INTERNAL)
        merged_model_specs = dict(internal_backend.model_specs)
        for model_name, plugin_model in plugin_model_declarations.internal_models.items():
            if model_name == MODEL_SPEC_DEFAULTS_TABLE:
                msg = (
                    f"Plugin '{plugin_model.plugin}' declares an internal model named '{model_name}', which is the name of a backend "
                    "file's table of defaults, so it cannot name a model."
                )
                raise PluginModelDeclarationError(msg, plugin=plugin_model.plugin)
            if model_name in internal_backend.model_specs:
                msg = (
                    f"Plugin '{plugin_model.plugin}' declares the internal model '{model_name}', which '{internal_file_path}' declares too. "
                    "Remove it from that file, or run `pipelex update` to refresh the file from the kit: the plugin's declaration is the one "
                    "that ships with its engine."
                )
                raise PluginModelDeclarationError(msg, plugin=plugin_model.plugin)
            try:
                plugin_model_specs = self._build_backend_model_specs(
                    model_specs_dict={model_name: plugin_model.spec},
                    backend_name=PipelexBackend.INTERNAL,
                    backend_config_source=f"plugin '{plugin_model.plugin}'",
                    backend_listed_constraints=internal_backend.listed_constraints,
                    backend_valued_constraints=internal_backend.valued_constraints,
                )
            except InferenceBackendLibraryError as exc:
                msg = f"Plugin '{plugin_model.plugin}' declares the internal model '{model_name}' with a table that is not a valid model spec: {exc}"
                raise PluginModelDeclarationError(msg, plugin=plugin_model.plugin) from exc
            merged_model_specs.update(plugin_model_specs)
        self.root[PipelexBackend.INTERNAL] = internal_backend.model_copy(update={"model_specs": merged_model_specs})
        return True

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
