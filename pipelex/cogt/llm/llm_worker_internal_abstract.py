from typing import Optional

from typing_extensions import override

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.reporting.reporting_protocol import ReportingProtocol


class LLMWorkerInternalAbstract(LLMWorkerAbstract):
    def __init__(
        self,
        inference_model: InferenceModelSpec,
        structure_method: Optional[StructureMethod] = None,
        reporting_delegate: Optional[ReportingProtocol] = None,
    ):
        """
        Initialize the LLMWorker.

        Args:
            inference_model (InferenceModelSpec): The inference model to be used by the worker.
            structure_method (Optional[StructureMethod]): The structure method to be used by the worker.
            reporting_delegate (Optional[ReportingProtocol]): An optional report delegate for reporting unit jobs.
        """
        LLMWorkerAbstract.__init__(self, reporting_delegate=reporting_delegate)
        self.inference_model = inference_model
        self.structure_method = structure_method

    #########################################################
    # Instance methods
    #########################################################

    @property
    @override
    def desc(self) -> str:
        return f"LLM-Worker:{self.inference_model.tag}"

    @property
    @override
    def is_gen_object_supported(self) -> bool:
        return self.inference_model.is_gen_object_supported

    @override
    async def _before_job(
        self,
        llm_job: LLMJob,
    ):
        await super()._before_job(llm_job=llm_job)
        llm_job.llm_job_before_start(inference_model=self.inference_model)

    @override
    def _check_can_perform_job(self, llm_job: LLMJob):
        # This can be overridden by subclasses for specific checks
        self._check_vision_support(llm_job=llm_job)

    def _check_vision_support(self, llm_job: LLMJob):
        if llm_job.llm_prompt.user_images:
            if not self.inference_model.is_vision_supported:
                raise LLMCapabilityError(f"LLM Engine '{self.inference_model.tag}' does not support vision.")

            nb_images = len(llm_job.llm_prompt.user_images)
            max_prompt_images = self.inference_model.max_prompt_images or 5000
            if nb_images > max_prompt_images:
                raise LLMCapabilityError(f"LLM Engine '{self.inference_model.tag}' does not accept that many images: {nb_images}.")
