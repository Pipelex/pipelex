import sys
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
from pipelex.pipe_operators.func.pipe_func_execution_dtos import PipeFuncExecutionRequest, PipeFuncExecutionResponse
from pipelex.pipe_operators.func.pipe_func_execution_transport import build_pipe_func_execution_request
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode

# A method whose ONLY custom source is the PipeFunc — its output structure (Greeting) is a concept
# declared in the .mthds, NOT a shipped .py. The box must regenerate `structures.py` from the crate's
# concepts so the func's `from structures import greet_demo__Greeting` resolves.
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
function_name = "greet_demo_funcs.greeting.greet_it"
"""

_GREET_FUNC = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.system.registries.func_registry import pipe_func

from greet_demo_funcs.wording import GREETING_TEXT
from structures import greet_demo__Greeting


@pipe_func()
async def greet_it(working_memory: WorkingMemory) -> greet_demo__Greeting:
    return greet_demo__Greeting(text=GREETING_TEXT)
"""

_GREET_WORDING = 'GREETING_TEXT = "hello from generated structures"\n'


def _job_metadata() -> JobMetadata:
    return JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user", pipeline_run_id="run"))


def _dry_run_params() -> PipeRunParams:
    return PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=10, batch_max_concurrency=None)


def _missing_pipe_request(*, files: dict[str, str]) -> PipeFuncExecutionRequest:
    return PipeFuncExecutionRequest(
        crate=LibraryCrate(),
        files=dict(files),
        working_memory_raw={},
        pipe_code="missing_pipe",
        function_name="missing_funcs.missing_func",
        job_metadata=_job_metadata(),
        pipe_run_params=_dry_run_params(),
    )


async def _run_transported(*, request: PipeFuncExecutionRequest, tree_root: Path | None = None) -> PipeFuncExecutionResponse:
    library_id = direct_pipe_func_executor._TRANSPORTED_LIBRARY_ID  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
    with scoped_current_library(library_id=library_id):
        try:
            if tree_root is None:
                return await DirectPipeFuncExecutor().run_pipe_func_transported(request=request)
            return await DirectPipeFuncExecutor().run_pipe_func_transported_at(request=request, tree_root=tree_root)
        finally:
            get_library_manager().teardown(library_id=library_id)


def _greet_request(*, tmp_path: Path) -> PipeFuncExecutionRequest:
    """The request a sandbox-hosted deployment builds for the greet step of a method folder holding its Python."""
    method_dir = tmp_path / "greet_method"
    (method_dir / "greet_demo_funcs").mkdir(parents=True)
    (method_dir / "greet.mthds").write_text(_GREET_MTHDS, encoding="utf-8")
    (method_dir / "greet_demo_funcs" / "greeting.py").write_text(_GREET_FUNC, encoding="utf-8")
    (method_dir / "greet_demo_funcs" / "wording.py").write_text(_GREET_WORDING, encoding="utf-8")

    pipe_func_config = get_config().interpreter.pipe_func
    previous_mode = pipe_func_config.execution_mode
    pipe_func_config.execution_mode = "local_sandbox"
    library_manager = get_library_manager()
    try:
        build_library_id, _ = library_manager.open_library()
        set_current_library(library_id=build_library_id)
        try:
            library_manager.load_libraries(library_id=build_library_id, library_dirs=[method_dir])
            return build_pipe_func_execution_request(
                job_metadata=_job_metadata(),
                # Qualified, as PipeFunc sends it: the transported library is keyed by pipe_ref and its lookup is strict.
                pipe_code="greet_demo.greet",
                function_name="greet_demo_funcs.greeting.greet_it",
                working_memory=WorkingMemoryFactory.make_empty(),
                pipe_run_params=_dry_run_params(),
            )
        finally:
            library_manager.teardown(library_id=build_library_id)
    finally:
        pipe_func_config.execution_mode = previous_mode


class TestDirectExecutorWorkdir:
    @pytest.mark.asyncio
    async def test_transported_run_cleans_up_workdir_on_failure(self, tmp_path: Path, mocker: MockerFixture):
        """The directory the call's files are written into must not leak, even when the transported run fails."""
        workdir = tmp_path / "transported_workdir"
        workdir.mkdir()
        mocker.patch("tempfile.mkdtemp", return_value=str(workdir))

        with pytest.raises((PipelexError, ValidationError)):
            await _run_transported(request=_missing_pipe_request(files={"missing_funcs.py": "x = 1\n"}))

        assert not workdir.exists()

    @pytest.mark.asyncio
    async def test_transported_run_restores_sys_path(self, tmp_path: Path, mocker: MockerFixture):
        """No sys.path entry under the workdir may survive a transported run, even a failing one."""
        workdir = tmp_path / "transported_workdir"
        workdir.mkdir()
        mocker.patch("tempfile.mkdtemp", return_value=str(workdir))

        with pytest.raises((PipelexError, ValidationError)):
            await _run_transported(request=_missing_pipe_request(files={"missing_funcs/helpers.py": "x = 1\n"}))

        stale_entries = [entry for entry in sys.path if Path(entry).is_relative_to(workdir)]
        assert stale_entries == []

    @pytest.mark.asyncio
    async def test_transported_run_restores_sys_path_under_a_symlinked_temp_dir(self, tmp_path: Path, mocker: MockerFixture):
        """The call's root is resolved, so a temp dir reached through a symlink (`/var` on macOS) leaves no entry behind."""
        real_workdir = tmp_path / "real_workdir"
        real_workdir.mkdir()
        linked_workdir = tmp_path / "linked_workdir"
        linked_workdir.symlink_to(real_workdir, target_is_directory=True)
        mocker.patch("tempfile.mkdtemp", return_value=str(linked_workdir))

        with pytest.raises((PipelexError, ValidationError)):
            await _run_transported(request=_missing_pipe_request(files={"missing_funcs/probe.py": "x = 1\n"}))

        stale_entries = [entry for entry in sys.path if Path(entry).is_relative_to(real_workdir) or Path(entry).is_relative_to(linked_workdir)]
        assert stale_entries == []

    @pytest.mark.asyncio
    async def test_transported_run_imports_by_import_path_and_generates_concept_structures(self, tmp_path: Path):
        """A PipeFunc that imports a sibling module and its output concept's structure runs in the box.

        The call carries every file of the step's tree but the bundles: the function's module and the module it imports
        travel at their tree paths, and the box regenerates `structures.py` from the crate's concepts, so the method
        ships no copy of it that could drift from the .mthds.
        """
        request = _greet_request(tmp_path=tmp_path)
        assert sorted(request.files) == ["greet_demo_funcs/greeting.py", "greet_demo_funcs/wording.py"]
        assert request.crate.pipe_func_files == {}

        response = await _run_transported(request=request)

        assert response.function_module == "greet_demo_funcs.greeting"
        assert response.function_qualname == "greet_it"
        assert "greet_demo_funcs.greeting" not in sys.modules

    @pytest.mark.asyncio
    async def test_transported_run_at_a_root_the_client_filled(self, tmp_path: Path):
        """A sandbox client may unpack the call's files itself and hand the directory over; nothing is written beside them."""
        request = _greet_request(tmp_path=tmp_path)
        tree_root = (tmp_path / "unpacked").resolve()
        for tree_path, entry in request.files.items():
            target = tree_root.joinpath(*tree_path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            assert isinstance(entry, str)
            target.write_text(entry, encoding="utf-8")

        response = await _run_transported(request=request.model_copy(update={"files": {}}), tree_root=tree_root)

        assert response.function_qualname == "greet_it"
        assert (tree_root / "structures.py").is_file()
        assert not list(tree_root.rglob("__pycache__"))
