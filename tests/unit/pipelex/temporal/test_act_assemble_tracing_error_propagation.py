"""Pins the error-propagation contract of ``act_assemble_tracing``.

Tracing assembly is best-effort observability: ``assemble_tracing`` catches the EXPECTED
read/assemble failures and returns them on the ``*_assembly_error`` fields (no raise). A
genuinely unexpected error (a programming bug in assembly) must instead PROPAGATE out of the
activity so that ``WfPipeRun``'s ``except ActivityError`` branch records it on the pipe output —
mirroring DIRECT mode, where ``assemble_tracing_on_output`` lets the same errors surface.
Swallowing it into an empty result would make the workflow see success and silently produce no
cost report and no diagnostic. These tests pin that the activity does not swallow unexpected
errors and otherwise passes the assembled result through unchanged.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.pipe_run.tracing_assembly import TracingAssembly
from pipelex.temporal.tprl_pipe.act_assemble_tracing import AssembleTracingArg, act_assemble_tracing


@pytest.mark.asyncio(loop_scope="class")
class TestActAssembleTracingErrorPropagation:
    async def test_unexpected_error_propagates(self, mocker: MockerFixture) -> None:
        """An unexpected error from assemble_tracing propagates instead of degrading to an empty result."""
        mocker.patch(
            "pipelex.temporal.tprl_pipe.act_assemble_tracing.assemble_tracing",
            side_effect=KeyError("unexpected programming bug in assembly"),
        )
        arg = AssembleTracingArg(pipeline_run_id="plr-boom", assemble_graph=True, assemble_usage=True)

        with pytest.raises(KeyError):
            await act_assemble_tracing(arg)

    async def test_assembled_result_passes_through(self, mocker: MockerFixture) -> None:
        """On success the activity returns assemble_tracing's result unchanged (including *_error fields)."""
        expected = TracingAssembly(usage_assembly_error="recorded read failure")
        mocker.patch(
            "pipelex.temporal.tprl_pipe.act_assemble_tracing.assemble_tracing",
            return_value=expected,
        )
        arg = AssembleTracingArg(pipeline_run_id="plr-ok", assemble_graph=False, assemble_usage=True)

        result = await act_assemble_tracing(arg)

        assert result == expected
