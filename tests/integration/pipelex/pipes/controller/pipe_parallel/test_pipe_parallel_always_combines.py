"""PipeParallel always combines its branch outputs into its declared output and stamps it as main stuff.

Covers the two failure modes of the old `combined_output`-gated behavior:
- stale stamp: a sequence ending in an add-each-only parallel used to silently deliver the previous
  step's stuff as main stuff;
- missing main stuff: an add-each-only parallel as top-level pipe (API path, memory built from
  pipeline inputs) used to complete with no main stuff at all.

Dry-run parity is covered by the pipe_run_mode parametrization: the same shape assertions run in
both live and dry modes.
"""

import pytest

from pipelex.core.stuffs.composite_content import CompositeContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexMTHDSProtocol

_LIBRARY_DIR = "tests/integration/pipelex/pipes/controller/pipe_parallel"


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeParallelAlwaysCombines:
    async def test_terminal_parallel_delivers_main_stuff(self, pipe_run_mode: PipeRunMode):
        """An add-each-only parallel as top-level pipe must deliver the combined composite as main stuff."""
        runner = PipelexMTHDSProtocol(
            library_dirs=[_LIBRARY_DIR],
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute(
            pipe_code="pac_terminal_parallel",
            inputs={"input_text": TextContent(text="The quick brown fox jumps over the lazy dog.")},
        )
        pipe_output = response.pipe_output

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert main_stuff.concept.code == "Composite"
        assert isinstance(main_stuff.content, CompositeContent)
        combined_dump = main_stuff.content.smart_dump()
        assert set(combined_dump.keys()) == {"tone_result", "length_result"}

        # add_each_output still exposes the branch outputs by name
        working_memory = pipe_output.working_memory
        assert working_memory.get_stuff("tone_result") is not None
        assert working_memory.get_stuff("length_result") is not None

    async def test_sequence_ending_in_parallel_delivers_composite_not_stale_stuff(self, pipe_run_mode: PipeRunMode):
        """Stale-stamp regression: the sequence's main stuff must be the parallel's combined composite,
        not the previous step's output.
        """
        runner = PipelexMTHDSProtocol(
            library_dirs=[_LIBRARY_DIR],
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute(
            pipe_code="pac_sequence_ending_in_parallel",
            inputs={"input_text": TextContent(text="A tale of two cities, in one sentence.")},
        )
        pipe_output = response.pipe_output

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert main_stuff.concept.code == "Composite", (
            f"Main stuff must be the parallel's combined output, not the previous step's stuff (got concept '{main_stuff.concept.concept_ref}')"
        )
        assert isinstance(main_stuff.content, CompositeContent)
        combined_dump = main_stuff.content.smart_dump()
        assert set(combined_dump.keys()) == {"tone_result", "length_result"}

        # The combined stuff is stored under the step's result name
        working_memory = pipe_output.working_memory
        combo_stuff = working_memory.get_stuff("combo")
        assert combo_stuff is not None
        assert combo_stuff.stuff_code == main_stuff.stuff_code
