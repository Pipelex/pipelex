from pathlib import Path
from typing import Callable

import pytest

from pipelex import log, pretty_print
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.stuff import Stuff
from pipelex.hub import get_pipe_router, get_required_pipe
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.exceptions import PipeStackOverflowError
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.test_data import PipeTestCases


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.extract
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeRunningVariants:
    @pytest.mark.parametrize(("topic", "stuff", "pipe_code"), PipeTestCases.STUFF_AND_PIPE)
    async def test_pipe_from_stuff(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        topic: str,
        stuff: Stuff,
        pipe_code: str,
        load_test_library: Callable[[list[Path]], None],
    ):
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])
        log.verbose(stuff, title=f"{topic}: start from '{stuff.stuff_name}', run pipe '{pipe_code}'")
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)
        _ = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code=pipe_code),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=job_metadata,
            ),
        )

    @pytest.mark.parametrize(("topic", "pipe_code"), PipeTestCases.NO_INPUT)
    async def test_pipe_no_input(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        topic: str,
        pipe_code: str,
        load_test_library: Callable[[list[Path]], None],
    ):
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])
        log.verbose(f"{topic}: just run pipe '{pipe_code}'")
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code=pipe_code),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=WorkingMemoryFactory.make_empty(),
                job_metadata=job_metadata,
            ),
        )

        stuff = pipe_output.main_stuff
        pretty_print(stuff, title=f"{topic}: run pipe '{pipe_code}'")
        pretty_print(await stuff.content.rendered_html_async(), title=f"{topic}: run pipe '{pipe_code}' in html")
        pretty_print(await stuff.content.rendered_markdown_async(), title=f"{topic}: run pipe '{pipe_code}' in markdown")

    @pytest.mark.parametrize(("topic", "pipe_code", "output_multiplicity"), PipeTestCases.NO_INPUT_PARALLEL1)
    async def test_pipe_batch_no_input(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        topic: str,
        pipe_code: str,
        output_multiplicity: VariableMultiplicity | None,
        load_test_library: Callable[[list[Path]], None],
    ):
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])
        log.verbose(f"{topic}: just run pipe '{pipe_code}'")
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code=pipe_code),
                pipe_run_params=PipeRunParamsFactory.make_run_params(
                    pipe_run_mode=pipe_run_mode,
                    output_multiplicity=output_multiplicity,
                ),
                job_metadata=job_metadata,
                working_memory=WorkingMemoryFactory.make_empty(),
            ),
        )

        stuff = pipe_output.main_stuff
        pretty_print(stuff, title=f"{topic}: run pipe '{pipe_code}'")
        pretty_print(await stuff.content.rendered_html_async(), title=f"{topic}: run pipe '{pipe_code}' in html")
        pretty_print(await stuff.content.rendered_markdown_async(), title=f"{topic}: run pipe '{pipe_code}' in markdown")

    @pytest.mark.parametrize(("pipe_code", "exception", "expected_error_message"), PipeTestCases.FAILURE_PIPES)
    async def test_pipe_infinite_loop(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        pipe_code: str,
        exception: type[Exception],
        expected_error_message: str,
        load_test_library: Callable[[list[Path]], None],
    ):
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])
        log.verbose(f"This pipe '{pipe_code}' is supposed to cause an error of type: {exception.__name__}")
        with pytest.raises(PipeStackOverflowError) as exc:
            await get_pipe_router().run(
                pipe_job=PipeJobFactory.make_pipe_job(
                    pipe=get_required_pipe(pipe_code=pipe_code),
                    pipe_run_params=PipeRunParamsFactory.make_run_params(
                        pipe_stack_limit=6,
                        pipe_run_mode=pipe_run_mode,
                    ),
                    job_metadata=job_metadata,
                ),
            )
        pretty_print(exc.value, title="exception")
        assert expected_error_message in str(exc.value)
