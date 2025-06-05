from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar, cast

from instructor.exceptions import InstructorRetryException

from pipelex import log
from pipelex.cogt.exceptions import LLMWorkerError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract, LLMWorkerJobFuncName

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


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
        self: LLMWorkerAbstract,
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
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=llm_job)

        return result

    return cast(F, wrapper)
