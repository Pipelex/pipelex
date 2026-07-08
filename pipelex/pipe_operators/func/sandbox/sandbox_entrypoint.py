import asyncio
import sys
import tempfile
from pathlib import Path

from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_library_manager
from pipelex.pipe_operators.func.in_process_pipe_func_executor import InProcessPipeFuncExecutor
from pipelex.pipe_operators.func.sandbox.exceptions import SandboxExecutionError
from pipelex.pipe_operators.func.sandbox.sandbox_transport import SandboxRunRequest, SandboxRunResult
from pipelex.runtime_bridge.primitives.rehydration import rehydrate_library_and_memory
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils
from pipelex.system.registries.func_registry_utils import FuncRegistryUtils

_SANDBOX_LIBRARY_ID = "sandbox_lib"


async def _run(request: SandboxRunRequest) -> SandboxRunResult:
    """Register the customer's real code, rebuild the library + memory, run the one PipeFunc, transport the output.

    This runs INSIDE the sandbox, so — unlike the runner/worker — it deliberately imports and
    executes customer code. Hosted mode is off here (default), so the PipeFunc validators run for
    real against the now-registered function.
    """
    workdir = Path(tempfile.mkdtemp(prefix="pipelex_pipe_func_"))
    for relpath, source in request.crate.python_sources.items():
        target = workdir / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")

    # Register the customer's structure classes and @pipe_func functions from their real source.
    ClassRegistryUtils.import_modules_in_folder(folder_path=workdir, base_class_names=[StructuredContent.__name__])
    ClassRegistryUtils.auto_register_all_subclasses(base_class=StructuredContent)
    FuncRegistryUtils.register_funcs_in_folder(folder_path=workdir)

    # working_memory_raw is a required dict on the request, so rehydration always yields a memory.
    working_memory = rehydrate_library_and_memory(
        library_id=_SANDBOX_LIBRARY_ID,
        crate=request.crate,
        working_memory_raw=request.working_memory_raw,
    )
    if working_memory is None:
        msg = f"Sandbox rehydration produced no working memory for pipe '{request.pipe_code}'"
        raise SandboxExecutionError(msg)

    # Runaway-code guard: kill the PipeFunc if it runs past the request's (plan-dependent) timeout.
    try:
        execution_result = await asyncio.wait_for(
            InProcessPipeFuncExecutor().run_pipe_func(
                job_metadata=request.job_metadata,
                pipe_code=request.pipe_code,
                function_name=request.function_name,
                working_memory=working_memory,
                pipe_run_params=request.pipe_run_params,
            ),
            timeout=request.timeout_seconds,
        )
    except TimeoutError as exc:
        msg = f"PipeFunc '{request.function_name}' exceeded its {request.timeout_seconds}s sandbox timeout"
        raise SandboxExecutionError(msg) from exc

    # Wrap the output in a memory so it round-trips with its concept (and thus its class identity).
    pipe = get_library_manager().get_library(library_id=_SANDBOX_LIBRARY_ID).pipe_library.get_required_pipe(pipe_code=request.pipe_code)
    output_stuff = StuffFactory.make_stuff(concept=pipe.output.concept, content=execution_result.content)
    working_memory.set_new_main_stuff(stuff=output_stuff)

    return SandboxRunResult(
        output_memory_raw=working_memory.dump_for_transport(),
        function_module=execution_result.function_module,
        function_qualname=execution_result.function_qualname,
    )


def main() -> None:
    """CLI entrypoint run as a subprocess: read the request JSON, write the result JSON.

    argv: <request_json_path> <result_json_path>. On any failure the process exits non-zero with a
    diagnostic on stderr — the client turns that into a SandboxExecutionError.
    """
    request_path = Path(sys.argv[1])
    result_path = Path(sys.argv[2])
    request = SandboxRunRequest.model_validate_json(request_path.read_text(encoding="utf-8"))

    # Import here so module import (e.g. for tests) stays cheap and free of boot side effects.
    from pipelex.pipelex import Pipelex  # noqa: PLC0415

    Pipelex.make(needs_inference=False)
    try:
        result = asyncio.run(_run(request))
    finally:
        Pipelex.teardown_if_needed()
    result_path.write_text(result.model_dump_json(), encoding="utf-8")


if __name__ == "__main__":
    main()
