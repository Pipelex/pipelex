"""Dry-run coverage for native YesNo from a `.mthds` file.

Two shapes, both keyless (dry mode mocks only the cogt leaf and rides the live render path):
- YesNo as a PipeLLM output — the object path mocks a `YesNoContent` via polyfactory.
- YesNo as a pipeline input in the envelope form (`{"concept": "YesNo", "content": bool}`) — the
  bool flows through the factory's YesNo arm and renders inline in the downstream prompt.
"""

import pytest

from pipelex.pipeline.pipeline_response import RunState
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.test_extras.mthds_corpus.loader import get_entry

# The bundle is a corpus entry, not a fixture local to this test: the corpus is the single source
# for language-level `.mthds` methods, and covering `native.yes_no` is exactly why the entry exists.
_FIXTURE_DIR = get_entry(name="native_yes_no_urgent_message").directory


@pytest.mark.asyncio(loop_scope="class")
class TestYesNoDryRun:
    async def test_dry_run_yes_no_output_produces_mock_verdict(self):
        """A PipeLLM whose output is YesNo completes in dry mode with a mocked YesNoContent verdict."""
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)], pipe_run_mode=PipeRunMode.DRY)

        response = await runner.execute(pipe_code="judge_is_urgent", inputs={"message": "The server is on fire"})

        assert response.state == RunState.COMPLETED
        assert response.pipe_output.main_stuff.is_yes_no
        # The mocked value is a genuine bool.
        assert isinstance(response.pipe_output.main_stuff_as_yes_no.yes_no, bool)

    async def test_dry_run_yes_no_envelope_input_flows_through(self):
        """A YesNo pipeline input in the envelope form is shaped into YesNoContent and rides into the render context."""
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)], pipe_run_mode=PipeRunMode.DRY)

        response = await runner.execute(pipe_code="explain_verdict", inputs={"verdict": {"concept": "YesNo", "content": True}})

        assert response.state == RunState.COMPLETED
        verdict_stuff = response.pipe_output.working_memory.get_stuff("verdict")
        assert verdict_stuff.is_yes_no
        assert verdict_stuff.as_yes_no.yes_no is True
        # The downstream Text output was produced (the guarded render completed).
        assert response.pipe_output.main_stuff.as_text.text
