from typing import Dict

from pydantic import Field, RootModel
from typing_extensions import override

from pipelex import log, pretty_print
from pipelex.cogt.inference.inference_backend import InferenceBackend
from pipelex.cogt.inference.inference_backend_factory import InferenceBackendBlueprint, InferenceBackendFactory
from pipelex.cogt.inference.inference_backend_provider import InferenceBackendProviderAbstract
from pipelex.config import get_config
from pipelex.tools.misc.toml_utils import load_toml_from_path

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
        path_to_backends_toml = get_config().pipelex.inference_backends_config_path
        backends_dict = load_toml_from_path(
            path=path_to_backends_toml,
            is_env_var_substitution_enabled=True,
        )
        for backend_name, backend_dict in backends_dict.items():
            backend_blueprint = InferenceBackendBlueprint.model_validate(backend_dict)
            if not backend_blueprint.enabled:
                continue
            backend = InferenceBackendFactory.make_inference_backend(inference_backend_blueprint=backend_blueprint)
            self.root[backend_name] = backend
            log.debug(f"Loaded inference backend '{backend_name}'")

        # pretty_print(self.root, title="Inference Backends")
