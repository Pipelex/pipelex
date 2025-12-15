from abc import ABC, abstractmethod
from typing import Any

from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class PluginFactoryAbstract(ABC):
    @abstractmethod
    def make_extras(
        self, inference_model: InferenceModelSpec, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        pass
