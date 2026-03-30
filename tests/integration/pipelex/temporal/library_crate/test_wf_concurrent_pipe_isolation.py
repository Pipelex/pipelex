"""Concurrent pipe isolation tests for Temporal workflows.

Validates that two workflows running simultaneously on the same worker each load
their own LibraryCrate and resolve pipe_refs through per-workflow library scoping
(via ContextVar). Alpha's pipes (about colors) and beta's pipes (about animals)
live in separate domains and are resolved independently on each workflow.

┌──────────────────────────────────────────────────────────────┐
│                    Temporal Test Server (in-process)          │
├──────────────────────────────────────────────────────────────┤
│  ┌──────────────── Worker (shared) ────────────────────────┐ │
│  │  ┌─ Workflow A ─────────────┐ ┌─ Workflow B ──────────┐ │ │
│  │  │ domain: pipe_conflict_a  │ │ domain: pipe_conflict_b│ │ │
│  │  │   alpha_shared_step:     │ │   beta_shared_step:    │ │ │
│  │  │     prompt: about colors │ │     prompt: about animals│ │
│  │  │                          │ │                        │ │ │
│  │  │ Library A (ContextVar)   │ │ Library B (ContextVar) │ │ │
│  │  └──────────────────────────┘ └────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
"""

import asyncio
import uuid

import pytest
from temporalio.client import Client as TemporalClient

from pipelex import log
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.temporal.temporal_hub import get_task_manager
from tests.integration.pipelex.temporal.library_crate.helpers import assert_text_stuff_names, execute_workflow
from tests.integration.pipelex.temporal.test_data import ConflictPipeAlphaTestData, ConflictPipeBetaTestData


@pytest.mark.temporal
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestWfConcurrentPipeIsolation:
    async def test_pipe_alpha_solo(
        self,
        pipe_run_mode: PipeRunMode,
        alpha_pipe_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Alpha pipeline alone: shared_step should generate text about colors."""
        task_queue = str(uuid.uuid4())
        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            output = await execute_workflow(alpha_pipe_job, temporal_client, task_queue)

        assert_text_stuff_names(output, ConflictPipeAlphaTestData.EXPECTED_STUFF_NAMES)
        log.info(f"Pipe alpha solo passed (mode={pipe_run_mode})")

    async def test_pipe_beta_solo(
        self,
        pipe_run_mode: PipeRunMode,
        beta_pipe_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Beta pipeline alone: shared_step should generate text about animals."""
        task_queue = str(uuid.uuid4())
        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            output = await execute_workflow(beta_pipe_job, temporal_client, task_queue)

        assert_text_stuff_names(output, ConflictPipeBetaTestData.EXPECTED_STUFF_NAMES)
        log.info(f"Pipe beta solo passed (mode={pipe_run_mode})")

    async def test_concurrent_pipe_resolution(
        self,
        pipe_run_mode: PipeRunMode,
        alpha_pipe_job: PipeJob,
        beta_pipe_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Both pipelines run simultaneously on the same worker.

        Each defines pipe 'shared_step' with a different prompt. Without per-workflow
        library scoping, get_required_pipe('shared_step') could resolve the wrong one.
        """
        task_queue = str(uuid.uuid4())
        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            alpha_output, beta_output = await asyncio.gather(
                execute_workflow(alpha_pipe_job, temporal_client, task_queue),
                execute_workflow(beta_pipe_job, temporal_client, task_queue),
            )

        assert_text_stuff_names(alpha_output, ConflictPipeAlphaTestData.EXPECTED_STUFF_NAMES)
        assert_text_stuff_names(beta_output, ConflictPipeBetaTestData.EXPECTED_STUFF_NAMES)

        log.info(f"Concurrent pipe isolation passed (mode={pipe_run_mode})")

    async def test_repeated_concurrent_pipe_resolution(
        self,
        pipe_run_mode: PipeRunMode,
        alpha_pipe_job: PipeJob,
        beta_pipe_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Run the concurrent test 5 times to catch intermittent race conditions."""
        task_queue = str(uuid.uuid4())
        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            for round_index in range(5):
                alpha_output, beta_output = await asyncio.gather(
                    execute_workflow(alpha_pipe_job, temporal_client, task_queue),
                    execute_workflow(beta_pipe_job, temporal_client, task_queue),
                )

                assert_text_stuff_names(alpha_output, ConflictPipeAlphaTestData.EXPECTED_STUFF_NAMES)
                assert_text_stuff_names(beta_output, ConflictPipeBetaTestData.EXPECTED_STUFF_NAMES)
                log.verbose(f"Round {round_index + 1}/5 passed")

        log.info(f"Repeated concurrent pipe isolation passed (mode={pipe_run_mode})")
