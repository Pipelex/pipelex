import asyncio
import inspect
import shutil
import sys
import tempfile
from pathlib import Path
from typing import cast

from typing_extensions import override

from pipelex import log
from pipelex.codegen.emitters.python_structures import emit_python_structures
from pipelex.codegen.resolved_concepts import resolve_concepts_from_crate
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_library_manager
from pipelex.pipe_operators.func.exceptions import PipeFuncExecutionError
from pipelex.pipe_operators.func.pipe_func_execution_dtos import PipeFuncExecutionRequest, PipeFuncExecutionResponse
from pipelex.pipe_operators.func.pipe_func_executor_protocol import PipeFuncExecutionResult, PipeFuncExecutorProtocol
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.runtime_bridge.primitives.rehydration import rehydrate_library_and_memory
from pipelex.system.job_metadata import JobMetadata
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
        try:
            return await self._run_transported_from_workdir(request=request, workdir=workdir)
        finally:
            # The imported modules live on in memory; the materialized sources are only needed during
            # import, so the workdir is removed on every path (success, timeout, failure). The sys.path
            # entries inserted for that import are pruned too — the mkdtemp path is unique, so removing
            # exactly the entries under this workdir is safe even with concurrent transported runs
            # (unlike a snapshot/restore of the whole list).
            sys.path[:] = [entry for entry in sys.path if not Path(entry).is_relative_to(workdir)]
            shutil.rmtree(workdir, ignore_errors=True)

    async def _run_transported_from_workdir(self, *, request: PipeFuncExecutionRequest, workdir: Path) -> PipeFuncExecutionResponse:
        for relpath, source in request.crate.python_sources.items():
            target = workdir / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")

        # Generate the method's concept structure classes from the crate — the .mthds is the single
        # source of truth for them (`resolve_concepts_from_crate` reads the crate's ConceptBlueprints,
        # `emit_python_structures` projects a `structures.py`). So a PipeFunc can
        # `from structures import <domain>__<Concept>` without the method having to STORE or transport a
        # hand-written copy that could drift from the .mthds. A file the method actually shipped at the
        # same path wins (already materialized above) — never clobber customer source.
        #
        # Force domain-qualified class names (`atlas_devis__PricedQuote`): the runtime ALWAYS qualifies a
        # concept's structure class (`concept.structure_class_name`), and that is the exact name a
        # PipeFunc's return-type validation checks against — so the generated classes must match the
        # runtime spelling, not the emitter's default collision-only qualification (which would emit a
        # bare `PricedQuote` the validator rejects).
        resolved_library = resolve_concepts_from_crate(request.crate)
        qualified_library = resolved_library.model_copy(
            update={"concepts": [concept.model_copy(update={"needs_qualification": True}) for concept in resolved_library.concepts]}
        )
        for emitted in emit_python_structures(qualified_library):
            generated_target = workdir / emitted.filename
            if generated_target.exists():
                log.verbose(f"Structures file '{emitted.filename}' was shipped by the method; keeping the shipped copy over the generated one.")
                continue
            generated_target.parent.mkdir(parents=True, exist_ok=True)
            generated_target.write_text(emitted.content, encoding="utf-8")

        # Put the bundle's directories on sys.path so a PipeFunc (or structure class) can import a sibling
        # file from the same bundle. This is only reached in-box (transported path): the crate is
        # re-materialized into a throwaway workdir that is NOT on sys.path, and each module is imported by
        # file path (spec_from_file_location), which does NOT add its directory to sys.path either — so a
        # top-level `from helpers import ...` between sibling files raises ModuleNotFoundError, the module
        # never finishes importing, and its @pipe_func never registers. A local direct run does not hit
        # this: its funcs were registered at boot from the real on-disk project already on sys.path. Add
        # workdir (resolves `from funcs.helpers import ...`) and every subdirectory holding a .py file
        # (resolves the sibling-relative `from helpers import ...`); the caller's finally prunes these
        # entries once the import phase is over, so they never outlive the run.
        source_dirs = {workdir} | {py_file.parent for py_file in workdir.rglob("*.py")}
        for source_dir in source_dirs:
            sys.path.insert(0, str(source_dir))

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

        # Runaway-code guard: time out the PipeFunc if it runs past the request's (plan-dependent)
        # deadline. Best-effort in-process — a blocking sync function keeps its worker thread; the
        # hard kill is the execution boundary's job (the sandbox destroys the box, the subprocess is
        # terminated).
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
