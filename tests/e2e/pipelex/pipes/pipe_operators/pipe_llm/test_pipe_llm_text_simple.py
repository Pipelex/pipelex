"""E2E test for PipeLLM with simple text-only input and output."""

import pytest

from pipelex import pretty_print
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio
class TestPipeLLMTextSimple:
    @pytest.mark.parametrize(
        ("variant", "pipe_code"),
        [
            ("using_setting", "write_haiku_e2e_using_setting"),
            ("using_preset", "write_haiku_e2e_using_preset"),
        ],
    )
    async def test_write_haiku(self, pipe_run_mode: PipeRunMode, variant: str, pipe_code: str) -> None:
        """Test a simple text-to-text PipeLLM pipe that writes a haiku."""
        pipeline_response = await PipelexMTHDSProtocol(library_dirs=["tests/e2e/pipelex/pipes/pipe_operators"], pipe_run_mode=pipe_run_mode).execute(
            pipe_code=pipe_code,
            inputs={
                "topic": TextContent(text="hello world"),
            },
        )

        # Basic assertions
        assert pipeline_response.pipe_output is not None
        assert pipeline_response.pipe_output.working_memory is not None
        assert pipeline_response.pipe_output.main_stuff is not None

        result_text = pipeline_response.pipe_output.main_stuff_as_str
        assert result_text is not None
        assert len(result_text.strip()) > 0

        pretty_print(result_text, title=f"Haiku ({variant})")

        # In live mode, verify haiku structure (3 non-empty lines)
        if pipe_run_mode.is_live:
            lines = [line for line in result_text.strip().splitlines() if line.strip()]
            assert len(lines) == 3, f"Expected 3 lines in haiku, got {len(lines)}: {result_text}"
