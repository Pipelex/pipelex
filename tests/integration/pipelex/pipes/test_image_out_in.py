from pathlib import Path
from typing import Callable

import pytest

from pipelex.hub import get_pipe_router, get_required_pipe
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestImageOutIn:
    async def test_image_out_in(
        self, pipe_run_mode: PipeRunMode, load_test_library: Callable[[list[Path]], None], dummy_job_metadata: JobMetadata
    ) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="image_out_in"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                job_metadata=dummy_job_metadata,
            ),
        )

        if pipe_run_mode != PipeRunMode.DRY:
            description = pipe_output.main_stuff_as_str
            assert description
