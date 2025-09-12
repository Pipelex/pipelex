from typing import Dict, List, Optional

from pydantic import Field, RootModel, ValidationError
from typing_extensions import override

from pipelex import log, pretty_print
from pipelex.cogt.inference.exceptions import InferenceBackendLibraryError, InferenceModelSpecError
from pipelex.cogt.inference.inference_backend import InferenceBackend
from pipelex.cogt.inference.inference_backend_factory import InferenceBackendBlueprint, InferenceBackendFactory
from pipelex.cogt.inference.inference_backend_provider import InferenceBackendProviderAbstract
from pipelex.cogt.inference.inference_model_spec import InferenceModelSpec
from pipelex.cogt.inference.inference_model_spec_factory import InferenceModelSpecBlueprint, InferenceModelSpecFactory
from pipelex.config import get_config
from pipelex.tools.misc.toml_utils import TOMLValidationError, load_toml_from_path

InferenceBackendLibraryRoot = Dict[str, InferenceBackend]


class InferenceBackendLibrary(RootModel[InferenceBackendLibraryRoot], InferenceBackendProviderAbstract):
    root: InferenceBackendLibraryRoot = Field(default_factory=dict)

    @override
    def setup(self):
        pass

    @override
    def teardown(self):
        self.root = {}

    @override
    def reset(self):
        self.teardown()
        self.setup()

    @classmethod
    def make_empty(cls):
        return cls(root={})

    @override
    def load_backends(self):
        inference_config_path = get_config().pipelex.inference_config_path
        backends_toml_path = f"{inference_config_path}/backends.toml"
        try:
            backends_dict = load_toml_from_path(
                path=backends_toml_path,
                is_env_var_substitution_enabled=True,
            )
        except (FileNotFoundError, TOMLValidationError) as exc:
            raise InferenceBackendLibraryError(f"Failed to load inference backend library from file '{backends_toml_path}': {exc}") from exc
        for backend_name, backend_dict in backends_dict.items():
            backend_blueprint = InferenceBackendBlueprint.model_validate(backend_dict)
            if not backend_blueprint.enabled:
                continue
            path_to_model_specs_toml = f"{inference_config_path}/backends/{backend_name}.toml"
            try:
                model_specs_dict = load_toml_from_path(
                    path=path_to_model_specs_toml,
                    is_env_var_substitution_enabled=True,
                )
            except (FileNotFoundError, TOMLValidationError) as exc:
                raise InferenceBackendLibraryError(f"Failed to load inference model specs from file '{path_to_model_specs_toml}': {exc}") from exc
            default_sdk: Optional[str] = model_specs_dict.pop("default_sdk", None)
            backend_model_specs: List[InferenceModelSpec] = []
            for model_spec_name, model_spec_dict in model_specs_dict.items():
                try:
                    model_spec_blueprint = InferenceModelSpecBlueprint.model_validate(model_spec_dict)
                    model_spec = InferenceModelSpecFactory.make_inference_model_spec(
                        blueprint=model_spec_blueprint,
                        default_sdk=default_sdk,
                    )
                    backend_model_specs.append(model_spec)
                except (InferenceModelSpecError, ValidationError) as exc:
                    raise InferenceBackendLibraryError(
                        f"Failed to load inference model spec '{model_spec_name}' for backend '{backend_name}' "
                        f"from file '{path_to_model_specs_toml}': {exc}"
                    )
            backend = InferenceBackendFactory.make_inference_backend(inference_backend_blueprint=backend_blueprint, model_specs=backend_model_specs)
            self.root[backend_name] = backend
            log.debug(f"Loaded inference backend '{backend_name}'")
