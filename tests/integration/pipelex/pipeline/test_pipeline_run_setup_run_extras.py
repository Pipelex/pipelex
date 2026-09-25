"""Integration tests for :func:`pipeline_run_setup` threading ``extras``
onto :class:`JobMetadata`.

The extras ride the ``PipeJob``
(``arg.pipe_job.job_metadata.run_metadata.extras``) — the same payload-first
route ``request_id`` takes, and for the same reason: there is no ContextVar layer
and the worker on the far side of a Temporal hop rehydrates the whole job. The
PostHog exporters read them back off the span attributes; this test pins the
dispatcher-side contract, which is what the hosted runner will call once it
accepts the field on the wire.

It also pins WHERE the refusal happens. Validation sits above
``add_new_pipeline`` deliberately: a malformed mapping must not register a run.
Asserting only that a ``ValueError`` escapes would pass with the validation at
the bottom of ``prepare_pipe_job``, which is where it used to be. It sits above
``handle_trace_start`` too, but that clause no longer distinguishes anything —
the trace-start has since moved below ``prepare_pipe_job``, so every gate in
this function precedes it.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.pipeline import pipeline_run_setup as pipeline_run_setup_module
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup

_MINIMAL_MTHDS = """
domain = "extras_test"
description = "Minimal bundle for extras propagation test"

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
class TestPipelineRunSetupRunExtras:
    async def test_run_extras_thread_onto_job_metadata(self) -> None:
        """``pipeline_run_setup(..., extras=...)`` puts them on ``job_metadata.run_metadata``."""
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(
            generate_graph=False,
        )
        pipe_job, _, _ = await pipeline_run_setup(
            storage_scope="test/scope",
            user_id="test-user",
            execution_config=execution_config,
            mthds_contents=[_MINIMAL_MTHDS],
            pipe_code="echo_topic",
            extras={"organization": "org_acme"},
        )
        assert pipe_job.job_metadata.run_metadata.extras == {"organization": "org_acme"}

    async def test_omitting_them_leaves_an_empty_mapping(self) -> None:
        """Every existing caller omits the field, and an omission is an empty group facet, not an error."""
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(
            generate_graph=False,
        )
        pipe_job, _, _ = await pipeline_run_setup(
            storage_scope="test/scope",
            user_id="test-user",
            execution_config=execution_config,
            mthds_contents=[_MINIMAL_MTHDS],
            pipe_code="echo_topic",
        )
        assert pipe_job.job_metadata.run_metadata.extras == {}

    async def test_malformed_extras_are_refused_before_the_run_starts(self) -> None:
        """The validator on the field is what makes a bad mapping fail at setup rather than at capture."""
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(
            generate_graph=False,
        )
        with pytest.raises(ValueError, match="extras"):
            await pipeline_run_setup(
                storage_scope="test/scope",
                user_id="test-user",
                execution_config=execution_config,
                mthds_contents=[_MINIMAL_MTHDS],
                pipe_code="echo_topic",
                extras={"Organization": "org_acme"},
            )

    async def test_the_refusal_registers_no_run_and_emits_no_trace_start(self, mocker: MockerFixture) -> None:
        """A rejected mapping must leave NOTHING behind — not a pipeline entry, not a telemetry event.

        The teardown can release a registered pipeline and an opened tracer; it cannot
        unsend a ``handle_trace_start`` that already reached the backend. The pipeline
        half is what bites today: ``add_new_pipeline`` runs above ``prepare_pipe_job``,
        so this test fails if the gate is moved back down there, where the mapping was
        first validated. The telemetry half is now satisfied by the ordering whatever
        the gate does — the trace-start sits below ``prepare_pipe_job`` — and stays as a
        guard against that ordering moving back.
        """
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(
            generate_graph=False,
        )
        # SPIES, not stubs: they call through, so this test fails on the assertion
        # below rather than on some mock artifact tripping a constructor first.
        pipeline_manager = mocker.spy(pipeline_run_setup_module, "get_pipeline_manager")
        telemetry_manager = mocker.spy(pipeline_run_setup_module, "get_telemetry_manager")

        with pytest.raises(ValueError, match="extras"):
            await pipeline_run_setup(
                storage_scope="test/scope",
                user_id="test-user",
                execution_config=execution_config,
                mthds_contents=[_MINIMAL_MTHDS],
                pipe_code="echo_topic",
                extras={"Organization": "org_acme"},
            )

        pipeline_manager.assert_not_called()
        telemetry_manager.assert_not_called()
