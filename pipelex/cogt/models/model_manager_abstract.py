from abc import ABC, abstractmethod

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


class ModelManagerAbstract(ABC):
    @abstractmethod
    def validate_model_deck(self):
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def setup(self, secrets_provider: SecretsProviderAbstract) -> None:
        pass

    @abstractmethod
    def get_inference_model(self, model_handle: str) -> InferenceModelSpec:
        pass

    @abstractmethod
    def get_model_deck(self) -> ModelDeck:
        pass

    @abstractmethod
    def get_required_inference_backend(self, backend_name: str) -> InferenceBackend:
        pass
