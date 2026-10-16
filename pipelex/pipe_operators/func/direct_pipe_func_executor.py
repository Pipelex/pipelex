import asyncio
import shutil
import tempfile
from pathlib import Path

from mthds.method_tree.exceptions import MethodTreeRefusedError, TreeSourceError
from mthds.method_tree.written_tree import read_written_tree
from typing_extensions import override

from pipelex import log
from pipelex.codegen.emitters.python_structures import emit_python_structures
from pipelex.codegen.resolved_concepts import resolve_concepts_from_crate
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.method_trees.exceptions import TreePythonError
from pipelex.core.method_trees.tree_files import write_call_files
from pipelex.core.method_trees.tree_python import TREE_PYTHON_HOLD
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.interpreter_hub import get_library_manager, get_required_pipe
from pipelex.kernel.func_ops import call_function
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_operators.func.exceptions import PipeFuncExecutionError
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_call_context import function_of_call_in_flight
from pipelex.pipe_operators.func.pipe_func_execution_dtos import PipeFuncExecutionRequest, PipeFuncExecutionResponse
from pipelex.pipe_operators.func.pipe_func_executor_protocol import PipeFuncExecutionResult, PipeFuncExecutorProtocol
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.runtime_bridge.primitives.rehydration import rehydrate_library_and_memory
from pipelex.system.job_metadata import JobMetadata

# The library id the transported run rebuilds under. Internal to one process (a fresh sandbox box or a
# one-shot subprocess), so a fixed id is safe — there is no other library to collide with.
_TRANSPORTED_LIBRARY_ID = "pipe_func_transported_lib"


def resolve_pipe_func(*, pipe_code: str) -> PipeFunc:
    """The `PipeFunc` step of the current library a call names.

    Raises:
        PipeFuncExecutionError: The step the call names is not a `PipeFunc`.
    """
    pipe = get_required_pipe(pipe_code=pipe_code)
    if not isinstance(pipe, PipeFunc):
        msg = f"The pipe '{pipe_code}' a PipeFunc call names is a {pipe.type}, not a PipeFunc."
        raise PipeFuncExecutionError(msg)
    return pipe


class DirectPipeFuncExecutor(PipeFuncExecutorProtocol):
    """The ``direct`` execution mode: import the step's function in this process and run it here.

    The free, in-process, trusted mode core owns (mirrors ``DirectOrchestrator`` on the orchestration
    axis). It is used for local runs and inside a sandbox box, where the call's files were written to
    disk; a sandbox-dispatching executor from the out-of-tree plugin runs it out-of-process instead when
    ``execution_mode`` names a sandbox backend.

    The function is the step's own: the `PipeFunc` imports it by its import path, under the process's
    hold on its method tree's Python, and checks it (`PipeFunc.bind_function`). What running it *means*
    — async-vs-sync dispatch and the str/list -> StuffContent coercion — is the kernel's
    ``call_function``, so this executor is what is left once that is factored out: the in-process
    wiring of the live arm, and the whole transported arm below.
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
        # The step imported and checked its function before the run (its `_validate_before_run`), and names it for its
        # call in flight; a call that names none, the transported run's, finds the step in the current library, which
        # binds it once. The call itself — async/sync dispatch, return coercion — is the kernel's, so an out-of-process
        # executor and this one share one definition of what running a function means. Nothing is caught here: the
        # function is arbitrary user code whose failure surface is not enumerable, and the operator wraps this call to
        # decorate the failure with the pipe's inputs/output for a diagnostic PipeRunError.
        function = function_of_call_in_flight(pipe_ref=pipe_code) or resolve_pipe_func(pipe_code=pipe_code).bind_function()
        call_result = await call_function(function=function, function_name=function_name, memory=working_memory)
        return PipeFuncExecutionResult(
            content=call_result.content,
            function_module=call_result.function_module,
            function_qualname=call_result.function_qualname,
        )

    @override
    async def run_pipe_func_transported(self, *, request: PipeFuncExecutionRequest) -> PipeFuncExecutionResponse:
        """Write the call's files, rebuild the library + memory, run the one PipeFunc, transport the output.

        The far-from-caller half of out-of-process execution, and the single source of truth for it: a
        sandbox box runs exactly this (its entrypoint is a thin shell over this call), and it pulls in
        no sandbox code — pure open core — so a box needs only ``pipelex`` installed. Unlike the
        runner/worker, it deliberately imports and executes customer code, because it runs INSIDE the
        isolation boundary. The output rides back wrapped in a working memory so it round-trips with its
        concept (and thus its dynamic-class identity), rebound against the receiver's registry.

        The call's files are written into a fresh temporary directory, removed on every path.
        """
        # Resolved, so the root the hold puts on sys.path is the one the import system reports for its modules
        # (`/var` is `/private/var` on macOS).
        tree_root = Path(tempfile.mkdtemp(prefix="pipelex_pipe_func_")).resolve()
        try:
            return await self.run_pipe_func_transported_at(request=request, tree_root=tree_root)
        finally:
            shutil.rmtree(tree_root, ignore_errors=True)

    async def run_pipe_func_transported_at(self, *, request: PipeFuncExecutionRequest, tree_root: Path) -> PipeFuncExecutionResponse:
        """Run a transported call with its Python root at `tree_root`, a directory the caller may have filled already.

        A sandbox client may unpack the call's tree into the sandbox itself, such as from one archive per call, and hand
        the directory over; the files the request carries are written there too, at their tree paths. The directory is
        the call's import root: it goes first on `sys.path` under the process's hold on its Python, and the function is
        imported from it under its real import path.

        Raises:
            PipeFuncExecutionError: The call's files cannot be read back as a tree, or the function runs past its timeout.
        """
        write_call_files(files=request.files, destination=tree_root)
        self._write_generated_structures(crate=request.crate, tree_root=tree_root)
        try:
            tree = read_written_tree(tree_root)
        except (MethodTreeRefusedError, TreeSourceError) as exc:
            msg = f"The files of the PipeFunc call for pipe '{request.pipe_code}' cannot be read back as a method tree: {exc}"
            raise PipeFuncExecutionError(msg) from exc

        # The call's Python is held for the transported library until the run ends, and unloaded before its directory
        # is removed.
        TREE_PYTHON_HOLD.acquire(tree=tree, holder=_TRANSPORTED_LIBRARY_ID)
        try:
            return await self._run_transported(request=request, crate=self._crate_rooted_at(request=request, tree_json=tree.model_dump_json()))
        finally:
            TREE_PYTHON_HOLD.release(holder=_TRANSPORTED_LIBRARY_ID)
            TREE_PYTHON_HOLD.unload_if_unheld()

    @staticmethod
    def _write_generated_structures(*, crate: LibraryCrate, tree_root: Path) -> None:
        """Generate the method's concept structure classes from the crate as the `structures` module, unless the call shipped one.

        The .mthds is the single source of truth for them (`resolve_concepts_from_crate` reads the crate's
        ConceptBlueprints, `emit_python_structures` projects a `structures.py`), so a PipeFunc can
        `from structures import <domain>__<Concept>` without the method having to store or transport a
        hand-written copy that could drift from the .mthds. A file the method actually shipped at the
        same path wins — never clobber customer source.

        Domain-qualified class names are forced (`atlas_devis__PricedQuote`): the runtime ALWAYS qualifies a
        concept's structure class (`concept.structure_class_name`), and that is the exact name a
        PipeFunc's return-type validation checks against.
        """
        resolved_library = resolve_concepts_from_crate(crate)
        qualified_library = resolved_library.model_copy(
            update={"concepts": [concept.model_copy(update={"needs_qualification": True}) for concept in resolved_library.concepts]}
        )
        for emitted in emit_python_structures(qualified_library):
            generated_target = tree_root / emitted.filename
            if generated_target.exists():
                log.verbose(f"The structures file '{emitted.filename}' the method shipped was kept over the generated one")
                continue
            generated_target.parent.mkdir(parents=True, exist_ok=True)
            generated_target.write_text(emitted.content, encoding="utf-8")

    @staticmethod
    def _crate_rooted_at(*, request: PipeFuncExecutionRequest, tree_json: str) -> LibraryCrate:
        """The request's crate with the called step's method tree replaced by the tree written here.

        A step read from a tree resolves its function, and any file its tree's other steps name, in that tree, which the
        crate carries as the host that assembled it listed it; here the tree is the call's files as written in this
        process. A step parsed from a content string has no tree, and imports from this process's import path, which
        the hold starts with the call's root.
        """
        crate = request.crate
        tree_bundle_ref = crate.tree_bundles.get(request.pipe_code)
        if tree_bundle_ref is None:
            return crate
        method_trees = dict(crate.method_trees)
        method_trees[tree_bundle_ref.tree_key] = tree_json
        return crate.model_copy(update={"method_trees": method_trees})

    async def _run_transported(self, *, request: PipeFuncExecutionRequest, crate: LibraryCrate) -> PipeFuncExecutionResponse:
        # The crate was validated where it was assembled; its other steps may name files of trees this process never
        # receives, so it is loaded as it is, and the one step called checks its function as it binds it.
        working_memory = rehydrate_library_and_memory(
            library_id=_TRANSPORTED_LIBRARY_ID,
            crate=crate,
            working_memory_raw=request.working_memory_raw,
            is_crate_prevalidated=True,
        )
        if working_memory is None:
            msg = f"Transported rehydration produced no working memory for pipe '{request.pipe_code}'"
            raise PipeFuncExecutionError(msg)

        pipe_func = resolve_pipe_func(pipe_code=request.pipe_code)
        try:
            pipe_func.bind_function()
        except TreePythonError as exc:
            msg = f"PipeFunc '{request.pipe_code}' cannot call its function '{request.function_name}': {exc.message}"
            raise PipeFuncExecutionError(msg) from exc

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
