import asyncio
import inspect
from typing import cast

from typing_extensions import override

from pipelex import log
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_operators.func.pipe_func_executor_protocol import PipeFuncExecutionResult, PipeFuncExecutorProtocol
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.system.registries.func_registry import func_registry


class InProcessPipeFuncExecutor(PipeFuncExecutorProtocol):
    """Default executor: resolve the function from the process-global registry and run it here.

    This is the pre-existing PipeFunc behavior, extracted verbatim from ``_live_run_operator_pipe``:
    async vs sync dispatch, and str/list -> StuffContent coercion. It is used for local/direct runs
    and inside the sandbox (where the real function IS registered). It is NOT used on the hosted
    runner/worker, which injects the sandbox-dispatching executor instead.
    """

    @override
    async def run_pipe_func(
        self,
        *,
        job_metadata: JobMetadata,
        pipe_code: str,
        function_name: str,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
    ) -> PipeFuncExecutionResult:
        log.verbose(f"Running PipeFunc in-process with function '{function_name}'")
        function = func_registry.get_required_function(function_name)

        # The function is arbitrary user code; its failure surface is not enumerable. We do NOT catch
        # here: the operator wraps this call and decorates the failure with the pipe's inputs/output
        # for a diagnostic PipeRunError (preserving the pre-refactor behavior).
        if inspect.iscoroutinefunction(function):
            func_output_object = await function(working_memory=working_memory)
        else:
            func_output_object = await asyncio.to_thread(function, working_memory=working_memory)

        the_content: StuffContent
        if isinstance(func_output_object, StuffContent):
            the_content = func_output_object
        elif isinstance(func_output_object, list):
            func_result_list = cast("list[StuffContent]", func_output_object)
            the_content = ListContent(items=func_result_list)
        elif isinstance(func_output_object, str):
            the_content = TextContent(text=func_output_object)
        else:
            msg = f"Function '{function_name}' must return a StuffContent or a list, got {type(func_output_object)}"
            raise TypeError(msg)

        return PipeFuncExecutionResult(
            content=the_content,
            function_module=getattr(function, "__module__", None),
            function_qualname=getattr(function, "__qualname__", function_name),
        )
