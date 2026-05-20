"""Canonical regression gate for the activity-id collision bug.

Background: ``ContentGeneratorInWorkflow`` used to default ``activity_id`` to a
constant per-method label (e.g. ``"craft-text"``). Temporal requires
``activity_id`` to be unique within a single workflow execution, so any
workflow that called the same method twice in a row crashed on the second
call.

After the activity-id naming redesign (see
``wip/temporal-primitives/id-and-naming-design.md``), Pipelex never passes
``activity_id=``: the Temporal Python SDK auto-assigns deterministic
sequential integers per workflow run. This test pins the invariant —
``activity_id`` is omitted from the dispatch kwargs — and trusts the SDK to
produce unique-per-run ids by construction.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.tprl_content_generation.content_generator_in_workflow import ContentGeneratorInWorkflow
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider


def _make_job_metadata() -> JobMetadata:
    return JobMetadata(user_id="test-user", pipeline_run_id="test-run")


def _make_generator() -> ContentGeneratorInWorkflow:
    factory = GeneratedContentFactory(storage_provider=InMemoryStorageProvider())
    return ContentGeneratorInWorkflow(generated_content_factory=factory)


def _make_llm_setting() -> LLMSetting:
    return LLMSetting(model="test-llm", temperature=0.5)


@pytest.mark.asyncio(loop_scope="class")
class TestDefaultActivityIdCollisionBug:
    async def test_two_default_activity_calls_in_one_workflow_produce_distinct_activity_ids(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Two back-to-back ``make_llm_text`` calls in the same workflow must
        dispatch without colliding on ``activity_id``.

        The redesign satisfies this by never passing ``activity_id=`` — the
        Temporal SDK assigns deterministic sequential integers per workflow
        run, which guarantees per-``(workflow_id, run_id)`` uniqueness by
        construction and is replay-safe (assigned by history position).
        """
        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.return_value = "stub text"
        generator = _make_generator()

        await generator.make_llm_text(
            job_metadata=_make_job_metadata(),
            llm_setting_main=_make_llm_setting(),
            llm_prompt_for_text=LLMPrompt(user_text="hello"),
        )
        await generator.make_llm_text(
            job_metadata=_make_job_metadata(),
            llm_setting_main=_make_llm_setting(),
            llm_prompt_for_text=LLMPrompt(user_text="hello again"),
        )

        assert mock_execute.call_count == 2
        for call in mock_execute.call_args_list:
            assert call.kwargs.get("activity_id") is None, (
                "Pipelex must not customize activity_id — the SDK assigns deterministic integers per workflow run."
            )
