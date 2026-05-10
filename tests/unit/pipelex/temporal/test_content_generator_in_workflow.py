"""Unit tests for ContentGeneratorInWorkflow.

Validates that each protocol method dispatches the correct activity with the
expected kwargs, including the asymmetric ``task_queue=worker_config.inference_task_queue``
rule for ``make_llm_text`` only, the per-method default ``activity_id``, and the
runtime uniqueness check on activity_ids.
"""

from typing import Any

import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture
from temporalio.exceptions import ActivityError, ApplicationError

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.config import get_config
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.exceptions import ContentGenerationError
from pipelex.temporal.tprl_content_generation.content_generator_in_workflow import ContentGeneratorInWorkflow
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider


class _Person(BaseModel):
    name: str
    age: int


def _make_job_metadata() -> JobMetadata:
    return JobMetadata(user_id="test-user", pipeline_run_id="test-run")


def _make_generator() -> ContentGeneratorInWorkflow:
    factory = GeneratedContentFactory(storage_provider=InMemoryStorageProvider())
    return ContentGeneratorInWorkflow(generated_content_factory=factory)


def _make_llm_setting() -> LLMSetting:
    return LLMSetting(model="test-llm", temperature=0.5)


def _make_page_content() -> PageContent:
    return PageContent(text_and_images=TextAndImagesContent(text=None, images=None))


def _make_activity_error(message: str = "activity failed") -> ActivityError:
    """Construct an ``ActivityError`` with stub identifiers for tests.

    The Temporal SDK's ``ActivityError`` requires several activity-execution fields
    (scheduled_event_id, started_event_id, etc.) that tests don't care about. This
    helper fills them with stub values so the test focuses on the cause chain.
    """
    return ActivityError(
        message,
        scheduled_event_id=0,
        started_event_id=0,
        identity="test-identity",
        activity_type="test-activity",
        activity_id="test-activity-id",
        retry_state=None,
    )


@pytest.fixture
def patch_workflow_info(mocker: MockerFixture) -> str:
    """Patch ``temporalio.workflow.info()`` and ``workflow.unsafe.is_replaying()``
    so the generator's runtime checks can be exercised outside a real workflow.

    The new generator calls ``workflow.info().workflow_id`` to scope its per-run
    activity-id uniqueness set, and ``workflow.unsafe.is_replaying()`` to skip
    the check during replay. Without these patches every test would run outside
    a workflow context and the calls would error out.
    """
    workflow_id = "test-workflow"
    fake_info = mocker.MagicMock()
    fake_info.workflow_id = workflow_id
    mocker.patch("temporalio.workflow.info", return_value=fake_info)
    mocker.patch("temporalio.workflow.unsafe.is_replaying", return_value=False)
    # ``temporal_error.from_app_error`` calls ``workflow_log`` which itself checks
    # ``is_replaying_history_events()``. Patch it so the error-translation tests
    # can exercise the catch block outside a real workflow context.
    mocker.patch("temporalio.workflow.unsafe.is_replaying_history_events", return_value=False)
    return workflow_id


@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.usefixtures("patch_workflow_info")
class TestContentGeneratorInWorkflow:
    """Per-method assertions on the activity-dispatch kwargs and the runtime uniqueness check."""

    async def test_make_llm_text_passes_inference_task_queue(self, mocker: MockerFixture) -> None:
        """make_llm_text must route to ``worker_config.inference_task_queue``."""
        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.return_value = "stub text"
        generator = _make_generator()

        result = await generator.make_llm_text(
            job_metadata=_make_job_metadata(),
            llm_setting_main=_make_llm_setting(),
            llm_prompt_for_text=LLMPrompt(user_text="hello"),
        )

        assert result == "stub text"
        kwargs = mock_execute.call_args.kwargs
        worker_config = get_config().temporal.worker_config
        assert kwargs.get("task_queue") == worker_config.inference_task_queue
        assert kwargs.get("activity_id") == "craft-text"

    async def test_make_llm_text_threads_explicit_wfid(self, mocker: MockerFixture) -> None:
        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.return_value = "stub text"
        generator = _make_generator()

        await generator.make_llm_text(
            job_metadata=_make_job_metadata(),
            llm_setting_main=_make_llm_setting(),
            llm_prompt_for_text=LLMPrompt(user_text="hello"),
            wfid="custom-wfid-1",
        )

        assert mock_execute.call_args.kwargs.get("activity_id") == "custom-wfid-1"

    @pytest.mark.parametrize(
        ("method_default_id", "caller"),
        [
            ("craft-object-direct", "make_object"),
            ("craft-object-list-direct", "make_object_list"),
            ("craft-image-single", "make_single_image"),
            ("craft-image-list", "make_image_list"),
            ("jinja2-text", "make_templated_text"),
            ("render-page-views", "make_render_page_views"),
        ],
    )
    async def test_non_llm_methods_omit_inference_task_queue(
        self,
        mocker: MockerFixture,
        method_default_id: str,
        caller: str,
    ) -> None:
        """Each non-LLM-text method must NOT pass ``task_queue=`` so its activity runs
        on the workflow's own queue (mis-routing image-gen to the inference queue would
        break split-worker production where the runner doesn't register the activity).
        """
        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.return_value = self._stub_for(caller)
        generator = _make_generator()

        await self._invoke(generator, caller)

        kwargs = mock_execute.call_args.kwargs
        assert kwargs.get("task_queue") is None, f"{caller} must not pass task_queue= (got {kwargs.get('task_queue')!r})"
        assert kwargs.get("activity_id") == method_default_id

    async def test_make_extract_pages_dispatches_extract_only_when_no_page_views(self, mocker: MockerFixture) -> None:
        """When ``should_include_page_views`` is false, only the extract activity is called."""
        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.return_value = [_make_page_content()]
        generator = _make_generator()

        await generator.make_extract_pages(
            job_metadata=_make_job_metadata(),
            extract_input=ExtractInput(image_uri="test://image.png"),
            extract_handle="test-handle",
            extract_job_params=ExtractJobParams.make_default_extract_job_params(),
            extract_job_config=ExtractJobConfig(),
        )

        assert mock_execute.call_count == 1
        kwargs = mock_execute.call_args.kwargs
        assert kwargs.get("task_queue") is None
        assert kwargs.get("activity_id") == "extract-pages"

    async def test_make_extract_pages_image_uri_with_page_views_skips_render_activity(self, mocker: MockerFixture) -> None:
        """When ``image_uri`` is set and ``should_include_page_views`` is true, the
        single-image branch builds page_view inline without calling act_render_page_views.
        """
        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.return_value = [_make_page_content()]
        generator = _make_generator()

        params = ExtractJobParams.make_default_extract_job_params()
        params.should_include_page_views = True
        await generator.make_extract_pages(
            job_metadata=_make_job_metadata(),
            extract_input=ExtractInput(image_uri="test://image.png"),
            extract_handle="test-handle",
            extract_job_params=params,
            extract_job_config=ExtractJobConfig(),
        )

        # Only the extract activity should have been dispatched; the page-view branch
        # synthesizes ImageContent inline from image_uri.
        assert mock_execute.call_count == 1
        assert mock_execute.call_args.kwargs.get("activity_id") == "extract-pages"

    async def test_make_extract_pages_document_uri_with_page_views_dispatches_two_activities(self, mocker: MockerFixture) -> None:
        """When ``document_uri`` is set and ``should_include_page_views`` is true, both
        the extract and render activities are dispatched with distinct activity_ids.
        """
        page = _make_page_content()
        page_view = ImageContent(url="test://view.png")

        def _side_effect(*_args: Any, **kwargs: Any) -> Any:
            activity_id = kwargs.get("activity_id")
            if activity_id == "extract-pages":
                return [page]
            if activity_id == "extract-render-page-views":
                return [page_view]
            msg = f"Unexpected activity_id: {activity_id!r}"
            raise AssertionError(msg)

        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.side_effect = _side_effect
        generator = _make_generator()

        params = ExtractJobParams.make_default_extract_job_params()
        params.should_include_page_views = True
        result = await generator.make_extract_pages(
            job_metadata=_make_job_metadata(),
            extract_input=ExtractInput(document_uri="test://doc.pdf"),
            extract_handle="test-handle",
            extract_job_params=params,
            extract_job_config=ExtractJobConfig(),
        )

        assert mock_execute.call_count == 2
        observed_activity_ids = [call.kwargs.get("activity_id") for call in mock_execute.call_args_list]
        assert observed_activity_ids == ["extract-pages", "extract-render-page-views"]
        # Both activities must run on the workflow's own queue, not inference_task_queue.
        for call in mock_execute.call_args_list:
            assert call.kwargs.get("task_queue") is None
        assert result[0].page_view is page_view

    async def test_duplicate_wfid_raises_content_generation_error(self, mocker: MockerFixture) -> None:
        """Calling the same method twice with the same wfid must raise ContentGenerationError.

        This is the regression guard for the per-workflow uniqueness invariant on activity_ids.
        """
        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.return_value = "stub text"
        generator = _make_generator()

        await generator.make_llm_text(
            job_metadata=_make_job_metadata(),
            llm_setting_main=_make_llm_setting(),
            llm_prompt_for_text=LLMPrompt(user_text="hello"),
            wfid="duplicate-id",
        )

        with pytest.raises(ContentGenerationError) as exc_info:
            await generator.make_llm_text(
                job_metadata=_make_job_metadata(),
                llm_setting_main=_make_llm_setting(),
                llm_prompt_for_text=LLMPrompt(user_text="hello again"),
                wfid="duplicate-id",
            )

        assert "duplicate-id" in str(exc_info.value)
        assert "make_llm_text" in str(exc_info.value)

    async def test_duplicate_check_is_skipped_during_replay(self, mocker: MockerFixture) -> None:
        """During replay, ``_record_activity_id`` must short-circuit so a cached set on
        this same worker process does not produce false-positive duplicates.

        After cache eviction Temporal replays the workflow code from history on the
        same worker; the singleton generator's set still holds entries from the
        original execution. The replay path must not raise.
        """
        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.return_value = "stub text"
        generator = _make_generator()

        # First call populates the set as if on the original (non-replay) execution.
        await generator.make_llm_text(
            job_metadata=_make_job_metadata(),
            llm_setting_main=_make_llm_setting(),
            llm_prompt_for_text=LLMPrompt(user_text="hello"),
            wfid="craft-text-replay",
        )

        # Now flip into replay mode and re-call: must NOT raise.
        mocker.patch("temporalio.workflow.unsafe.is_replaying", return_value=True)
        await generator.make_llm_text(
            job_metadata=_make_job_metadata(),
            llm_setting_main=_make_llm_setting(),
            llm_prompt_for_text=LLMPrompt(user_text="hello again"),
            wfid="craft-text-replay",
        )

        assert mock_execute.call_count == 2

    async def test_activity_error_with_application_error_translates_to_temporal_error(self, mocker: MockerFixture) -> None:
        """``ActivityError(cause=ApplicationError)`` must be translated to ``TemporalError``
        with the original error_type and message preserved, chained via ``__cause__``.
        """
        from pipelex.temporal.tprl.temporal_error import TemporalError  # noqa: PLC0415

        app_error = ApplicationError("upstream failure", type="MyDomainError")
        activity_error = _make_activity_error()
        activity_error.__cause__ = app_error
        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.side_effect = activity_error
        generator = _make_generator()

        with pytest.raises(TemporalError) as exc_info:
            await generator.make_llm_text(
                job_metadata=_make_job_metadata(),
                llm_setting_main=_make_llm_setting(),
                llm_prompt_for_text=LLMPrompt(user_text="hello"),
            )

        assert exc_info.value.message == "upstream failure"
        assert exc_info.value.type == "MyDomainError"
        assert exc_info.value.__cause__ is activity_error

    async def test_activity_error_with_other_cause_re_raises_unchanged(self, mocker: MockerFixture) -> None:
        """An ``ActivityError`` whose cause is NOT ``ApplicationError`` must propagate
        unchanged — we must not silently swallow or convert non-Application failures.
        """
        non_app_cause = RuntimeError("unexpected runtime error")
        activity_error = _make_activity_error()
        activity_error.__cause__ = non_app_cause
        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.side_effect = activity_error
        generator = _make_generator()

        with pytest.raises(ActivityError) as exc_info:
            await generator.make_llm_text(
                job_metadata=_make_job_metadata(),
                llm_setting_main=_make_llm_setting(),
                llm_prompt_for_text=LLMPrompt(user_text="hello"),
            )

        assert exc_info.value is activity_error

    async def test_default_wfids_for_image_methods_are_distinct(self, mocker: MockerFixture) -> None:
        """make_single_image and make_image_list must use distinct default activity_ids
        so a future call site invoking both within the same workflow does not collide.

        Pre-collapse, both defaulted to ``"craft-image"``; the new generator splits them
        into ``"craft-image-single"`` / ``"craft-image-list"``.
        """

        def _side_effect(*_args: Any, **_kwargs: Any) -> Any:
            return [ImageContent(url="test://img.png")]

        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.side_effect = _side_effect
        generator = _make_generator()

        await generator.make_single_image(
            job_metadata=_make_job_metadata(),
            img_gen_handle="test-handle",
            img_gen_prompt=ImgGenPrompt(positive_text="prompt"),
        )
        await generator.make_image_list(
            job_metadata=_make_job_metadata(),
            img_gen_handle="test-handle",
            img_gen_prompt=ImgGenPrompt(positive_text="prompt"),
            nb_images=2,
        )

        observed_activity_ids = [call.kwargs.get("activity_id") for call in mock_execute.call_args_list]
        assert observed_activity_ids == ["craft-image-single", "craft-image-list"]

    @staticmethod
    def _stub_for(caller: str) -> Any:
        """Return a stub return value matching the activity's contract for each method."""
        if caller == "make_object":
            return _Person(name="John", age=30)
        if caller == "make_object_list":
            return [_Person(name="John", age=30)]
        if caller == "make_single_image":
            return [ImageContent(url="test://img.png")]
        if caller == "make_image_list":
            return [ImageContent(url="test://img1.png"), ImageContent(url="test://img2.png")]
        if caller == "make_templated_text":
            return "rendered"
        if caller == "make_render_page_views":
            return [ImageContent(url="test://view.png")]
        msg = f"Unknown caller: {caller}"
        raise AssertionError(msg)

    @staticmethod
    async def _invoke(generator: ContentGeneratorInWorkflow, caller: str) -> Any:
        """Invoke the named method on the generator with reasonable default args."""
        job_metadata = _make_job_metadata()
        if caller == "make_object":
            return await generator.make_object(
                job_metadata=job_metadata,
                object_class=_Person,
                llm_setting_for_object=_make_llm_setting(),
                llm_prompt_for_object=LLMPrompt(user_text="hello"),
            )
        if caller == "make_object_list":
            return await generator.make_object_list(
                job_metadata=job_metadata,
                object_class=_Person,
                llm_setting_for_object_list=_make_llm_setting(),
                llm_prompt_for_object_list=LLMPrompt(user_text="hello"),
            )
        if caller == "make_single_image":
            return await generator.make_single_image(
                job_metadata=job_metadata,
                img_gen_handle="test-handle",
                img_gen_prompt=ImgGenPrompt(positive_text="prompt"),
            )
        if caller == "make_image_list":
            return await generator.make_image_list(
                job_metadata=job_metadata,
                img_gen_handle="test-handle",
                img_gen_prompt=ImgGenPrompt(positive_text="prompt"),
                nb_images=2,
            )
        if caller == "make_templated_text":
            return await generator.make_templated_text(
                job_metadata=job_metadata,
                context={"key": "value"},
                template="{{ key }}",
            )
        if caller == "make_render_page_views":
            return await generator.make_render_page_views(
                job_metadata=job_metadata,
                extract_input=ExtractInput(document_uri="test://doc.pdf"),
                extract_handle="test-handle",
            )
        msg = f"Unknown caller: {caller}"
        raise AssertionError(msg)
