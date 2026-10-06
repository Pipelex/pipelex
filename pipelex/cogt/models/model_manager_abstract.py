from abc import ABC, abstractmethod

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.plugins.plugin_model_declarations import PluginModelDeclarations
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


class ModelManagerAbstract(ABC):
    @abstractmethod
    def validate_model_deck(self):
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def setup(
        self,
        *,
        secrets_provider: SecretsProviderAbstract,
        plugin_model_declarations: PluginModelDeclarations,
        needs_inference: bool = True,
    ) -> None:
        """Load the inference backends, the routing profile and the model deck, and build the deck.

        With ``needs_inference=False`` an implementation knows every enabled backend's models, as a boot
        that needs inference does, but resolves no credential; ``get_required_inference_backend`` then
        refuses every backend whose credentials it left unresolved.

        ``plugin_model_declarations`` carries the internal models and the model deck defaults the registered plugins
        declared (``PluginRegistrar.make_model_declarations``): an implementation merges the models into the internal
        backend and the defaults beneath the deck files. Required, so no caller can forget the plugins' engines.
        """

    @abstractmethod
    def get_inference_model(self, model_handle: str, *, model_type: ModelType) -> InferenceModelSpec:
        pass

    @abstractmethod
    def get_model_deck(self) -> ModelDeck:
        pass

    @abstractmethod
    def get_required_inference_backend(self, backend_name: str) -> InferenceBackend:
        """The backend a worker calls, and the one way to a backend's credentials.

        Raises ``InferenceBackendCredentialsError`` for a backend whose credentials this process left
        unresolved, because it booted without inference.
        """
