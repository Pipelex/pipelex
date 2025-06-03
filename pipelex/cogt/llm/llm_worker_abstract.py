from abc import ABC, abstractmethod
from typing import Optional, Type

from typing_extensions import override

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.pipeline.job_metadata import UnitJobId
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from pipelex.types import StrEnum


class LLMWorkerJobFuncName(StrEnum):
    GEN_TEXT = "gen_text"
    GEN_OBJECT = "gen_object"


class LLMWorkerAbstract(InferenceWorkerAbstract, ABC):
    def __init__(
        self,
        llm_engine: LLMEngine,
        structure_method: Optional[StructureMethod],
        report_delegate: Optional[InferenceReportDelegate] = None,
    ):
        """
        Initialize the LLMWorker.

        Args:
            llm_engine (LLMEngine): The LLM engine to be used by the worker.
            structure_method (Optional[StructureMethod]): The structure method to be used by the worker.
            report_delegate (Optional[InferenceReportDelegate]): An optional report delegate for reporting unit jobs.
        """
        InferenceWorkerAbstract.__init__(self, report_delegate=report_delegate)
        self.llm_engine = llm_engine
        self.structure_method = structure_method

    #########################################################
    # Instance methods
    #########################################################

    @property
    @override
    def desc(self) -> str:
        return f"LLM Worker using:\n{self.llm_engine.desc}"

    def unit_job_id(self, func_name: LLMWorkerJobFuncName) -> UnitJobId:
        match func_name:
            case LLMWorkerJobFuncName.GEN_TEXT:
                return UnitJobId.LLM_GEN_TEXT
            case LLMWorkerJobFuncName.GEN_OBJECT:
                return UnitJobId.LLM_GEN_OBJECT

    def check_can_perform_job(self, llm_job: LLMJob, func_name: LLMWorkerJobFuncName):
        match func_name:
            case LLMWorkerJobFuncName.GEN_TEXT:
                pass
            case LLMWorkerJobFuncName.GEN_OBJECT:
                if not self.llm_engine.is_gen_object_supported:
                    raise LLMCapabilityError(f"LLM Engine '{self.llm_engine.tag}' does not support object generation.")

        if llm_job.llm_prompt.user_images:
            if not self.llm_engine.llm_model.is_vision_supported:
                raise LLMCapabilityError(f"LLM Engine '{self.llm_engine.tag}' does not support vision.")

            nb_images = len(llm_job.llm_prompt.user_images)
            max_prompt_images = self.llm_engine.llm_model.max_prompt_images or 5000
            if nb_images > max_prompt_images:
                raise LLMCapabilityError(f"LLM Engine '{self.llm_engine.tag}' does not accept that many images: {nb_images}.")

    @abstractmethod
    async def gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        pass

    @abstractmethod
    async def gen_object(
        self,
        llm_job: LLMJob,
        schema: Type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        pass
