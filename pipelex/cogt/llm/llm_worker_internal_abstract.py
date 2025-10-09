from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_utils import dump_prompt, dump_response_from_text_gen
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.config import get_config
from pipelex.reporting.reporting_protocol import ReportingProtocol


class LLMWorkerInternalAbstract(LLMWorkerAbstract):
    def __init__(
        self,
        inference_model: InferenceModelSpec,
        structure_method: StructureMethod | None = None,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        """Initialize the LLMWorker.

        Args:
            inference_model (InferenceModelSpec): The inference model to be used by the worker.
            structure_method (StructureMethod | None): The structure method to be used by the worker.
            reporting_delegate (ReportingProtocol | None): An optional report delegate for reporting unit jobs.

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
        return f"LLM-Worker: {self.inference_model.tag}"

    @property
    @override
    def is_gen_object_supported(self) -> bool:
        return self.inference_model.is_gen_object_supported

    @override
    async def _before_job(
        self,
        llm_job: LLMJob,
    ):
        log.info(f"LLM Worker: {self.desc} --------------------------------")
        await super()._before_job(llm_job=llm_job)
        llm_job.llm_job_before_start(inference_model=self.inference_model)
        if get_config().cogt.llm_config.is_dump_text_prompts_enabled:
            dump_prompt(llm_prompt=llm_job.llm_prompt)

    @override
    async def _after_job(
        self,
        llm_job: LLMJob,
        result: str,
    ):
        if get_config().cogt.llm_config.is_dump_response_text_enabled:
            dump_response_from_text_gen(response=result)
        await super()._after_job(llm_job=llm_job, result=result)

    @override
    def _check_can_perform_job(self, llm_job: LLMJob):
        # This can be overridden by subclasses for specific checks
        self._check_vision_support(llm_job=llm_job)

    def _check_vision_support(self, llm_job: LLMJob):
        if llm_job.llm_prompt.user_images:
            if not self.inference_model.is_vision_supported:
                msg = f"LLM Engine '{self.inference_model.tag}' does not support vision."
                raise LLMCapabilityError(msg)

            nb_images = len(llm_job.llm_prompt.user_images)
            max_prompt_images = self.inference_model.max_prompt_images or 5000
            if nb_images > max_prompt_images:
                msg = f"LLM Engine '{self.inference_model.tag}' does not accept that many images: {nb_images}."
                raise LLMCapabilityError(msg)
