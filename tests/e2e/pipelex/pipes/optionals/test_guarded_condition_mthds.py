"""Runtime branch selection by a PipeCondition whose expression guards a declared-optional input,
from a `.mthds` file: present selects the flagged branch, absent evaluates the guard over an
undefined variable and selects the fallback — plus a negative control proving the load gate
rejects the unguarded variant.
"""

from pathlib import Path

import pytest

from pipelex.base_exceptions import PipelexError
from pipelex.core.memory.absence import AbsenceKind
from pipelex.pipeline.pipeline_response import RunState
from pipelex.pipeline.runner import PipelexMTHDSProtocol

_FIXTURE_DIR = Path(__file__).parent / "guarded_condition"
_BUNDLE_PATH = _FIXTURE_DIR / "guarded_condition.mthds"


@pytest.mark.asyncio(loop_scope="class")
class TestGuardedConditionExpression:
    async def test_flag_present_selects_with_flag_branch(self):
        """With the optional flag provided, the guarded expression evaluates truthy and routes to
        the flagged branch.
        """
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)])

        response = await runner.execute(pipe_code="ogc_route_on_flag", inputs={"flag": "urgent"})

        assert response.state == RunState.COMPLETED
        assert response.pipe_output.main_stuff.as_text.text == "flagged-branch"
        assert response.pipe_output.working_memory.absences == {}

    async def test_flag_absent_selects_no_flag_branch_and_keeps_record(self):
        """With the flag omitted, the expression evaluates the guard over an undefined variable,
        routes to the fallback branch, and the not-provided record persists.
        """
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)])

        response = await runner.execute(pipe_code="ogc_route_on_flag", inputs={})

        assert response.state == RunState.COMPLETED
        assert response.pipe_output.main_stuff.as_text.text == "plain-branch"
        flag_record = response.pipe_output.working_memory.get_optional_absence("flag")
        assert flag_record is not None
        assert flag_record.kind == AbsenceKind.NOT_PROVIDED

    async def test_unguarded_variant_fails_at_load(self):
        """Negative control: the same bundle with an unguarded expression over the optional input
        is rejected by the load-time guard lint — the passing bundle passes because it guards.
        """
        guarded_text = _BUNDLE_PATH.read_text(encoding="utf-8")
        unguarded_text = guarded_text.replace(
            """expression_template = "{{ 'with_flag' if flag is defined else 'no_flag' }}\"""",
            """expression_template = "{{ flag.text }}\"""",
        )
        assert unguarded_text != guarded_text

        runner = PipelexMTHDSProtocol()
        with pytest.raises(PipelexError) as exc_info:
            await runner.execute(mthds_contents=[unguarded_text], inputs={})

        assert "flag" in str(exc_info.value)
