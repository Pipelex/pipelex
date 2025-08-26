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

    #########################################################
    # Instance methods
    #########################################################

    @property
    @override
    def desc(self) -> str:
        return "LLM Worker • if you're using an external plugin, override this method to describe your llm worker"

    @property
    @abstractmethod
    def is_gen_object_supported(self) -> bool:
        return False

    async def _before_job(
        self,
        llm_job: LLMJob,
    ):
        # Verify that the job is valid
        llm_job.validate_before_execution()

        # Verify feasibility
        self._check_can_perform_job(llm_job=llm_job)

    async def _after_job(
        self,
        llm_job: LLMJob,
    ):
        # Report job
        llm_job.llm_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=llm_job)

    def _check_can_perform_job(self, llm_job: LLMJob):
        # This can be overridden by subclasses for specific checks
        pass

    async def gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        log.debug("LLM Worker gen_text")
        log.verbose(llm_job.params_desc)
        log.verbose(llm_job.llm_prompt.desc(), title="llm_prompt")

        # metadata
        llm_job.job_metadata.unit_job_id = UnitJobId.LLM_GEN_TEXT

        await self._before_job(llm_job=llm_job)

        result = await self._gen_text(llm_job=llm_job)

        await self._after_job(llm_job=llm_job)

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
        log.debug(f"LLM Worker gen_object using {self.desc}")
        log.verbose(llm_job.params_desc)
        log.verbose(llm_job.llm_prompt.desc(), title="llm_prompt")

        # metadata
        llm_job.job_metadata.unit_job_id = UnitJobId.LLM_GEN_OBJECT

        await self._before_job(llm_job=llm_job)

        # Execute job
        result = await self._gen_object(llm_job=llm_job, schema=schema)

        # Cleanup result
        if hasattr(result, "_raw_response"):
            delattr(result, "_raw_response")

        await self._after_job(llm_job=llm_job)

        return result

    @abstractmethod
    async def _gen_object(
        self,
        llm_job: LLMJob,
        schema: Type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        pass
