from typing import Dict, List, Optional, Set

from pydantic import Field, RootModel, ValidationError
from typing_extensions import Self

from pipelex import log
from pipelex.cogt.exceptions import InferenceBackendLibraryError, InferenceModelSpecError
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.backend_factory import InferenceBackendBlueprint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_factory import InferenceModelSpecBlueprint, InferenceModelSpecFactory
from pipelex.config import get_config
from pipelex.tools.misc.toml_utils import TOMLValidationError, load_toml_from_path

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
            backends_dict = load_toml_from_path(
                path=backends_library_path,
                is_env_var_substitution_enabled=True,
            )
        except (FileNotFoundError, TOMLValidationError) as exc:
            raise InferenceBackendLibraryError(f"Failed to load inference backend library from file '{backends_library_path}': {exc}") from exc
        for backend_name, backend_dict in backends_dict.items():
            backend_blueprint = InferenceBackendBlueprint.model_validate(backend_dict)
            if not backend_blueprint.enabled:
                continue
            path_to_model_specs_toml = get_config().cogt.inference_config.model_specs_path(backend_name=backend_name)
            try:
                model_specs_dict = load_toml_from_path(
                    path=path_to_model_specs_toml,
                    is_env_var_substitution_enabled=True,
                )
            except (FileNotFoundError, TOMLValidationError) as exc:
                raise InferenceBackendLibraryError(f"Failed to load inference model specs from file '{path_to_model_specs_toml}': {exc}") from exc
            default_sdk: Optional[str] = model_specs_dict.pop("default_sdk", None)
            backend_model_specs: Dict[str, InferenceModelSpec] = {}
            for model_spec_name, model_spec_dict in model_specs_dict.items():
                try:
                    model_spec_blueprint = InferenceModelSpecBlueprint.model_validate(model_spec_dict)
                    model_spec = InferenceModelSpecFactory.make_inference_model_spec(
                        backend_name=backend_name,
                        name=model_spec_name,
                        blueprint=model_spec_blueprint,
                        fallback_sdk=default_sdk,
                        endpoint=backend_blueprint.endpoint,
                    )
                    backend_model_specs[model_spec_name] = model_spec
                except (InferenceModelSpecError, ValidationError) as exc:
                    raise InferenceBackendLibraryError(
                        f"Failed to load inference model spec '{model_spec_name}' for backend '{backend_name}' "
                        f"from file '{path_to_model_specs_toml}': {exc}"
                    )
            backend = InferenceBackend(endpoint=backend_blueprint.endpoint, api_key=backend_blueprint.api_key, model_specs=backend_model_specs)
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

    def get_required_backend(self, backend_name: str) -> InferenceBackend:
        """Get a backend by name."""
        backend = self.root.get(backend_name)
        if not backend:
            raise InferenceBackendLibraryError(f"Backend '{backend_name}' not found in inference backend library")
        return backend
