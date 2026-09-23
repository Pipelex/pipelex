"""The pipe execution span carries the run's identity.

The companion of the LLM-span unit test, but driven through a real library: the
pipe comes out of ``pipeline_run_setup``, so this pins the whole dispatcher-side
route — the groups the caller supplied reach ``RunMetadata``, and the span site
reads them off it — rather than a hand-built metadata object.
"""

from typing import Any

import pytest
from opentelemetry.sdk.trace import Span as SdkSpan
from opentelemetry.sdk.trace import TracerProvider
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.system.job_metadata import OtelContext
from pipelex.system.telemetry.otel_constants import LangfuseSpanAttr, OTelConstants, PipelexSpanAttr
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract

_MINIMAL_MTHDS = """
domain = "pipe_span_identity_test"
description = "Minimal bundle for pipe-span identity test"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = { type = "text", description = "Topic name" }

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used only to build a span"
inputs = { subject = "Text" }
output = "Topic"
prompt = "Echo the $subject as a topic"
"""

_PARENT_OTEL_CONTEXT = OtelContext(
    trace_id=1234,
    trace_name="echo_topic_abc12345",
    trace_name_redacted="abc12345",
    span_id=OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID,
)


async def _make_pipe_job(*, analytics_groups: dict[str, str] | None = None) -> PipeJob:
    execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)
    pipe_job, _, _ = await pipeline_run_setup(
        storage_scope="test/scope",
        user_id="user-42",
        execution_config=execution_config,
        mthds_contents=[_MINIMAL_MTHDS],
        pipe_code="echo_topic",
        analytics_groups=analytics_groups,
        inputs={"subject": "a subject"},
    )
    return pipe_job


def _start_span(*, mocker: MockerFixture, pipe_job: PipeJob) -> SdkSpan:
    mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=TracerProvider().get_tracer("test"))
    span, _ = pipe_job.pipe._start_pipe_span(  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
        parent_otel_context=_PARENT_OTEL_CONTEXT,
        run_metadata=pipe_job.job_metadata.run_metadata,
        working_memory=pipe_job.get_working_memory(),
    )
    assert isinstance(span, SdkSpan)
    return span


def _attributes(span: SdkSpan) -> dict[str, Any]:
    return dict(span.attributes or {})


@pytest.mark.asyncio(loop_scope="class")
class TestPipeSpanIdentity:
    async def test_the_span_names_the_runs_user(self, mocker: MockerFixture) -> None:
        pipe_job = await _make_pipe_job()

        assert _attributes(_start_span(mocker=mocker, pipe_job=pipe_job))[PipelexSpanAttr.RUN_USER_ID] == "user-42"

    async def test_the_groups_the_caller_supplied_reach_the_span(self, mocker: MockerFixture) -> None:
        pipe_job = await _make_pipe_job(analytics_groups={"organization": "org_acme"})

        attributes = _attributes(_start_span(mocker=mocker, pipe_job=pipe_job))
        assert attributes[PipelexSpanAttr.RUN_ANALYTICS_GROUPS] == '{"organization": "org_acme"}'

    async def test_a_run_with_no_groups_writes_no_groups_attribute(self, mocker: MockerFixture) -> None:
        pipe_job = await _make_pipe_job()

        assert PipelexSpanAttr.RUN_ANALYTICS_GROUPS not in _attributes(_start_span(mocker=mocker, pipe_job=pipe_job))

    async def test_langfuse_gets_the_user_id_when_it_is_enabled(self, mocker: MockerFixture) -> None:
        pipe_job = await _make_pipe_job()
        mocker.patch.object(TelemetryManagerAbstract, "get_langfuse_enabled", return_value=True)

        assert _attributes(_start_span(mocker=mocker, pipe_job=pipe_job))[LangfuseSpanAttr.USER_ID] == "user-42"
