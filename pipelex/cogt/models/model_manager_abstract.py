from abc import ABC, abstractmethod

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.models.model_deck import ModelDeck


class ModelManagerAbstract(ABC):
    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def setup(self) -> None:
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
