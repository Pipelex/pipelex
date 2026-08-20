"""Dry-run PipeLLM with a guarded optional prompt variable, from a `.mthds` file: dry mode rides
the live render path (only the cogt leaf mocks), so completing the run proves the guarded template
rendered correctly with the optional input genuinely absent — no API key involved.
"""

import pytest

from pipelex.core.memory.absence import AbsenceKind
from pipelex.pipeline.pipeline_response import RunState
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.test_extras.mthds_corpus.loader import get_entry

# The bundle is a corpus entry, not a fixture local to this test: the corpus is the single source for
# language-level `.mthds` methods, and covering `feature.optionals` is exactly why the entry exists.
_FIXTURE_DIR = get_entry(name="feature_optionals_village_notice").directory


@pytest.mark.asyncio(loop_scope="class")
class TestPromptGuardDryRun:
    async def test_dry_run_with_absent_optional_completes_and_keeps_record(self):
        """Omitting the guarded optional (without mock seeding) leaves it undefined in the prompt
        render context: the guarded arms render empty, the mock output is produced, and the
        not-provided record persists in the ledger.
        """
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)], pipe_run_mode=PipeRunMode.DRY)

        response = await runner.execute(pipe_code="draft_notice", inputs={"subject": "the bus timetable change"})

        assert response.state == RunState.COMPLETED
        assert response.pipe_output.main_stuff.as_text.text
        memory = response.pipe_output.working_memory
        style_hint_record = memory.get_optional_absence("style_hint")
        assert style_hint_record is not None
        assert style_hint_record.kind == AbsenceKind.NOT_PROVIDED
        # The output itself is a delivered mock value, not an absence.
        assert memory.get_optional_absence(response.main_stuff_name or "") is None

    async def test_dry_run_with_present_optional_renders_guarded_arm(self):
        """With the optional provided, the value rides into the render context and the ledger
        stays empty.
        """
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)], pipe_run_mode=PipeRunMode.DRY)

        response = await runner.execute(pipe_code="draft_notice", inputs={"subject": "the bus timetable change", "style_hint": "keep it formal"})

        assert response.state == RunState.COMPLETED
        memory = response.pipe_output.working_memory
        assert memory.absences == {}
        assert memory.get_stuff("style_hint").as_text.text == "keep it formal"
