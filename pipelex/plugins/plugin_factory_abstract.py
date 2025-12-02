from abc import ABC, abstractmethod

from pipelex.cogt.llm.llm_job import LLMJob


class PluginFactoryAbstract(ABC):
    @abstractmethod
    def make_extra_headers(self, llm_job: LLMJob, output_desc: str) -> dict[str, str]:
        pass
