from typing import Any, Dict, List, Optional, Set

from pydantic import Field, RootModel, ValidationError
from typing_extensions import Self

from pipelex import log
from pipelex.cogt.exceptions import InferenceBackendCredentialsError, InferenceBackendLibraryError, InferenceModelSpecError
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.backend_factory import InferenceBackendBlueprint, InferenceBackendFactory
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_factory import InferenceModelSpecBlueprint, InferenceModelSpecFactory
from pipelex.cogt.model_backends.prompting_target import PromptingTarget
from pipelex.config import get_config
from pipelex.tools.misc.dict_utils import apply_to_strings_recursive
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.secrets.secrets_utils import UnknownVarPrefixError, VarNotFoundError, substitute_vars

InferenceBackendLibraryRoot = Dict[str, InferenceBackend]


class InferenceBackendLibrary(RootModel[InferenceBackendLibraryRoot]):
    root: InferenceBackendLibraryRoot = Field(default_factory=dict)

    def reset(self):
        self.root = {}

    @classmethod
    def make_empty(cls) -> Self:
        return cls(root={})

    def load(self):
        backends_library_path = get_config().cogt.inference_config.backends_library_path
        try:
            backends_dict = load_toml_from_path(path=backends_library_path)
        except (FileNotFoundError, InferenceBackendLibraryError) as exc:
            raise InferenceBackendLibraryError(f"Failed to load inference backend library from file '{backends_library_path}': {exc}") from exc
        for backend_name, backend_dict in backends_dict.items():
            # We'll split the read settings into standard fields and extra config
            standard_fields = InferenceBackendBlueprint.model_fields.keys()
            extra_config: Dict[str, Any] = {}
            inference_backend_blueprint_dict_raw = backend_dict.copy()
            if not inference_backend_blueprint_dict_raw.get("enabled", True):
                continue
            try:
                inference_backend_blueprint_dict = apply_to_strings_recursive(inference_backend_blueprint_dict_raw, substitute_vars)
            except (VarNotFoundError, UnknownVarPrefixError) as exc:
                raise InferenceBackendCredentialsError(f"Variable substitution failed in file '{backends_library_path}': {exc}") from exc

            for key in backend_dict.keys():
                if key not in standard_fields:
                    extra_config[key] = inference_backend_blueprint_dict.pop(key)
            backend_blueprint = InferenceBackendBlueprint.model_validate(inference_backend_blueprint_dict)
            # if not backend_blueprint.enabled:
            #     continue

            path_to_model_specs_toml = get_config().cogt.inference_config.model_specs_path(backend_name=backend_name)
            try:
                model_specs_dict_raw = load_toml_from_path(
                    path=path_to_model_specs_toml,
                )
                try:
                    model_specs_dict = apply_to_strings_recursive(model_specs_dict_raw, substitute_vars)
                except (VarNotFoundError, UnknownVarPrefixError) as exc:
                    raise InferenceModelSpecError(f"Variable substitution failed in file '{path_to_model_specs_toml}': {exc}") from exc
            except (FileNotFoundError, InferenceModelSpecError) as exc:
                raise InferenceBackendLibraryError(f"Failed to load inference model specs from file '{path_to_model_specs_toml}': {exc}") from exc
            default_sdk: Optional[str] = model_specs_dict.pop("default_sdk", None)
            default_prompting_target: Optional[PromptingTarget] = model_specs_dict.pop("default_prompting_target", None)
            backend_model_specs: Dict[str, InferenceModelSpec] = {}
            for model_spec_name, model_spec_dict in model_specs_dict.items():
                try:
                    model_spec_blueprint = InferenceModelSpecBlueprint.model_validate(model_spec_dict)
                    model_spec = InferenceModelSpecFactory.make_inference_model_spec(
                        backend_name=backend_name,
                        name=model_spec_name,
                        blueprint=model_spec_blueprint,
                        default_prompting_target=default_prompting_target,
                        fallback_sdk=default_sdk,
                    )
                    backend_model_specs[model_spec_name] = model_spec
                except (InferenceModelSpecError, ValidationError) as exc:
                    raise InferenceBackendLibraryError(
                        f"Failed to load inference model spec '{model_spec_name}' for backend '{backend_name}' "
                        f"from file '{path_to_model_specs_toml}': {exc}"
                    )
            backend = InferenceBackendFactory.make_inference_backend(
                name=backend_name,
                blueprint=backend_blueprint,
                extra_config=extra_config,
                model_specs=backend_model_specs,
            )
            self.root[backend_name] = backend
            log.debug(f"Loaded inference backend '{backend_name}'")

    def list_backend_names(self) -> List[str]:
        return list(self.root.keys())

    def list_all_model_names(self) -> List[str]:
        """List the names of all models in all backends."""
        all_model_names: Set[str] = set()
        for backend in self.root.values():
            all_model_names.update(backend.list_model_names())
        return sorted(all_model_names)

    def get_all_models_and_possible_backends(self) -> Dict[str, List[str]]:
        """Get a dictionary of all models and their possible backends."""
        all_models_and_possible_backends: Dict[str, List[str]] = {}
        for backend in self.root.values():
            for model_name in backend.list_model_names():
                if model_name not in all_models_and_possible_backends:
                    all_models_and_possible_backends[model_name] = []
                all_models_and_possible_backends[model_name].append(backend.name)
        return all_models_and_possible_backends

    def get_inference_backend(self, backend_name: str) -> Optional[InferenceBackend]:
        """Get a backend by name."""
        backend = self.root.get(backend_name)
        return backend
