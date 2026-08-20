from pathlib import Path
from typing import Callable

import pytest

from pipelex.interpreter_hub import get_pipe_router, get_required_entry_pipe
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.test_extras.mthds_corpus.loader import get_entry


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestImageOutIn:
    async def test_image_out_in(self, job_metadata: JobMetadata, pipe_run_mode: PipeRunMode, load_test_library: Callable[[list[Path]], None]) -> None:
        # The bundle is a corpus entry: an Image produced by one pipe and consumed by the next is
        # a language-level shape, and the corpus is the single source for those.
        load_test_library([get_entry(name="image_round_trip_room_photo").directory])
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_entry_pipe(pipe_code="illustrate_and_caption_room"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                job_metadata=job_metadata,
            ),
        )

        if pipe_run_mode.is_live:
            description = pipe_output.main_stuff_as_str
            assert description
