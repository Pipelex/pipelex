import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.dry_mock import MOCK_USAGE_MODEL_NAME
from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.config import get_config
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_hub import scoped_event_log
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.activity_event_log import ActivityEventLogCache
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.trace_events import UsageReportEvent

_DOMAIN = "usage_scoped_event_log"
_MTHDS = f"""
domain = "{_DOMAIN}"
description = "Minimal bundle for usage capture through a scoped event log"

[pipe.write_text]
type = "PipeLLM"
description = "Pipe that outputs plain text"
inputs = {{ subject = "Text" }}
output = "Text"
prompt = "Write about $subject"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestUsageScopedEventLog:
    async def test_isolated_leaf_usage_assembles_from_the_scoped_event_log(self, mocker: MockerFixture) -> None:
        """A run whose leaves report as if inside an isolated execution gets its usage from its scoped log alone.

        Tracing is off and the isolation probe says every emission comes from an isolated sub-execution, so before
        usage honoured the override the leaf's usage went to the runner fallback, which tracing-off drops, and the
        run assembled none. Now the leaf's usage lands in the scoped log, the run's assembly reads it from there, and
        the per-process fallback is never built.
        """
        mocker.patch.object(get_config().runtime.tracing, "is_enabled", False)
        mocker.patch("pipelex.reporting.reporting_manager.is_in_isolated_execution", return_value=True)
        fallback_spy = mocker.spy(ActivityEventLogCache, "get_or_create")
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(
            generate_graph=False,
            generate_usage=True,
            mock_inputs=True,
        )
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, is_mock_usage=True, execution_config=execution_config)
        run_log = InMemoryEventLog()

        with scoped_event_log(run_log):
            response = await runner.execute(pipe_code="write_text", mthds_contents=[_MTHDS])

        pipe_output = response.pipe_output
        assert pipe_output.usage_assembly_error is None
        assert pipe_output.tokens_usages is not None
        assert len(pipe_output.tokens_usages) >= 1
        assert all(usage.inference_model_name == MOCK_USAGE_MODEL_NAME for usage in pipe_output.tokens_usages)
        assert CostRegistry.aggregate_costs(pipe_output.tokens_usages).total_nb_tokens > 0
        pipeline_run_id = pipe_output.pipeline_run_id
        captured = [event for event in run_log.read_events(pipeline_run_id) if isinstance(event, UsageReportEvent)]
        assert len(captured) == len(pipe_output.tokens_usages)
        fallback_spy.assert_not_called()
