"""Multi-concept isolation stress tests for Temporal workflows.

Validates the worst-case scenario: two workflows running simultaneously on the same
worker, each defining MULTIPLE dynamic concepts with the SAME names but incompatible
structures. This exercises the full ClassRegistry scoping path under maximum pressure.

Both workflows define 'Profile' and 'Summary' concepts but with completely different
field structures. If the per-workflow ClassRegistry scoping (via ContextVar) fails,
one workflow's Profile class could be used to deserialize the other's — silently
returning wrong data without any error.

┌──────────────────────────────────────────────────────────────┐
│                    Temporal Test Server (in-process)          │
├──────────────────────────────────────────────────────────────┤
│  ┌──────────────── Worker (shared) ────────────────────────┐ │
│  │  ┌─ Workflow A ─────────────┐ ┌─ Workflow B ─────────┐ │ │
│  │  │ "Profile":               │ │ "Profile":            │ │ │
│  │  │   name: text             │ │   title: text         │ │ │
│  │  │   age: integer           │ │   department: text    │ │ │
│  │  │                          │ │   level: integer      │ │ │
│  │  │ "Summary":               │ │ "Summary":            │ │ │
│  │  │   headline: text         │ │   content: text       │ │ │
│  │  │   body: text             │ │                       │ │ │
│  │  └──────────────────────────┘ └───────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
"""

import asyncio
import uuid

import pytest
from temporalio.client import Client as TemporalClient

from pipelex import log
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.temporal.temporal_hub import get_task_manager
from tests.integration.pipelex.temporal.library_crate.helpers import execute_workflow
from tests.integration.pipelex.temporal.test_data import MultiConceptAlphaTestData, MultiConceptBetaTestData


@pytest.mark.temporal
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestWfMultiConceptIsolation:
    @staticmethod
    def _assert_alpha_output(output: PipeOutput) -> None:
        """Assert alpha pipeline produced Profile(name, age) + Summary(headline, body) + Text."""
        working_memory = output.working_memory
        assert working_memory is not None

        for stuff_name in MultiConceptAlphaTestData.EXPECTED_STUFF_NAMES:
            assert working_memory.is_stuff_exists(stuff_name), f"Expected stuff '{stuff_name}' missing"

        # Profile: name + age
        profile_stuff = working_memory.get_stuff("profile_result")
        assert isinstance(profile_stuff.content, StructuredContent)
        for field in MultiConceptAlphaTestData.EXPECTED_PROFILE_FIELDS:
            assert hasattr(profile_stuff.content, field), f"Alpha Profile missing '{field}'"

        # Summary: headline + body
        summary_stuff = working_memory.get_stuff("summary_result")
        assert isinstance(summary_stuff.content, StructuredContent)
        for field in MultiConceptAlphaTestData.EXPECTED_SUMMARY_FIELDS:
            assert hasattr(summary_stuff.content, field), f"Alpha Summary missing '{field}'"

        # Final: Text
        final_stuff = working_memory.get_stuff("final_result")
        assert isinstance(final_stuff.content, TextContent)

    @staticmethod
    def _assert_beta_output(output: PipeOutput) -> None:
        """Assert beta pipeline produced Profile(title, department, level) + Summary(content) + Text."""
        working_memory = output.working_memory
        assert working_memory is not None

        for stuff_name in MultiConceptBetaTestData.EXPECTED_STUFF_NAMES:
            assert working_memory.is_stuff_exists(stuff_name), f"Expected stuff '{stuff_name}' missing"

        # Profile: title + department + level
        profile_stuff = working_memory.get_stuff("profile_result")
        assert isinstance(profile_stuff.content, StructuredContent)
        for field in MultiConceptBetaTestData.EXPECTED_PROFILE_FIELDS:
            assert hasattr(profile_stuff.content, field), f"Beta Profile missing '{field}'"

        # Summary: content
        summary_stuff = working_memory.get_stuff("summary_result")
        assert isinstance(summary_stuff.content, StructuredContent)
        for field in MultiConceptBetaTestData.EXPECTED_SUMMARY_FIELDS:
            assert hasattr(summary_stuff.content, field), f"Beta Summary missing '{field}'"

        # Final: Text
        final_stuff = working_memory.get_stuff("final_result")
        assert isinstance(final_stuff.content, TextContent)

    async def test_multi_alpha_solo(
        self,
        pipe_run_mode: PipeRunMode,
        multi_alpha_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Alpha pipeline alone: Profile(name, age) + Summary(headline, body)."""
        task_queue = str(uuid.uuid4())
        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            output = await execute_workflow(multi_alpha_job, temporal_client, task_queue)

        self._assert_alpha_output(output)
        log.info(f"Multi-concept alpha solo passed (mode={pipe_run_mode})")

    async def test_multi_beta_solo(
        self,
        pipe_run_mode: PipeRunMode,
        multi_beta_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Beta pipeline alone: Profile(title, department, level) + Summary(content)."""
        task_queue = str(uuid.uuid4())
        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            output = await execute_workflow(multi_beta_job, temporal_client, task_queue)

        self._assert_beta_output(output)
        log.info(f"Multi-concept beta solo passed (mode={pipe_run_mode})")

    async def test_concurrent_multi_concept(
        self,
        pipe_run_mode: PipeRunMode,
        multi_alpha_job: PipeJob,
        multi_beta_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Both pipelines run simultaneously with conflicting Profile and Summary classes.

        This is the worst-case scenario: two dynamic classes with the same name ('Profile')
        and two more ('Summary') coexist on the same worker. Without scoping, alpha's
        Profile(name, age) could be used to deserialize beta's Profile(title, department, level).
        """
        task_queue = str(uuid.uuid4())
        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            alpha_output, beta_output = await asyncio.gather(
                execute_workflow(multi_alpha_job, temporal_client, task_queue),
                execute_workflow(multi_beta_job, temporal_client, task_queue),
            )

        self._assert_alpha_output(alpha_output)
        self._assert_beta_output(beta_output)

        log.info(f"Concurrent multi-concept isolation passed (mode={pipe_run_mode})")

    async def test_high_concurrency_multi_concept(
        self,
        pipe_run_mode: PipeRunMode,
        multi_alpha_job: PipeJob,
        multi_beta_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Run 3 pairs concurrently (6 workflows) to stress ContextVar scoping.

        Exercises the scenario where many workflow coroutines are interleaved on the
        same worker, maximizing the chance of ContextVar leaking between them.
        """
        task_queue = str(uuid.uuid4())
        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            results = await asyncio.gather(
                execute_workflow(multi_alpha_job, temporal_client, task_queue),
                execute_workflow(multi_beta_job, temporal_client, task_queue),
                execute_workflow(multi_alpha_job, temporal_client, task_queue),
                execute_workflow(multi_beta_job, temporal_client, task_queue),
                execute_workflow(multi_alpha_job, temporal_client, task_queue),
                execute_workflow(multi_beta_job, temporal_client, task_queue),
            )

        # results[0], [2], [4] are alpha; [1], [3], [5] are beta
        for index in (0, 2, 4):
            self._assert_alpha_output(results[index])
        for index in (1, 3, 5):
            self._assert_beta_output(results[index])

        log.info(f"High concurrency multi-concept isolation passed (mode={pipe_run_mode})")
