# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC, abstractmethod
from enum import StrEnum
from functools import wraps
from typing import Any, Awaitable, Callable, Optional, Type, TypeVar, cast

from instructor.exceptions import InstructorRetryException
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMCapabilityError, LLMWorkerError
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.inference.inference_reporter_abstract import InferenceReporterAbstract
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.job_metadata import UnitJobId
from pipelex.tools.misc.model_helpers import BaseModelType

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


class LLMWorkerJobFuncName(StrEnum):
    GEN_TEXT = "gen_text"
    GEN_OBJECT = "gen_object"


def llm_job_func(func: F) -> F:
    """
    A decorator for asynchronous LLM job functions.

    This decorator wraps an asynchronous function that performs an LLM job,
    adding logging, integrity checks, feasibility checks, job preparation,
    execution timing, and reporting.

    Args:
        func (F): The asynchronous function to be decorated.

    Returns:
        F: The wrapped asynchronous function.
    """

    @wraps(func)
    async def wrapper(
        self: "LLMWorkerAbstract",
        llm_job: LLMJob,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        func_name = LLMWorkerJobFuncName(func.__name__)
        log.debug(f"LLM Working async job function: '{func_name}'")
        log.verbose(f"\n{self.llm_engine.desc}")
        log.verbose(llm_job.params_desc)

        # Verify that the job is valid
        llm_job.validate_before_execution()

        # Verify feasibility
        self.check_can_perform_job(llm_job=llm_job, func_name=func_name)

        # TODO: Fix printing prompts that contain image bytes
        # log.verbose(llm_job.llm_prompt.desc, title="llm_prompt")

        # metadata
        llm_job.job_metadata.unit_job_id = self.unit_job_id(func_name=func_name)

        # Prepare job
        llm_job.llm_job_before_start(llm_engine=self.llm_engine)

        # Execute job
        try:
            result = await func(self, llm_job, *args, **kwargs)
        except InstructorRetryException as exc:
            raise LLMWorkerError(
                f"LLM Worker error: Instructor failed after retry with llm '{self.llm_engine.tag}': {exc}\nLLMPrompt: {llm_job.llm_prompt.desc}"
            ) from exc

        # Cleanup result
        if hasattr(result, "_raw_response"):
            delattr(result, "_raw_response")

        # Report job
        llm_job.llm_job_after_complete()
        if self.report_delegate:
            self.report_delegate.report_inference_job(inference_job=llm_job)

        return result

    return cast(F, wrapper)


class LLMWorkerAbstract(InferenceReporterAbstract, ABC):
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
        InferenceReporterAbstract.__init__(self, report_delegate=report_delegate)
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
        schema: Type[BaseModelType],
    ) -> BaseModelType:
        pass
