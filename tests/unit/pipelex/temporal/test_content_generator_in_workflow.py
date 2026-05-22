"""Unit tests for ContentGeneratorInWorkflow.

Validates that each protocol method dispatches the correct activity with the
expected kwargs, including the hybrid ``task_queue`` routing via
``WorkerConfig.resolve_dispatch`` (empty ``activity_queues`` → omit
``task_queue`` so Temporal routes to the workflow's queue), and that
Pipelex never customizes ``activity_id`` (the SDK assigns deterministic
integers per workflow run).

Per-call meaning is carried in the ``summary=`` kwarg, formatted via
``pipelex.temporal.tprl.observability.build_activity_summary``.
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
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.tprl_content_generation.content_generator_in_workflow import ContentGeneratorInWorkflow
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider


class _Person(BaseModel):
    name: str
    age: int


def _make_job_metadata() -> JobMetadata:
    return JobMetadata(user_id="test-user", pipeline_run_id="test-run", pipe_code="my_pipe")


def _make_generator() -> ContentGeneratorInWorkflow:
    factory = GeneratedContentFactory(storage_provider=InMemoryStorageProvider())
    return ContentGeneratorInWorkflow(generated_content_factory=factory)


def _make_llm_setting() -> LLMSetting:
    return LLMSetting(model="test-llm", temperature=0.5)


def _make_page_content() -> PageContent:
    return PageContent(text_and_images=TextAndImagesContent(text=None, images=None))


def _make_activity_error(message: str = "activity failed") -> ActivityError:
    """Construct an ``ActivityError`` with stub identifiers for tests."""
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
def patch_workflow_runtime(mocker: MockerFixture) -> None:
    """Patch ``workflow.unsafe.is_replaying_history_events`` so the error-path
    tests can exercise the catch block outside a real workflow context.

    The non-error tests rely solely on ``temporalio.workflow.execute_activity``
    being patched, which the individual tests do themselves.
    """
    mocker.patch("temporalio.workflow.unsafe.is_replaying_history_events", return_value=False)


@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.usefixtures("patch_workflow_runtime")
class TestContentGeneratorInWorkflow:
    """Per-method assertions on the activity-dispatch kwargs."""

    async def test_make_llm_text_omits_activity_id_and_sets_summary(self, mocker: MockerFixture) -> None:
        """``make_llm_text`` must never customize ``activity_id`` (the SDK assigns it)
        and must carry the per-call meaning in ``summary=``.
        """
        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.return_value = "stub text"
        generator = _make_generator()

        await generator.make_llm_text(
            job_metadata=_make_job_metadata(),
            llm_setting_main=_make_llm_setting(),
            llm_prompt_for_text=LLMPrompt(user_text="hello"),
        )

        kwargs = mock_execute.call_args.kwargs
        assert kwargs.get("activity_id") is None
        assert kwargs.get("summary") == "LLM text · pipe=my_pipe · model=test-llm"
        # Empty activity_queues → hybrid fallback omits task_queue.
        assert "task_queue" not in kwargs

    @pytest.mark.parametrize(
        ("caller", "expected_summary_prefix"),
        [
            ("make_object", "LLM object · pipe=my_pipe · class=_Person"),
            ("make_object_list", "LLM object list · pipe=my_pipe · class=_Person"),
            ("make_single_image", "Img gen 1× · pipe=my_pipe · model=test-handle"),
            ("make_image_list", "Img gen N× · pipe=my_pipe · model=test-handle · n=2"),
            ("make_templated_text", "Templated text · pipe=my_pipe"),
            ("make_render_page_views", "Render page views · pipe=my_pipe"),
        ],
    )
    async def test_non_llm_text_methods_omit_activity_id_and_set_summary(
        self,
        mocker: MockerFixture,
        caller: str,
        expected_summary_prefix: str,
    ) -> None:
        """Every non-llm-text method routes through ``resolve_dispatch`` and must
        never customize ``activity_id``. The per-call meaning lives in ``summary=``.
        """
        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.return_value = self._stub_for(caller)
        generator = _make_generator()

        await self._invoke(generator, caller)

        kwargs = mock_execute.call_args.kwargs
        assert kwargs.get("activity_id") is None, f"{caller} must not customize activity_id"
        assert kwargs.get("summary") == expected_summary_prefix
        assert "task_queue" not in kwargs, f"{caller} should omit task_queue with empty activity_queues (got {kwargs.get('task_queue')!r})"

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
        assert "task_queue" not in kwargs
        assert kwargs.get("activity_id") is None
        assert kwargs.get("summary") == "Extract pages · pipe=my_pipe · handle=test-handle"

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
        assert mock_execute.call_args.kwargs.get("activity_id") is None
        assert mock_execute.call_args.kwargs.get("summary") == "Extract pages · pipe=my_pipe · handle=test-handle"

    async def test_make_extract_pages_document_uri_with_page_views_dispatches_two_activities(self, mocker: MockerFixture) -> None:
        """When ``document_uri`` is set and ``should_include_page_views`` is true, both
        the extract and render activities are dispatched. ``activity_id`` is never
        customized on either; the SDK assigns sequential integers.
        """
        page = _make_page_content()
        page_view = ImageContent(url="test://view.png")
        return_queue: list[Any] = [[page], [page_view]]

        def _side_effect(*_args: Any, **_kwargs: Any) -> Any:
            return return_queue.pop(0)

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
        for call in mock_execute.call_args_list:
            assert call.kwargs.get("activity_id") is None
            assert "task_queue" not in call.kwargs
        summaries = [call.kwargs.get("summary") for call in mock_execute.call_args_list]
        assert summaries == [
            "Extract pages · pipe=my_pipe · handle=test-handle",
            "Render page views (extract) · pipe=my_pipe",
        ]
        assert result[0].page_view is page_view

    async def test_make_templated_text_updates_content_generation_job_id(self, mocker: MockerFixture) -> None:
        """``make_templated_text`` must set ``job_metadata.content_generation_job_id``
        consistently with every other activity-dispatching method.
        """
        mock_execute = mocker.patch("temporalio.workflow.execute_activity", new_callable=mocker.AsyncMock)
        mock_execute.return_value = "rendered"
        generator = _make_generator()
        job_metadata = _make_job_metadata()

        await generator.make_templated_text(
            job_metadata=job_metadata,
            context={"key": "value"},
            template="{{ key }}",
        )

        assert job_metadata.content_generation_job_id == "make_templated_text"

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
