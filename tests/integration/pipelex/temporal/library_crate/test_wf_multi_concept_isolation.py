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
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.temporal.temporal_hub import get_task_manager
from tests.integration.pipelex.temporal.library_crate.helpers import (
    assert_structured_fields,
    assert_stuff_names,
    assert_text_stuff_names,
    execute_workflow,
)
from tests.integration.pipelex.temporal.test_data import MultiConceptAlphaTestData, MultiConceptBetaTestData


def _assert_alpha_output(output: PipeOutput) -> None:
    """Assert alpha pipeline produced Profile(name, age) + Summary(headline, body) + Text."""
    assert_stuff_names(output, MultiConceptAlphaTestData.EXPECTED_STUFF_NAMES)
    assert_structured_fields(output, "profile_result", MultiConceptAlphaTestData.EXPECTED_PROFILE_FIELDS)
    assert_structured_fields(output, "summary_result", MultiConceptAlphaTestData.EXPECTED_SUMMARY_FIELDS)
    assert_text_stuff_names(output, ["final_result"])


def _assert_beta_output(output: PipeOutput) -> None:
    """Assert beta pipeline produced Profile(title, department, level) + Summary(content) + Text."""
    assert_stuff_names(output, MultiConceptBetaTestData.EXPECTED_STUFF_NAMES)
    assert_structured_fields(output, "profile_result", MultiConceptBetaTestData.EXPECTED_PROFILE_FIELDS)
    assert_structured_fields(output, "summary_result", MultiConceptBetaTestData.EXPECTED_SUMMARY_FIELDS)
    assert_text_stuff_names(output, ["final_result"])


@pytest.mark.temporal
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestWfMultiConceptIsolation:
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

        _assert_alpha_output(output)
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

        _assert_beta_output(output)
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

        _assert_alpha_output(alpha_output)
        _assert_beta_output(beta_output)

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
            _assert_alpha_output(results[index])
        for index in (1, 3, 5):
            _assert_beta_output(results[index])

        log.info(f"High concurrency multi-concept isolation passed (mode={pipe_run_mode})")
