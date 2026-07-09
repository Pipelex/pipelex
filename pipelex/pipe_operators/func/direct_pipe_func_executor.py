import asyncio
import inspect
import tempfile
from pathlib import Path
from typing import cast

from typing_extensions import override

from pipelex import log
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_library_manager
from pipelex.pipe_operators.func.exceptions import PipeFuncExecutionError
from pipelex.pipe_operators.func.pipe_func_execution_dtos import PipeFuncExecutionRequest, PipeFuncExecutionResponse
from pipelex.pipe_operators.func.pipe_func_executor_protocol import PipeFuncExecutionResult, PipeFuncExecutorProtocol
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.runtime_bridge.primitives.rehydration import rehydrate_library_and_memory
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils
from pipelex.system.registries.func_registry import func_registry
from pipelex.system.registries.func_registry_utils import FuncRegistryUtils

# The library id the transported run rebuilds under. Internal to one process (a fresh sandbox box or a
# one-shot subprocess), so a fixed id is safe — there is no other library to collide with.
_TRANSPORTED_LIBRARY_ID = "pipe_func_transported_lib"


class DirectPipeFuncExecutor(PipeFuncExecutorProtocol):
    """The ``direct`` execution mode: resolve the function from the process-global registry and run it here.

    The free, in-process, trusted mode core owns (mirrors ``DirectOrchestrator`` on the orchestration
    axis). This is the pre-existing PipeFunc behavior, extracted verbatim from ``_live_run_operator_pipe``:
    async vs sync dispatch, and str/list -> StuffContent coercion. It is used for local runs and inside
    a sandbox box (where the real function IS registered); a sandbox-dispatching executor from the
    out-of-tree plugin runs it out-of-process instead when ``execution_mode`` names a sandbox backend.
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

    @override
    async def run_pipe_func_transported(self, *, request: PipeFuncExecutionRequest) -> PipeFuncExecutionResponse:
        """Register the customer's real code from the crate, rebuild the library + memory, run the one PipeFunc, transport the output.

        The far-from-caller half of out-of-process execution, and the single source of truth for it: a
        sandbox box runs exactly this (its entrypoint is a thin shell over this call), and it pulls in
        no sandbox code — pure open core — so a box needs only ``pipelex`` installed. Unlike the
        runner/worker, it deliberately imports and executes customer code, because it runs INSIDE the
        isolation boundary. The output rides back wrapped in a working memory so it round-trips with its
        concept (and thus its dynamic-class identity), rebound against the receiver's registry.
        """
        workdir = Path(tempfile.mkdtemp(prefix="pipelex_pipe_func_"))
        for relpath, source in request.crate.python_sources.items():
            target = workdir / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")

        # Register the customer's structure classes and @pipe_func functions from their real source,
        # before rehydration seeds a per-run registry from the global one and before the function lookup.
        ClassRegistryUtils.import_modules_in_folder(folder_path=workdir, base_class_names=[StructuredContent.__name__])
        ClassRegistryUtils.auto_register_all_subclasses(base_class=StructuredContent)
        FuncRegistryUtils.register_funcs_in_folder(folder_path=workdir)

        working_memory = rehydrate_library_and_memory(
            library_id=_TRANSPORTED_LIBRARY_ID,
            crate=request.crate,
            working_memory_raw=request.working_memory_raw,
        )
        if working_memory is None:
            msg = f"Transported rehydration produced no working memory for pipe '{request.pipe_code}'"
            raise PipeFuncExecutionError(msg)

        # Runaway-code guard: kill the PipeFunc if it runs past the request's (plan-dependent) timeout.
        try:
            execution_result = await asyncio.wait_for(
                self.run_pipe_func(
                    job_metadata=request.job_metadata,
                    pipe_code=request.pipe_code,
                    function_name=request.function_name,
                    working_memory=working_memory,
                    pipe_run_params=request.pipe_run_params,
                ),
                timeout=request.timeout_seconds,
            )
        except TimeoutError as exc:
            msg = f"PipeFunc '{request.function_name}' exceeded its {request.timeout_seconds}s timeout"
            raise PipeFuncExecutionError(msg) from exc

        # Wrap the output in a memory so it round-trips with its concept (and thus its class identity).
        pipe = get_library_manager().get_library(library_id=_TRANSPORTED_LIBRARY_ID).pipe_library.get_required_pipe(pipe_code=request.pipe_code)
        output_stuff = StuffFactory.make_stuff(concept=pipe.output.concept, content=execution_result.content)
        working_memory.set_new_main_stuff(stuff=output_stuff)

        return PipeFuncExecutionResponse(
            output_memory_raw=working_memory.dump_for_transport(),
            function_module=execution_result.function_module,
            function_qualname=execution_result.function_qualname,
        )
