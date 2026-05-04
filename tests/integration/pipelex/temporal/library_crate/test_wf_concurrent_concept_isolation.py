"""Concurrent concept isolation tests for Temporal workflows.

Validates that two workflows running simultaneously on the same worker can each
define a concept called 'Result' with incompatible structures, and the per-workflow
ClassRegistry scoping (via ContextVar) keeps them isolated.

Without proper scoping, the bare class name 'Result' would collide in the registry,
causing one workflow to deserialize with the wrong field structure — a silent data
corruption bug.

┌──────────────────────────────────────────────────────────────┐
│                    Temporal Test Server (in-process)          │
├──────────────────────────────────────────────────────────────┤
│  ┌──────────────── Worker (shared) ────────────────────────┐ │
│  │  ┌─ Workflow A ─────────────┐ ┌─ Workflow B ─────────┐ │ │
│  │  │ concept "Result":        │ │ concept "Result":     │ │ │
│  │  │   score: int             │ │   value: text         │ │ │
│  │  │   label: text            │ │   confidence: number  │ │ │
│  │  │                          │ │   is_valid: text      │ │ │
│  │  │ ClassRegistry A (scoped) │ │ ClassRegistry B       │ │ │
│  │  └──────────────────────────┘ └───────────────────────┘ │ │
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
from tests.integration.pipelex.temporal.library_crate.helpers import (
    assert_structured_fields,
    assert_stuff_names,
    assert_text_stuff_names,
    execute_workflow,
)
from tests.integration.pipelex.temporal.test_data import ConflictConceptAlphaTestData, ConflictConceptBetaTestData


@pytest.mark.temporal
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestWfConcurrentConceptIsolation:
    async def test_alpha_solo(
        self,
        pipe_run_mode: PipeRunMode,
        alpha_concept_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Alpha pipeline alone: Result should have score and label fields."""
        task_queue = str(uuid.uuid4())
        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            output = await execute_workflow(alpha_concept_job, temporal_client, task_queue)

        assert_stuff_names(output, ConflictConceptAlphaTestData.EXPECTED_STUFF_NAMES)
        assert_structured_fields(output, "alpha_result", ConflictConceptAlphaTestData.EXPECTED_RESULT_FIELDS)
        log.info(f"Alpha solo passed (mode={pipe_run_mode})")

    async def test_beta_solo(
        self,
        pipe_run_mode: PipeRunMode,
        beta_concept_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Beta pipeline alone: Result should have value, confidence, and is_valid fields."""
        task_queue = str(uuid.uuid4())
        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            output = await execute_workflow(beta_concept_job, temporal_client, task_queue)

        assert_stuff_names(output, ConflictConceptBetaTestData.EXPECTED_STUFF_NAMES)
        assert_structured_fields(output, "beta_result", ConflictConceptBetaTestData.EXPECTED_RESULT_FIELDS)
        log.info(f"Beta solo passed (mode={pipe_run_mode})")

    async def test_concurrent_different_results(
        self,
        pipe_run_mode: PipeRunMode,
        alpha_concept_job: PipeJob,
        beta_concept_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Both pipelines run simultaneously on the same worker.

        Each defines concept 'Result' with different fields. Without per-workflow
        ClassRegistry scoping, one would overwrite the other in the registry.
        """
        task_queue = str(uuid.uuid4())
        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            alpha_output, beta_output = await asyncio.gather(
                execute_workflow(alpha_concept_job, temporal_client, task_queue),
                execute_workflow(beta_concept_job, temporal_client, task_queue),
            )

        # Alpha: Result has score + label
        assert_stuff_names(alpha_output, ConflictConceptAlphaTestData.EXPECTED_STUFF_NAMES)
        assert_structured_fields(alpha_output, "alpha_result", ConflictConceptAlphaTestData.EXPECTED_RESULT_FIELDS)

        # Beta: Result has value + confidence + is_valid
        assert_stuff_names(beta_output, ConflictConceptBetaTestData.EXPECTED_STUFF_NAMES)
        assert_structured_fields(beta_output, "beta_result", ConflictConceptBetaTestData.EXPECTED_RESULT_FIELDS)

        # Verify summary outputs are TextContent
        assert_text_stuff_names(alpha_output, ["alpha_summary"])
        assert_text_stuff_names(beta_output, ["beta_summary"])

        log.info(f"Concurrent concept isolation passed (mode={pipe_run_mode})")

    async def test_repeated_concurrent(
        self,
        pipe_run_mode: PipeRunMode,
        alpha_concept_job: PipeJob,
        beta_concept_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Run the concurrent test 5 times to catch intermittent ContextVar race conditions."""
        task_queue = str(uuid.uuid4())
        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            for round_index in range(5):
                alpha_output, beta_output = await asyncio.gather(
                    execute_workflow(alpha_concept_job, temporal_client, task_queue),
                    execute_workflow(beta_concept_job, temporal_client, task_queue),
                )

                assert_structured_fields(alpha_output, "alpha_result", ConflictConceptAlphaTestData.EXPECTED_RESULT_FIELDS)
                assert_structured_fields(beta_output, "beta_result", ConflictConceptBetaTestData.EXPECTED_RESULT_FIELDS)
                log.verbose(f"Round {round_index + 1}/5 passed")

        log.info(f"Repeated concurrent concept isolation passed (mode={pipe_run_mode})")
