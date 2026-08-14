import sys
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.config import get_config
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.interpreter_hub import get_library_manager, scoped_current_library, set_current_library
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_operators.func import direct_pipe_func_executor
from pipelex.pipe_operators.func.direct_pipe_func_executor import DirectPipeFuncExecutor
from pipelex.pipe_operators.func.pipe_func_execution_dtos import PipeFuncExecutionRequest
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode

# A method whose ONLY custom source is the PipeFunc — its output structure (Greeting) is a concept
# declared in the .mthds, NOT a shipped .py. The box must regenerate `structures.py` from the crate's
# concepts so the func's `from structures import Greeting` resolves and the func registers.
_GREET_MTHDS = """\
domain = "greet_demo"
description = "Greeting demo for structure regeneration"

[concept.Greeting]
description = "A greeting"
[concept.Greeting.structure]
text = { type = "text", description = "the greeting text", required = true }

[pipe.greet]
type = "PipeFunc"
description = "Build a greeting via customer code"
output = "Greeting"
function_name = "greet_it"
"""

_GREET_FUNC = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.system.registries.func_registry import pipe_func

from structures import greet_demo__Greeting


@pipe_func(name="greet_it")
async def greet_it(working_memory: WorkingMemory) -> greet_demo__Greeting:
    return greet_demo__Greeting(text="hello from generated structures")
"""


class TestDirectExecutorWorkdir:
    @pytest.mark.asyncio
    async def test_transported_run_cleans_up_workdir_on_failure(self, tmp_path: Path, mocker: MockerFixture):
        """The materialized source workdir must not leak, even when the transported run fails."""
        workdir = tmp_path / "transported_workdir"
        workdir.mkdir()
        mocker.patch("tempfile.mkdtemp", return_value=str(workdir))

        request = PipeFuncExecutionRequest(
            crate=LibraryCrate(python_sources={"funcs.py": "x = 1\n"}),
            working_memory_raw={},
            pipe_code="missing_pipe",
            function_name="missing_func",
            job_metadata=JobMetadata(user_id="user", pipeline_run_id="run"),
            pipe_run_params=PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=10, batch_max_concurrency=None),
        )

        with scoped_current_library(library_id=direct_pipe_func_executor._TRANSPORTED_LIBRARY_ID):  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            try:
                with pytest.raises((PipelexError, ValidationError)):
                    await DirectPipeFuncExecutor().run_pipe_func_transported(request=request)
            finally:
                get_library_manager().teardown(library_id=direct_pipe_func_executor._TRANSPORTED_LIBRARY_ID)  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]

        assert not workdir.exists()

    @pytest.mark.asyncio
    async def test_transported_run_restores_sys_path(self, tmp_path: Path, mocker: MockerFixture):
        """No sys.path entry under the workdir may survive a transported run, even a failing one."""
        workdir = tmp_path / "transported_workdir"
        workdir.mkdir()
        mocker.patch("tempfile.mkdtemp", return_value=str(workdir))

        request = PipeFuncExecutionRequest(
            crate=LibraryCrate(python_sources={"funcs/helpers.py": "x = 1\n"}),
            working_memory_raw={},
            pipe_code="missing_pipe",
            function_name="missing_func",
            job_metadata=JobMetadata(user_id="user", pipeline_run_id="run"),
            pipe_run_params=PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=10, batch_max_concurrency=None),
        )

        with scoped_current_library(library_id=direct_pipe_func_executor._TRANSPORTED_LIBRARY_ID):  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            try:
                with pytest.raises((PipelexError, ValidationError)):
                    await DirectPipeFuncExecutor().run_pipe_func_transported(request=request)
            finally:
                get_library_manager().teardown(library_id=direct_pipe_func_executor._TRANSPORTED_LIBRARY_ID)  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]

        stale_entries = [entry for entry in sys.path if Path(entry).is_relative_to(workdir)]
        assert stale_entries == []

    @pytest.mark.asyncio
    async def test_transported_run_generates_concept_structures(self):
        """A PipeFunc that imports its output concept structure runs even though the method ships no
        structure .py — the box regenerates `structures.py` from the crate's concepts.

        Regression for the atlas custom-PipeFunc failure: the method's `structures/*.py` never traveled,
        so `from structures import <Concept>` raised ModuleNotFoundError in the box and the func never
        registered ("Function not found in registry"). Generating the structures from the .mthds (the
        single source of truth) makes the import resolve without shipping — or drifting — a copy.
        """
        # Build a real crate from the .mthds (hosted mode: the loader tolerates the yet-unregistered
        # function), then attach ONLY the PipeFunc source — deliberately NO structures/ source.
        pipe_func_config = get_config().pipelex.pipe_func_config
        previous_mode = pipe_func_config.execution_mode
        pipe_func_config.execution_mode = "local_sandbox"
        library_manager = get_library_manager()
        try:
            with tempfile.TemporaryDirectory() as mthds_dir:
                (Path(mthds_dir) / "greet.mthds").write_text(_GREET_MTHDS, encoding="utf-8")
                build_library_id, _ = library_manager.open_library()
                set_current_library(library_id=build_library_id)
                try:
                    library_manager.load_libraries(library_id=build_library_id, library_dirs=[Path(mthds_dir)])
                    crate = library_manager.get_crate(library_id=build_library_id)
                    assert crate is not None
                finally:
                    library_manager.teardown(library_id=build_library_id)
        finally:
            pipe_func_config.execution_mode = previous_mode

        crate_with_func = crate.model_copy(update={"python_sources": {"funcs.py": _GREET_FUNC}})
        request = PipeFuncExecutionRequest(
            crate=crate_with_func,
            working_memory_raw=WorkingMemoryFactory.make_empty().dump_for_transport(),
            # Qualified, as PipeFunc now sends it: the transported library is keyed by pipe_ref and
            # its lookup is strict, so a bare code would not resolve on the far side.
            pipe_code="greet_demo.greet",
            function_name="greet_it",
            job_metadata=JobMetadata(user_id="user", pipeline_run_id="run"),
            pipe_run_params=PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=10, batch_max_concurrency=None),
        )

        with scoped_current_library(library_id=direct_pipe_func_executor._TRANSPORTED_LIBRARY_ID):  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            try:
                # No raise = the func registered = `from structures import Greeting` resolved against the
                # generated structures.py. Before the fix this raised "Function 'greet_it' not found in registry".
                response = await DirectPipeFuncExecutor().run_pipe_func_transported(request=request)
            finally:
                get_library_manager().teardown(library_id=direct_pipe_func_executor._TRANSPORTED_LIBRARY_ID)  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]

        assert response.function_qualname == "greet_it"
