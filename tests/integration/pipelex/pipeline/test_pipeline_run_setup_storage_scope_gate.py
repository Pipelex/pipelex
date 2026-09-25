"""Where `pipeline_run_setup` refuses a malformed `storage_scope`.

The scope decides where a tenant's bytes land, so a traversal in it is the
highest-stakes value this function takes. It was validated only inside
`prepare_pipe_job`, which runs below the pipeline registration, the library
acquire and the tracer open — so a scope carrying `..` registered a run before
anything looked at it. It ran below `handle_trace_start` as well, and emitted a
trace event that cannot be unsent; the trace-start has since moved beneath
`prepare_pipe_job`, so that half of the window is now closed by the ordering
itself. These pin the two gates that close the rest of it, and both fail if
either gate is removed.

The lower gate in `prepare_pipe_job` is NOT replaced by these and must stay: the
sentinel path rebinds the scope to the caller's `pipeline_run_id`, and only the
lower gate sees what a direct caller of that seam passes.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.pipeline import pipeline_run_setup as pipeline_run_setup_module
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.system.storage_scope import LOCAL_STORAGE_SCOPE

_MINIMAL_MTHDS = """
domain = "storage_scope_gate_test"
description = "Minimal bundle for the storage_scope gate test"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = { type = "text", description = "Topic name" }

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used only to set up a PipeJob"
inputs = { subject = "Text" }
output = "Topic"
prompt = "Echo the $subject as a topic"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestPipelineRunSetupStorageScopeGate:
    async def test_a_traversal_scope_registers_no_run_and_emits_no_trace_start(self, mocker: MockerFixture) -> None:
        """The caller's raw scope is refused above every observable effect.

        Spies, not stubs: they call through, so a failure here is the assertion
        and not a mock artifact tripping a constructor first.
        """
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)
        pipeline_manager = mocker.spy(pipeline_run_setup_module, "get_pipeline_manager")
        telemetry_manager = mocker.spy(pipeline_run_setup_module, "get_telemetry_manager")
        acquire_library = mocker.spy(pipeline_run_setup_module, "acquire_library")

        with pytest.raises(ValueError, match="storage_scope"):
            await pipeline_run_setup(
                storage_scope="../evil",
                user_id="test-user",
                execution_config=execution_config,
                mthds_contents=[_MINIMAL_MTHDS],
                pipe_code="echo_topic",
            )

        pipeline_manager.assert_not_called()
        acquire_library.assert_not_called()
        telemetry_manager.assert_not_called()

    async def test_the_sentinel_rebinds_to_a_validated_run_id(self, mocker: MockerFixture) -> None:
        """A caller passing the sentinel plus its own malformed run id picks the scope through the back door.

        The first gate sees only `LOCAL_STORAGE_SCOPE`, which is a valid scope, so
        this is the first look at what the scope actually became — and it still
        has to happen before the library and the tracer. Before the trace-start
        too, though that now follows `prepare_pipe_job` and so asks nothing of
        this gate.
        """
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)
        telemetry_manager = mocker.spy(pipeline_run_setup_module, "get_telemetry_manager")
        acquire_library = mocker.spy(pipeline_run_setup_module, "acquire_library")

        with pytest.raises(ValueError, match="storage_scope"):
            await pipeline_run_setup(
                storage_scope=LOCAL_STORAGE_SCOPE,
                pipeline_run_id="../escape",
                user_id="test-user",
                execution_config=execution_config,
                mthds_contents=[_MINIMAL_MTHDS],
                pipe_code="echo_topic",
            )

        acquire_library.assert_not_called()
        telemetry_manager.assert_not_called()

    async def test_the_sentinel_itself_still_passes_and_becomes_the_run_id(self) -> None:
        """The gate must not reject the sentinel: `local` is a valid one-segment scope.

        This is what makes the new gate additive rather than a behaviour change —
        a local run still gets its own run id as its scope.
        """
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)

        pipe_job, pipeline_run_id, _ = await pipeline_run_setup(
            storage_scope=LOCAL_STORAGE_SCOPE,
            user_id="test-user",
            execution_config=execution_config,
            mthds_contents=[_MINIMAL_MTHDS],
            pipe_code="echo_topic",
        )

        assert pipe_job.job_metadata.run_metadata.storage_scope == pipeline_run_id
