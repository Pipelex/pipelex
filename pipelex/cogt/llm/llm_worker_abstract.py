from abc import ABC, abstractmethod
from typing import Optional, Type

from typing_extensions import override

from pipelex import log
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.pipeline.job_metadata import UnitJobId
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class LLMWorkerAbstract(InferenceWorkerAbstract, ABC):
    def __init__(
        self,
        reporting_delegate: Optional[ReportingProtocol] = None,
    ):
        """
        Initialize the LLMWorker.

        Args:
            reporting_delegate (Optional[ReportingProtocol]): An optional report delegate for reporting unit jobs.
        """
        InferenceWorkerAbstract.__init__(self, reporting_delegate=reporting_delegate)

    @property
    @override
    def desc(self) -> str:
        return "LLM Worker • if you're using an external plugin, override this method to describe your llm worker"

    #########################################################
    # Instance methods
    #########################################################

    def _check_can_perform_job(self, llm_job: LLMJob):
        # This can be overridden by subclasses for specific checks
        pass

    async def gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        log.debug("LLM Worker gen_text")
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
        # TODO: prep job should exits for non-internal llm workers
        # llm_job.llm_job_before_start(llm_engine=self.llm_engine)

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
        log.verbose(llm_job.params_desc)

        # Verify that the job is valid
        llm_job.validate_before_execution()

        # Verify feasibility
        self._check_can_perform_job(llm_job=llm_job)

        # TODO: Fix printing prompts that contain image bytes
        # log.verbose(llm_job.llm_prompt.desc, title="llm_prompt")

        # metadata
        llm_job.job_metadata.unit_job_id = UnitJobId.LLM_GEN_OBJECT

        # Execute job
        result = await self._gen_object(llm_job=llm_job, schema=schema)

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
