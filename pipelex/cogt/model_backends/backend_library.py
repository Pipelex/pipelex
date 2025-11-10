from functools import partial
from typing import TYPE_CHECKING, Any, cast

from pydantic import Field, RootModel, ValidationError

from pipelex.cogt.exceptions import (
    InferenceBackendCredentialsError,
    InferenceBackendCredentialsErrorType,
    InferenceBackendLibraryError,
    InferenceBackendLibraryNotFoundError,
    InferenceBackendLibraryValidationError,
    InferenceModelSpecError,
)
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.backend_factory import (
    InferenceBackendBlueprint,
    InferenceBackendFactory,
)
from pipelex.cogt.model_backends.model_spec_factory import (
    InferenceModelSpecBlueprint,
    InferenceModelSpecFactory,
)
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.environment import get_optional_env
from pipelex.system.runtime import runtime_manager
from pipelex.tools.misc.dict_utils import (
    apply_to_strings_recursive,
    extract_vars_from_strings_recursive,
)
from pipelex.tools.misc.placeholder import value_is_placeholder
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.secrets.secrets_utils import (
    UnknownVarPrefixError,
    VarFallbackPatternError,
    VarNotFoundError,
    substitute_vars,
)
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.types import Self

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec

InferenceBackendLibraryRoot = dict[str, InferenceBackend]


class BackendCredentialStatus(ConfigModel):
    """Status of a single credential variable."""

    var_name: str
    is_set: bool
    is_placeholder: bool  # True if value exists but is a placeholder like "${VAR}"


class BackendCredentialsReport(ConfigModel):
    """Report of credential status for a backend."""

    backend_name: str
    required_vars: list[str]
    missing_vars: list[str]
    placeholder_vars: list[str]
    all_credentials_valid: bool


class CredentialsValidationReport(ConfigModel):
    """Complete report of credentials validation across all backends."""

    backend_reports: dict[str, BackendCredentialsReport]
    all_backends_valid: bool


class InferenceBackendLibrary(RootModel[InferenceBackendLibraryRoot]):
    root: InferenceBackendLibraryRoot = Field(default_factory=dict)

    def reset(self):
        self.root = {}

    @classmethod
    def make_empty(cls) -> Self:
        return cls(root={})

    def load(self, secrets_provider: SecretsProviderAbstract, backends_library_path: str, backends_dir_path: str, include_disabled: bool = False):
        try:
            backends_dict = load_toml_from_path(path=backends_library_path)
        except FileNotFoundError as file_not_found_exc:
            msg = f"Could not find inference backend library at '{backends_library_path}': {file_not_found_exc}"
            raise InferenceBackendLibraryNotFoundError(msg) from file_not_found_exc
        except ValidationError as exc:
            valiation_error_msg = format_pydantic_validation_error(exc)
            msg = f"Invalid inference backend library configuration in '{backends_library_path}': {valiation_error_msg}"
            raise InferenceBackendLibraryValidationError(msg) from exc

        # Create a partial function with the secrets provider bound
        substitute_vars_with_provider = partial(substitute_vars, secrets_provider=secrets_provider)

        for backend_name, backend_dict in backends_dict.items():
            # We'll split the read settings into standard fields and extra config
            standard_fields = InferenceBackendBlueprint.model_fields.keys()
            extra_config: dict[str, Any] = {}
            inference_backend_blueprint_dict_raw = backend_dict.copy()
            enabled = inference_backend_blueprint_dict_raw.get("enabled", True)
            if not enabled and not include_disabled:
                continue
            if runtime_manager.is_ci_testing and backend_name == "vertexai":
                continue
            try:
                inference_backend_blueprint_dict = apply_to_strings_recursive(inference_backend_blueprint_dict_raw, substitute_vars_with_provider)
            except VarFallbackPatternError as var_fallback_pattern_exc:
                msg = f"Variable substitution failed due to a pattern error in file '{backends_library_path}':\n{var_fallback_pattern_exc}"
                key_name = "unknown"
                raise InferenceBackendCredentialsError(
                    error_type=InferenceBackendCredentialsErrorType.VAR_FALLBACK_PATTERN,
                    backend_name=backend_name,
                    message=msg,
                    key_name=key_name,
                ) from var_fallback_pattern_exc
            except VarNotFoundError as var_not_found_exc:
                msg = (
                    f"Variable substitution failed due to a 'variable not found' error in file '{backends_library_path}':\n"
                    f"Backend name: '{backend_name}', Variable name: '{var_not_found_exc.var_name}'\n"
                    f"{var_not_found_exc}\nRun mode: '{runtime_manager.run_mode}'"
                )
                raise InferenceBackendCredentialsError(
                    error_type=InferenceBackendCredentialsErrorType.VAR_NOT_FOUND,
                    backend_name=backend_name,
                    message=msg,
                    key_name=var_not_found_exc.var_name,
                ) from var_not_found_exc
            except UnknownVarPrefixError as unknown_var_prefix_exc:
                raise InferenceBackendCredentialsError(
                    error_type=InferenceBackendCredentialsErrorType.UNKNOWN_VAR_PREFIX,
                    backend_name=backend_name,
                    message=(
                        f"Variable substitution failed due to an unknown variable prefix error "
                        f"in file '{backends_library_path}':\n{unknown_var_prefix_exc}"
                    ),
                    key_name=unknown_var_prefix_exc.var_name,
                ) from unknown_var_prefix_exc

            for key in backend_dict:
                if key not in standard_fields:
                    extra_config[key] = inference_backend_blueprint_dict.pop(key)
            backend_blueprint = InferenceBackendBlueprint.model_validate(inference_backend_blueprint_dict)

            path_to_model_specs_toml = f"{backends_dir_path}/{backend_name}.toml"
            try:
                model_specs_dict_raw = load_toml_from_path(path=path_to_model_specs_toml)
                try:
                    model_specs_dict = apply_to_strings_recursive(model_specs_dict_raw, substitute_vars_with_provider)
                except (VarNotFoundError, UnknownVarPrefixError) as exc:
                    msg = f"Variable substitution failed in file '{path_to_model_specs_toml}': {exc}"
                    raise InferenceModelSpecError(msg) from exc
            except (FileNotFoundError, InferenceModelSpecError) as exc:
                msg = f"Failed to load inference model specs from file '{path_to_model_specs_toml}': {exc}"
                raise InferenceBackendLibraryError(msg) from exc
            defaults_dict: dict[str, Any] = model_specs_dict.pop("defaults", {})
            backend_model_specs: dict[str, InferenceModelSpec] = {}
            for model_spec_name, value in model_specs_dict.items():
                if not isinstance(value, dict):
                    msg = f"Model spec '{model_spec_name}' for backend '{backend_name}' at path '{path_to_model_specs_toml}' is not a dictionary"
                    raise InferenceModelSpecError(msg)
                model_spec_dict: dict[str, Any] = cast("dict[str, Any]", value)
                try:
                    # Start from the defaults
                    model_spec_blueprint_dict = defaults_dict.copy()
                    # Override with the attributes from the model spec dict
                    model_spec_blueprint_dict.update(model_spec_dict)
                    model_spec_blueprint = InferenceModelSpecBlueprint.model_validate(model_spec_blueprint_dict)
                    model_spec = InferenceModelSpecFactory.make_inference_model_spec(
                        backend_name=backend_name,
                        name=model_spec_name,
                        blueprint=model_spec_blueprint,
                    )
                    backend_model_specs[model_spec_name] = model_spec
                except (InferenceModelSpecError, ValidationError) as exc:
                    msg = (
                        f"Failed to load inference model spec '{model_spec_name}' for backend '{backend_name}' from file '{path_to_model_specs_toml}'"
                    )
                    raise InferenceBackendLibraryError(msg) from exc
            backend = InferenceBackendFactory.make_inference_backend(
                name=backend_name,
                blueprint=backend_blueprint,
                extra_config=extra_config,
                model_specs=backend_model_specs,
            )
            self.root[backend_name] = backend

    def check_backend_credentials(self, path: str, include_disabled: bool = False) -> CredentialsValidationReport:
        """Check if required environment variables are set for enabled backends.

        This method loads backend configurations and extracts variable placeholders
        without performing actual substitution or loading model specs.

        Args:
            path: Path to the backend library TOML file
            include_disabled: If True, check disabled backends too

        Returns:
            CredentialsValidationReport with detailed status per backend

        """
        try:
            backends_dict = load_toml_from_path(path=path)
        except FileNotFoundError as file_not_found_exc:
            msg = f"Could not find inference backend library at '{path}': {file_not_found_exc}"
            raise InferenceBackendLibraryNotFoundError(msg) from file_not_found_exc

        backend_reports: dict[str, BackendCredentialsReport] = {}
        all_backends_valid = True

        for backend_name, backend_dict in backends_dict.items():
            enabled = backend_dict.get("enabled", True)
            if not enabled and not include_disabled:
                continue

            # Skip internal backend
            if backend_name == "internal":
                continue

            # Skip vertexai in CI testing
            if runtime_manager.is_ci_testing and backend_name == "vertexai":
                continue

            # Extract all variable placeholders from the backend config
            required_vars_set = extract_vars_from_strings_recursive(backend_dict)
            required_vars = sorted(required_vars_set)

            # Check status of each variable
            missing_vars: list[str] = []
            placeholder_vars: list[str] = []

            for var_name in required_vars:
                var_value = get_optional_env(var_name)
                if var_value is None:
                    missing_vars.append(var_name)
                elif value_is_placeholder(var_value):
                    placeholder_vars.append(var_name)

            # Determine if all credentials are valid for this backend
            backend_valid = len(missing_vars) == 0 and len(placeholder_vars) == 0

            # Create report for this backend
            backend_report = BackendCredentialsReport(
                backend_name=backend_name,
                required_vars=required_vars,
                missing_vars=missing_vars,
                placeholder_vars=placeholder_vars,
                all_credentials_valid=backend_valid,
            )
            backend_reports[backend_name] = backend_report

            if not backend_valid:
                all_backends_valid = False

        return CredentialsValidationReport(
            backend_reports=backend_reports,
            all_backends_valid=all_backends_valid,
        )

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
