from abc import ABC, abstractmethod
from typing import Dict

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_deck.llm_deck import LLMDeck


class ModelsManagerAbstract(ABC):
    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def get_all_inference_models(self) -> Dict[str, InferenceModelSpec]:
        pass

    @abstractmethod
    def get_inference_model(self, llm_handle: str) -> InferenceModelSpec:
        pass

    @abstractmethod
    def get_llm_deck(self) -> LLMDeck:
        pass

    @abstractmethod
    def get_required_inference_backend(self, backend_name: str) -> InferenceBackend:
        pass
