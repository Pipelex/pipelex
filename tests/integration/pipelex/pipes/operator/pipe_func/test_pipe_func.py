import pytest

from pipelex import log, pretty_print
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuffs.stuff_content import TextContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_pipe_router
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_operators.func.pipe_func_factory import PipeFuncFactory
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from pipelex.tools.func_registry import func_registry
from tests.cases.source_code import wrap_lines


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipeFunc:
    @classmethod
    def setup_class(cls):
        """Register test functions before running tests."""
        func_registry.register_function(wrap_lines)

    @classmethod
    def teardown_class(cls):
        """Clean up registered functions after tests."""
        if func_registry.has_function("wrap_lines"):
            func_registry.unregister_function_by_name("wrap_lines")

    async def test_wrap_lines_pipe_func(
        self,
        pipe_run_mode: PipeRunMode,
    ):
        # Sample source code to test with
        sample_code = """def hello_world():
    print("Hello, World!")
    return "Hello!"

if __name__ == "__main__":
    hello_world()"""

        # Create stuff with the source code
        source_text_stuff = StuffFactory.make_stuff(
            name="source_text",
            concept=ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT]),
            content=TextContent(text=sample_code),
        )

        # Create working memory with the source text
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=source_text_stuff)

        # Create the PipeFunc job
        pipe_func_blueprint = PipeFuncBlueprint(
            definition="Function pipe for wrapping lines",
            function_name="wrap_lines",
            output=NativeConceptEnum.TEXT,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeFuncFactory.make_from_blueprint(
                domain="source_code",
                pipe_code="wrap_lines",
                blueprint=pipe_func_blueprint,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            working_memory=working_memory,
        )

        # Execute the pipe
        pipe_func_output = await get_pipe_router().run(
            pipe_job=pipe_job,
        )

        # Log and verify results
        log.verbose(pipe_func_output, title="pipe_func_output")
        wrapped_text = pipe_func_output.main_stuff_as_text
        pretty_print(wrapped_text, title="wrapped_text")

        # Verify the output contains wrapped lines
        assert pipe_func_output is not None
        assert pipe_func_output.working_memory is not None
        assert pipe_func_output.main_stuff is not None

        # Get the actual text string for verification
        wrapped_text_str = wrapped_text.text

        # In DRY mode, we get mock content, so we only check basic structure
        if pipe_run_mode == PipeRunMode.DRY:
            # In dry mode, just verify we have text content and it's non-empty
            assert isinstance(wrapped_text_str, str)
            assert len(wrapped_text_str) > 0
        else:
            # In LIVE mode, check the actual wrapping functionality
            # Check that each line is wrapped in span tags
            lines = wrapped_text_str.split("\n")
            for line in lines:
                assert line.startswith('<span class="line">'), f"Line should start with span tag: {line}"
                assert line.endswith("</span>"), f"Line should end with span tag: {line}"

            # Verify we have the expected number of lines (original had 6 lines)
            assert len(lines) == 6, f"Expected 6 lines, got {len(lines)}"

            # Verify specific content is preserved within spans
            assert '<span class="line">def hello_world():</span>' in wrapped_text_str
            assert '<span class="line">    print("Hello, World!")</span>' in wrapped_text_str
