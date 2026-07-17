from pathlib import Path

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_operators.func import direct_pipe_func_executor
from pipelex.pipe_operators.func.direct_pipe_func_executor import DirectPipeFuncExecutor
from pipelex.pipe_operators.func.pipe_func_execution_dtos import PipeFuncExecutionRequest
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata


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
            pipe_run_params=PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=10),
        )

        prev_library_id = get_current_library_id_or_none()
        try:
            with pytest.raises((PipelexError, ValidationError)):
                await DirectPipeFuncExecutor().run_pipe_func_transported(request=request)
        finally:
            get_library_manager().teardown(library_id=direct_pipe_func_executor._TRANSPORTED_LIBRARY_ID)  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            if prev_library_id is not None:
                set_current_library(library_id=prev_library_id)
            else:
                clear_current_library()

        assert not workdir.exists()
