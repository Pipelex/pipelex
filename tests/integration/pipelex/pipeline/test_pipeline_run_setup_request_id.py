"""Integration tests for :func:`pipeline_run_setup` threading ``request_id``
onto :class:`JobMetadata`.

The ``X-Request-ID`` reaches the worker by riding the workflow input
(``arg.pipe_job.job_metadata.run_metadata.request_id``); there is no ContextVar layer. This
test pins the dispatcher-side contract: passing ``request_id`` to
``pipeline_run_setup`` produces a :class:`PipeJob` whose ``job_metadata``
carries it.
"""

import pytest

from pipelex.config import get_config
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup

_MINIMAL_MTHDS = """
domain = "request_id_test"
description = "Minimal bundle for request_id propagation test"

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
class TestPipelineRunSetupRequestId:
    async def test_request_id_threads_onto_job_metadata(self) -> None:
        """``pipeline_run_setup(..., request_id=...)`` puts the value on ``job_metadata.run_metadata.request_id``."""
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(
            generate_graph=False,
        )
        pipe_job, _, _ = await pipeline_run_setup(
            storage_scope="test/scope",
            user_id="test-user",
            execution_config=execution_config,
            mthds_contents=[_MINIMAL_MTHDS],
            pipe_code="echo_topic",
            request_id="r-pipeline-setup-abc-123",
        )
        assert pipe_job.job_metadata.run_metadata.request_id == "r-pipeline-setup-abc-123"

    async def test_request_id_absent_defaults_to_none(self) -> None:
        """Omitting ``request_id`` leaves ``job_metadata.run_metadata.request_id`` as ``None``."""
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
        assert pipe_job.job_metadata.run_metadata.request_id is None
