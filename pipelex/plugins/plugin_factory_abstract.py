from abc import ABC, abstractmethod
from typing import Any

from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class PluginFactoryAbstract(ABC):
    @abstractmethod
    def make_extras(self, inference_model: InferenceModelSpec, llm_job: LLMJob, output_desc: str) -> tuple[dict[str, str], dict[str, Any]]:
        pass
