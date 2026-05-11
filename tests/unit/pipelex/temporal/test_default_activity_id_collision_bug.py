"""Failing test pinning the activity-id collision bug.

Background: ``ContentGeneratorInWorkflow`` methods default ``activity_id`` to a
constant per-method label (e.g. ``"craft-text"``) when no ``wfid`` is passed.
Temporal requires ``activity_id`` to be unique within a single workflow
execution, so any workflow that calls the same method twice in a row crashes
on the second call. This is a structural bug — calling a content-generator
method twice is an ordinary pattern, not an error.

These tests assert the *desired* behavior: two back-to-back calls (either
both with no ``wfid``, or both with the same explicit ``wfid``) must succeed.
With the current default-constant scheme they fail, because
``_record_activity_id`` raises ``ContentGenerationError`` on the duplicate.

After the activity-id naming redesign (see
``wip/temporal-primitives/workflow-and-activity-ids.md``), these tests must
pass without re-introducing the duplicate collision via some other path.
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


@pytest.fixture
def patch_workflow_info(mocker: MockerFixture) -> None:
    """Patch ``temporalio.workflow.info()`` and ``workflow.unsafe.is_replaying()``
    so ``_record_activity_id`` can be exercised outside a real workflow context.

    Mirrors the pattern in ``test_content_generator_in_workflow.py`` — both calls
    happen under the same ``(workflow_id, run_id)`` key so the per-run uniqueness
    guard treats them as belonging to the same execution.
    """
    fake_info = mocker.MagicMock()
    fake_info.workflow_id = "test-workflow"
    fake_info.run_id = "test-run-id-1"
    mocker.patch("temporalio.workflow.info", return_value=fake_info)
    mocker.patch("temporalio.workflow.unsafe.is_replaying", return_value=False)


@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.usefixtures("patch_workflow_info")
class TestDefaultActivityIdCollisionBug:
    async def test_two_make_llm_text_calls_without_wfid_should_succeed(self, mocker: MockerFixture) -> None:
        """Two ``make_llm_text`` calls in the same workflow with no ``wfid`` must succeed.

        Today both default to ``activity_id="craft-text"`` and the second call
        raises ``ContentGenerationError("Duplicate activity_id 'craft-text' ...")``
        from ``_record_activity_id``. That makes a trivially common pattern —
        two LLM text generations inside one workflow — impossible at the
        default call site. The redesign must produce a per-call disambiguator
        (deterministic across replay) so this scenario works.
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
        observed_activity_ids = [call.kwargs.get("activity_id") for call in mock_execute.call_args_list]
        assert len(set(observed_activity_ids)) == 2, (
            f"Both calls produced the same activity_id ({observed_activity_ids!r}); Temporal requires per-(workflow_id, run_id) uniqueness."
        )

    async def test_two_make_llm_text_calls_with_same_explicit_wfid_should_succeed(self, mocker: MockerFixture) -> None:
        """Two ``make_llm_text`` calls with the same explicit ``wfid`` must succeed.

        Today this raises — the same string is used as ``activity_id`` both
        times. This proves ``wfid`` is not a usable disambiguator: it carries
        one id per call site, not one id per call. A single ``wfid`` value
        cannot disambiguate two invocations of the same method in the same
        workflow. The redesign must decouple the per-call ``activity_id`` from
        the (workflow-id-base) ``wfid`` parameter.
        """
        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.return_value = "stub text"
        generator = _make_generator()

        await generator.make_llm_text(
            job_metadata=_make_job_metadata(),
            llm_setting_main=_make_llm_setting(),
            llm_prompt_for_text=LLMPrompt(user_text="hello"),
            wfid="same-string",
        )
        await generator.make_llm_text(
            job_metadata=_make_job_metadata(),
            llm_setting_main=_make_llm_setting(),
            llm_prompt_for_text=LLMPrompt(user_text="hello again"),
            wfid="same-string",
        )

        assert mock_execute.call_count == 2
        observed_activity_ids = [call.kwargs.get("activity_id") for call in mock_execute.call_args_list]
        assert len(set(observed_activity_ids)) == 2, (
            f"Both calls produced the same activity_id ({observed_activity_ids!r}); ``wfid`` cannot be the per-call disambiguator."
        )
