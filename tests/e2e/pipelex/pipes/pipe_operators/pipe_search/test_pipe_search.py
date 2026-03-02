"""E2E tests for PipeSearch operator."""

import pytest

from pipelex import pretty_print
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexRunner
from tests.e2e.pipelex.pipes.pipe_operators.pipe_search.test_data import PipeSearchTestCases

LIBRARY_DIRS = ["tests/e2e/pipelex/pipes/pipe_operators/pipe_search"]


@pytest.mark.search
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio
class TestPipeSearch:
    """E2E tests for PipeSearch operator."""

    @pytest.mark.parametrize(
        ("variant", "pipe_code", "input_name", "input_value"),
        PipeSearchTestCases.SOURCED_QUERIES,
    )
    async def test_search_sourced(
        self,
        pipe_run_mode: PipeRunMode,
        variant: str,
        pipe_code: str,
        input_name: str,
        input_value: str,
    ) -> None:
        """Test a sourced web search that returns an answer with sources."""
        runner = PipelexRunner(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        pipeline_response = await runner.execute_pipeline(
            pipe_code=pipe_code,
            inputs={
                input_name: TextContent(text=input_value),
            },
        )

        pipe_output = pipeline_response.pipe_output
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        if pipe_run_mode.is_live:
            search_result = pipe_output.main_stuff_as(content_type=SearchResultContent)
            assert search_result.answer is not None
            assert len(search_result.answer.strip()) > 0
            assert len(search_result.sources) > 0
            pretty_print(search_result, title=f"Search Result ({variant})")
