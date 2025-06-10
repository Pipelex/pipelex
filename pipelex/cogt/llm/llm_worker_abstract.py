from abc import ABC, abstractmethod
from typing import Optional, Type

from instructor.exceptions import InstructorRetryException
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMCapabilityError, LLMCompletionError
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.pipeline.job_metadata import UnitJobId
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class LLMWorkerAbstract(InferenceWorkerAbstract, ABC):
    def __init__(
        self,
        llm_engine: LLMEngine,
        structure_method: Optional[StructureMethod],
        reporting_delegate: Optional[ReportingProtocol] = None,
    ):
        """
        Initialize the LLMWorker.

        Args:
            llm_engine (LLMEngine): The LLM engine to be used by the worker.
            structure_method (Optional[StructureMethod]): The structure method to be used by the worker.
            reporting_delegate (Optional[ReportingProtocol]): An optional report delegate for reporting unit jobs.
        """
        InferenceWorkerAbstract.__init__(self, reporting_delegate=reporting_delegate)
        self.llm_engine = llm_engine
        self.structure_method = structure_method

    #########################################################
    # Instance methods
    #########################################################

    @property
    @override
    def desc(self) -> str:
        return f"LLM Worker using:\n{self.llm_engine.desc}"

    def _check_can_perform_job(self, llm_job: LLMJob):
        # This can be overridden by subclasses for specific checks
        self._check_vision_support(llm_job=llm_job)

    def _check_vision_support(self, llm_job: LLMJob):
        if llm_job.llm_prompt.user_images:
            if not self.llm_engine.llm_model.is_vision_supported:
                raise LLMCapabilityError(f"LLM Engine '{self.llm_engine.tag}' does not support vision.")

            nb_images = len(llm_job.llm_prompt.user_images)
            max_prompt_images = self.llm_engine.llm_model.max_prompt_images or 5000
            if nb_images > max_prompt_images:
                raise LLMCapabilityError(f"LLM Engine '{self.llm_engine.tag}' does not accept that many images: {nb_images}.")

    async def gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        log.debug("LLM Worker gen_text")
        log.verbose(f"\n{self.llm_engine.desc}")
        log.verbose(llm_job.params_desc)

        # Verify that the job is valid
        llm_job.validate_before_execution()

        # Verify feasibility
        self._check_can_perform_job(llm_job=llm_job)

        # TODO: Fix printing prompts that contain image bytes
        # log.verbose(llm_job.llm_prompt.desc, title="llm_prompt")

        # metadata
        llm_job.job_metadata.unit_job_id = UnitJobId.LLM_GEN_TEXT

        # Prepare job
        llm_job.llm_job_before_start(llm_engine=self.llm_engine)

        result = await self._gen_text(llm_job=llm_job)

        # Cleanup result (Instructor adds the client's response as a _raw_response attribute, we don't want to pass it along)
        if hasattr(result, "_raw_response"):
            delattr(result, "_raw_response")

        # Report job
        llm_job.llm_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=llm_job)

        return result

    @abstractmethod
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        pass

    async def gen_object(
        self,
        llm_job: LLMJob,
        schema: Type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        log.debug("LLM Worker gen_object")
        log.verbose(f"\n{self.llm_engine.desc}")
        log.verbose(llm_job.params_desc)

        # Verify that the job is valid
        llm_job.validate_before_execution()

        # Verify feasibility
        if not self.llm_engine.is_gen_object_supported:
            raise LLMCapabilityError(f"LLM Engine '{self.llm_engine.tag}' does not support object generation.")
        self._check_can_perform_job(llm_job=llm_job)

        # TODO: Fix printing prompts that contain image bytes
        # log.verbose(llm_job.llm_prompt.desc, title="llm_prompt")

        # metadata
        llm_job.job_metadata.unit_job_id = UnitJobId.LLM_GEN_OBJECT

        # Prepare job
        llm_job.llm_job_before_start(llm_engine=self.llm_engine)

        # Execute job
        try:
            result = await self._gen_object(llm_job=llm_job, schema=schema)
        except InstructorRetryException as exc:
            raise LLMCompletionError(
                f"""Instructor failed to generate object: {schema} after retry with llm '{self.llm_engine.tag}'
                Reason: {exc}
                LLMPrompt: {llm_job.llm_prompt.desc}"""
            ) from exc

        # Cleanup result
        if hasattr(result, "_raw_response"):
            delattr(result, "_raw_response")

        # Report job
        llm_job.llm_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=llm_job)

        return result

    @abstractmethod
    async def _gen_object(
        self,
        llm_job: LLMJob,
        schema: Type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        pass
